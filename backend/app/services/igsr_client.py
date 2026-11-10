"""International Genome Sample Resource (IGSR) / 1000 Genomes client.

* Population metadata from the IGSR data-portal API (Elasticsearch,
  ``www.internationalgenome.org/api/beta``).
* Phase 3 sample → population panel (``integrated_call_samples_v3.20130502.ALL.panel``).
* Variant records for a gene region read directly from the phase 3 GRCh37
  VCFs on the EBI FTP server with HTTP range requests + the tabix index
  (see :mod:`app.services.tabix`). Only INFO fields are kept.

Phase 3 genotypes are complete for all 2,504 samples, so each super-population's
allele number is 2 × its sample count on autosomes. Population AC is derived as
round(super-population AF × AN) – recorded as a QC note on every record.
"""
from __future__ import annotations

import gzip
import io
import json
from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.services.cache import DiskCache
from app.services.http import ExternalServiceError, request_with_retry
from app.services.tabix import TabixIndex, bgzf_decompress_counted
from app.sources.tracking import record_error, record_retrieval

FTP = "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502"
PANEL = f"{FTP}/integrated_call_samples_v3.20130502.ALL.panel"
API = "https://www.internationalgenome.org/api/beta"
SUPERPOPS = {"AFR": ("afr", "African"), "AMR": ("amr", "Admixed American"), "EAS": ("eas", "East Asian"),
             "EUR": ("eur", "European"), "SAS": ("sas", "South Asian")}
MAX_RANGE_BYTES = 60_000_000


def vcf_url(chrom: str) -> str:
    c = str(chrom).replace("chr", "")
    if c == "X":
        return f"{FTP}/ALL.chrX.phase3_shapeit2_mvncall_integrated_v1c.20130502.genotypes.vcf.gz"
    if c == "Y":
        return f"{FTP}/ALL.chrY.phase3_integrated_v2b.20130502.genotypes.vcf.gz"
    if c in ("MT", "M"):
        return f"{FTP}/ALL.chrMT.phase3_callmom-v0_4.20130502.genotypes.vcf.gz"
    return f"{FTP}/ALL.chr{c}.phase3_shapeit2_mvncall_integrated_v5b.20130502.genotypes.vcf.gz"


def parse_info(info: str) -> dict:
    out = {}
    for kv in info.split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = v
        else:
            out[kv] = True
    return out


def vcf_line_to_rows(line: str, superpop_n: dict[str, int], gene_symbol: str) -> list[dict]:
    """Convert one phase 3 VCF line (multi-allelic aware) to GeneLens frequency rows."""
    f = line.split("\t", 8)
    chrom, pos, vid, ref, alts, _q, filt, info = f[:8]
    inf = parse_info(info)
    alts_l = alts.split(",")
    an = int(inf["AN"]) if "AN" in inf else None
    acs = inf.get("AC", "").split(",")
    rows = []
    for i, alt in enumerate(alts_l):
        if alt.startswith("<") or "[" in alt or "]" in alt:
            continue  # symbolic structural alleles (<DEL>, <CN0>, …) have no sequence to match
        ac = int(acs[i]) if i < len(acs) and acs[i].isdigit() else None
        pops = []
        for sp, (pid, label) in SUPERPOPS.items():
            vals = inf.get(f"{sp}_AF", "").split(",")
            if i < len(vals) and vals[i] not in ("", "."):
                p_af = float(vals[i])
                p_an = 2 * superpop_n.get(sp, 0) if chrom not in ("X", "Y", "MT") else None
                if p_an:
                    pops.append({"id": pid, "label": label, "an": p_an, "ac": round(p_af * p_an),
                                 "af": round(p_af * p_an) / p_an, "homozygote_count": None})
        rows.append({
            "source": "1000 Genomes", "gene_symbol": gene_symbol, "chrom": chrom, "pos": int(pos), "ref": ref,
            "alt": alt, "rsid": vid if vid.startswith("rs") else None, "gnomad_variant_id": None,
            "consequence": None, "hgvsc": None, "hgvsp": None, "ac": ac, "an": an,
            "af": (ac / an) if ac is not None and an else None, "populations": pops,
            "popmax_af": max((p["af"] for p in pops if p["ac"] > 0), default=None),
            "popmax_population": max(((p["af"], p["id"]) for p in pops if p["ac"] > 0), default=(None, None))[1],
            "gnomad_filters": [] if filt in ("PASS", ".") else [f"1kg:{filt}"],
            "gnomad_flags": [f"VT:{inf.get('VT')}"] if inf.get("VT") else [],
            "count_basis": "1000G phase 3 INFO AC/AN", "homozygote_count": None,
            "qc_flags": ["population_ac_derived_from_af"] if pops else [],
        })
    return rows


class IGSRClient:
    service = "IGSR / 1000 Genomes"
    source_id = "igsr"

    def __init__(self, cache: DiskCache | None = None):
        self.cache = cache or DiskCache("igsr")

    def populations(self) -> dict:
        """Super-population sample counts from the phase 3 panel + population names from the IGSR API."""
        key = DiskCache.key("igsr_pops_v1")
        if hit := self.cache.get(key):
            return hit["payload"]
        try:
            panel = request_with_retry("GET", PANEL, self.service).text
            body = request_with_retry("POST", f"{API}/population/_search", self.service,
                                      json={"size": 100, "query": {"match_all": {}}}).json()
        except ExternalServiceError as exc:
            record_error(self.source_id, str(exc))
            raise
        counts: dict[str, int] = {}
        pop_counts: dict[str, int] = {}
        for line in panel.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3:
                counts[parts[2]] = counts.get(parts[2], 0) + 1
                pop_counts[parts[1]] = pop_counts.get(parts[1], 0) + 1
        names = {h["_source"]["code"]: {"name": h["_source"].get("name"),
                                         "description": h["_source"].get("description"),
                                         "superpopulation": (h["_source"].get("superpopulation") or {}).get("code")}
                 for h in body.get("hits", {}).get("hits", [])}
        out = {"superpopulation_samples": counts, "population_samples": pop_counts,
               "populations": {k: {**names.get(k, {}), "phase3_samples": v} for k, v in pop_counts.items()},
               "total_samples": sum(counts.values())}
        self.cache.set(key, out)
        record_retrieval(self.source_id, len(pop_counts))
        return out

    def fetch_region(self, chrom: str, start: int, end: int, gene_symbol: str) -> tuple[list[dict], dict]:
        """All phase 3 variant records overlapping chrom:start-end (1-based, inclusive, GRCh37)."""
        key = DiskCache.key("igsr_region_v2", chrom, start, end)
        if hit := self.cache.get(key):
            return hit["payload"], {**hit["meta"], "access_mode": "cache"}
        url = vcf_url(chrom)
        try:
            idx_key = DiskCache.key("tbi", url)
            if hit := self.cache.get(idx_key):
                raw_idx = bytes.fromhex(hit["payload"])
            else:
                raw_idx = request_with_retry("GET", url + ".tbi", self.service).content
                self.cache.set(idx_key, raw_idx.hex())
            index = TabixIndex(raw_idx)
            voff = index.start_offset(str(chrom), start - 1)
            pops = self.populations()["superpopulation_samples"]
            rows: list[dict] = []
            if voff is not None:
                coff, uoff = voff >> 16, voff & 0xFFFF
                buf, done, fetched, step = "", False, 0, 512 * 1024
                with httpx.Client(timeout=120, follow_redirects=True) as cl:
                    while not done:
                        r = cl.get(url, headers={"Range": f"bytes={coff}-{coff + step - 1}"})
                        if r.status_code not in (200, 206):
                            raise ExternalServiceError(self.service, f"range request HTTP {r.status_code}", r.status_code)
                        data, used = bgzf_decompress_counted(r.content)
                        fetched += used
                        if used == 0 or fetched > MAX_RANGE_BYTES:
                            break  # end of file, or safety limit reached
                        text = data[uoff:].decode("utf-8", "replace")
                        uoff, coff = 0, coff + used
                        lines = (buf + text).split("\n")
                        buf = lines.pop()  # possibly incomplete last line
                        for line in lines:
                            if not line or line.startswith("#"):
                                continue
                            parts = line.split("\t", 2)
                            if len(parts) < 3 or not parts[1].isdigit():
                                continue
                            if parts[0] != str(chrom) or int(parts[1]) > end:
                                done = True
                                break
                            if int(parts[1]) >= start:
                                rows.extend(vcf_line_to_rows(line, pops, gene_symbol))
                        step = min(step * 2, 8 * 1024 * 1024)
        except ExternalServiceError as exc:
            record_error(self.source_id, str(exc))
            raise
        seen, unique = set(), []
        for r in rows:  # chunks can overlap at block boundaries
            k = (r["pos"], r["ref"], r["alt"])
            if k not in seen:
                seen.add(k)
                unique.append(r)
        meta = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "access_mode": "live_api",
                "dataset": "igsr_1000g_phase3", "dataset_label": "1000 Genomes Project phase 3",
                "release": "Phase 3 (release 20130502), GRCh37", "reference_genome": "GRCh37",
                "query": f"tabix {url.rsplit('/', 1)[-1]} {chrom}:{start}-{end}"}
        self.cache.set(key, unique, meta)
        record_retrieval(self.source_id, len(unique))
        return unique, meta

    def ping_files(self) -> str:
        r = request_with_retry("HEAD", vcf_url("22") + ".tbi", self.service)
        return r.headers.get("Last-Modified", "")

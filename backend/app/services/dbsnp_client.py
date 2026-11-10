"""NCBI dbSNP clients.

* **Gene-level RefSNP retrieval** – E-utilities ``esearch``/``esummary`` on
  ``db=snp`` (batched, rate-limited, cached). Each RefSNP summary carries
  canonical SPDI alleles (GRCh38) and per-study allele frequencies
  (``global_mafs``: ``"A=0.027356/137"`` = allele, frequency, allele count).
* **Variation Services API** (``api.ncbi.nlm.nih.gov/variation/v0``) – full
  RefSNP records for one rsID: placements, alleles, per-study allele and total
  counts, clinical cross-references.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.config import get_settings
from app.services.cache import DiskCache
from app.services.clinvar_client import refseq_to_chrom
from app.services.http import ExternalServiceError, request_with_retry
from app.sources.tracking import record_error, record_retrieval

log = logging.getLogger(__name__)
VARIATION_API = "https://api.ncbi.nlm.nih.gov/variation/v0"
# Study used for the headline frequency, in order of preference (largest first).
STUDY_PRIORITY = ["ALFA", "GnomAD_genomes", "1000Genomes_30X", "1000Genomes", "ExAC", "TOPMED"]
MAX_RECORDS = 25_000


def parse_maf(freq: str) -> tuple[str, float, int] | None:
    """``"A=0.027356/137"`` -> ("A", 0.027356, 137)."""
    try:
        allele, rest = freq.split("=", 1)
        f, c = rest.split("/", 1)
        return allele, float(f), int(c)
    except (ValueError, AttributeError):
        return None


def snp_summary_to_rows(doc: dict, study_priority=STUDY_PRIORITY) -> list[dict]:
    """One row per alternate allele of a RefSNP esummary document."""
    rsid = f"rs{doc.get('snp_id') or doc.get('uid')}"
    spdis = [s for s in (doc.get("spdi") or "").split(",") if s]
    mafs = {m.get("study"): parse_maf(m.get("freq", "")) for m in doc.get("global_mafs") or []}
    study = next((s for s in study_priority if mafs.get(s) and mafs[s][1] > 0), None)
    genes = ";".join(g.get("name", "") for g in doc.get("genes") or []) or None
    alts = []
    for s in spdis:
        try:
            acc, p0, d, ins = s.split(":")
        except ValueError:
            continue
        alts.append((refseq_to_chrom(acc), int(p0), d, ins))
    rows = []
    for chrom, p0, deleted, inserted in alts:
        ref, alt = deleted, inserted
        while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
            ref, alt = ref[:-1], alt[:-1]
        ac = an = af = None
        qc = []
        if study:
            allele, f, c = mafs[study]
            an_derived = round(c / f) if f > 0 else None
            if allele == inserted:
                af, ac, an = f, c, an_derived
            elif allele == deleted and len(alts) == 1 and an_derived:
                af, ac, an = 1 - f, an_derived - c, an_derived
            else:
                qc.append("frequency_not_reported_for_allele")
            if an is not None:
                qc.append("an_derived_from_study_frequency")
        else:
            qc.append("no_population_frequency")
        rows.append({
            "source": "dbSNP", "gene_symbol": genes, "chrom": chrom, "pos": p0 + 1, "ref": ref, "alt": alt,
            "rsid": rsid, "consequence": (doc.get("fxn_class") or "").split(",")[0] or None,
            "ac": ac, "an": an, "af": af, "populations": [], "gnomad_filters": [],
            "gnomad_flags": [f"study:{study}"] if study else [], "count_basis": f"dbSNP {study}" if study else None,
            "qc_flags": qc,
        })
    return rows


class DbSNPClient:
    service = "dbSNP"
    source_id = "dbsnp"

    def __init__(self, cache: DiskCache | None = None):
        self.settings = get_settings()
        self.cache = cache or DiskCache("dbsnp")
        self.min_interval = 0.11 if self.settings.ncbi_api_key else 0.35
        self._last = 0.0

    def _eutils(self, endpoint: str, method="GET", **params) -> dict:
        from app.services.clinvar_client import _LAST_START, _THROTTLE_LOCK

        with _THROTTLE_LOCK:  # same NCBI rate limit as ClinVar – one shared throttle
            wait = self.min_interval - (time.monotonic() - _LAST_START[0])
            if wait > 0:
                time.sleep(wait)
            _LAST_START[0] = time.monotonic()
        p = {"db": "snp", "retmode": "json", "tool": "genelens", **params}
        if self.settings.ncbi_api_key:
            p["api_key"] = self.settings.ncbi_api_key
        url = f"{self.settings.ncbi_eutils_url}/{endpoint}"
        try:
            resp = request_with_retry(method, url, self.service, **({"data": p} if method == "POST" else {"params": p}))
            return resp.json()
        except (ExternalServiceError, ValueError) as exc:
            record_error(self.source_id, str(exc))
            raise ExternalServiceError(self.service, str(exc)) from exc

    def info(self) -> dict:
        d = self._eutils("einfo.fcgi")["einforesult"]["dbinfo"][0]
        return {"build": d.get("dbbuild"), "last_update": d.get("lastupdate"), "count": d.get("count")}

    def fetch_gene(self, symbol: str, progress=None) -> tuple[list[dict], dict]:
        symbol = symbol.upper()
        key = DiskCache.key("dbsnp_gene_v1", symbol)
        if hit := self.cache.get(key):
            return hit["payload"], {**hit["meta"], "access_mode": "cache"}
        s = self._eutils("esearch.fcgi", term=f"{symbol}[gene]", usehistory="y", retmax=0)["esearchresult"]
        total = int(s.get("count", 0))
        n = min(total, MAX_RECORDS)
        starts = list(range(0, n, 400))
        done = [0]

        def fetch(start: int) -> list[dict]:
            body = self._eutils("esummary.fcgi", method="POST", WebEnv=s["webenv"], query_key=s["querykey"],
                                retstart=start, retmax=min(400, n - start))
            res = body.get("result") or {}
            done[0] += 1
            if progress:
                progress(min(1.0, done[0] / max(len(starts), 1)))
            return [res[u] for u in res.get("uids", [])]

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=3) as ex:
            docs = [d for batch in ex.map(fetch, starts) for d in batch]
        info = self.info()
        meta = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "access_mode": "live_api",
                "dataset": "dbsnp_refsnp", "release": f"dbSNP {info['build']} (updated {info['last_update']})",
                "query": f"esearch db=snp term={symbol}[gene]", "total_reported": total,
                "truncated": total > MAX_RECORDS}
        self.cache.set(key, docs, meta)
        record_retrieval(self.source_id, len(docs))
        return docs, meta

    def refsnp(self, rsid: str) -> dict:
        """Summarised Variation Services RefSNP record (GRCh38 placement, per-study counts)."""
        num = rsid.lower().removeprefix("rs")
        key = DiskCache.key("refsnp", num)
        if hit := self.cache.get(key):
            d = hit["payload"]
        else:
            try:
                d = request_with_retry("GET", f"{VARIATION_API}/refsnp/{num}", self.service).json()
            except ExternalServiceError as exc:
                record_error(self.source_id, str(exc))
                raise
            self.cache.set(key, d)
            record_retrieval(self.source_id, 1)
        snap = d.get("primary_snapshot_data") or {}
        freqs = []
        for ann in snap.get("allele_annotations") or []:
            for f in ann.get("frequency") or []:
                obs = f.get("observation") or {}
                if f.get("total_count"):
                    freqs.append({"study": f.get("study_name"), "allele": obs.get("inserted_sequence"),
                                  "ref": obs.get("deleted_sequence"), "allele_count": f.get("allele_count"),
                                  "total_count": f.get("total_count"),
                                  "af": f["allele_count"] / f["total_count"]})
        clin = sorted({c.get("accession_version") for ann in snap.get("allele_annotations") or []
                       for c in ann.get("clinical") or [] if c.get("accession_version")})
        return {"source": "NCBI Variation Services", "rsid": f"rs{num}", "variant_type": snap.get("variant_type"),
                "created": d.get("create_date"), "updated": d.get("last_update_date"),
                "build": d.get("last_update_build_id"), "frequencies": freqs[:40], "clinvar_rcv": clin[:20],
                "merged_rsids": [f"rs{m.get('merged_rsid')}" for m in d.get("dbsnp1_merges") or []][:10]}

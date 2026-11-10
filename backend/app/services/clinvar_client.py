"""ClinVar ingestion.

Two official access routes are supported:

1. **NCBI E-utilities** (default, targeted): ``esearch`` for ``<GENE>[gene]``
   followed by batched ``esummary`` calls. Coordinates come from the
   record's *canonical SPDI* (GRCh38, 0-based interbase), which is
   converted to 1-based VCF-style fields. Fast for one gene; no bulk download.
2. **variant_summary.txt.gz** (bulk TSV, ~450 MB): downloaded once and
   streamed in chunks with pandas, keeping only rows for the requested gene
   and assembly. Provides VCF-normalised columns (``PositionVCF``,
   ``ReferenceAlleleVCF``, ``AlternateAlleleVCF``) and Allele IDs. Required
   for GRCh37 analyses because SPDI is only provided for GRCh38.

Both routes produce identical standardised records (see ``CLINVAR_FIELDS``).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import get_settings
from app.services.cache import DiskCache
from app.services.http import ExternalServiceError, request_with_retry
from app.sources.tracking import record_error, record_retrieval

log = logging.getLogger(__name__)

CLINVAR_FIELDS = [
    "clinvar_variation_id", "clinvar_allele_id", "gene_symbol", "chrom", "pos", "ref", "alt",
    "clinical_significance", "review_status", "conditions", "submitter_count",
    "last_evaluated", "clinvar_type", "name", "rsid", "coordinate_source",
]

TSV_COLUMNS = [
    "AlleleID", "Type", "Name", "GeneSymbol", "ClinicalSignificance", "LastEvaluated",
    "RS# (dbSNP)", "PhenotypeList", "Assembly", "Chromosome", "ReviewStatus",
    "NumberSubmitters", "VariationID", "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF",
]


def spdi_to_vcf(spdi: str) -> tuple[str, int, str, str] | None:
    """Convert a canonical SPDI (``NC_000017.11:43045766:G:A``) to (chrom, pos, ref, alt).

    SPDI positions are 0-based interbase. For SNVs/MNVs ``pos = position + 1``.
    For indels the deleted and inserted sequences in a *normalised* SPDI share
    flanking context; we trim the shared suffix (keeping one base) so the
    record keeps a valid anchor base. Pure insertions/deletions without shared
    context keep an empty allele – the matching engine handles them through
    minimal-representation keys.
    """
    try:
        acc, pos0, deleted, inserted = spdi.split(":")
        pos0 = int(pos0)
    except (ValueError, AttributeError):
        return None
    chrom = refseq_to_chrom(acc)
    if chrom is None:
        return None
    ref, alt = deleted, inserted
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    return chrom, pos0 + 1, ref, alt


def refseq_to_chrom(accession: str) -> str | None:
    """NC_000017.11 -> '17', NC_000023 -> 'X', NC_000024 -> 'Y', NC_012920 -> 'MT'."""
    if accession.startswith("NC_012920"):
        return "MT"
    if not accession.startswith("NC_0000"):
        return None
    num = int(accession.split(".")[0][3:])
    return {23: "X", 24: "Y"}.get(num, str(num))


def _unique(items) -> list:
    """De-duplicate while preserving order."""
    return list(dict.fromkeys(items))


def parse_esummary_record(rec: dict) -> dict:
    """Map one ClinVar esummary document to the standard record format."""
    germ = rec.get("germline_classification") or {}
    vsets = rec.get("variation_set") or [{}]
    vset = vsets[0]
    # Haplotypes / compound records describe several alleles together. Their
    # classification applies to the combination, never to a single allele,
    # so they are kept (visible, clinvar_only) but never given coordinates.
    multi_allele = len(vsets) > 1
    coords = None if multi_allele else spdi_to_vcf(vset.get("canonical_spdi") or "")
    traits = _unique(t.get("trait_name") for t in germ.get("trait_set") or [] if t.get("trait_name"))
    rsids = [x["db_id"] for x in vset.get("variation_xrefs") or [] if x.get("db_source") == "dbSNP"]
    chrom = pos = ref = alt = None
    coordinate_source = "missing"
    if multi_allele:
        coordinate_source = "multi_allele_record"
    elif coords:
        chrom, pos, ref, alt = coords
        coordinate_source = "canonical_spdi"
    else:  # fall back to location only (no alleles) – cannot be matched exactly
        for loc in vset.get("variation_loc") or []:
            if loc.get("assembly_name") == "GRCh38" and loc.get("status") == "current":
                chrom = loc.get("chr") or None
                pos = int(loc["start"]) if loc.get("start", "").isdigit() else None
                coordinate_source = "location_only"
    last_eval = (germ.get("last_evaluated") or "").split(" ")[0] or None
    locs = {}
    for loc in vset.get("variation_loc") or []:
        if loc.get("assembly_name") in ("GRCh38", "GRCh37") and str(loc.get("start", "")).isdigit():
            locs[loc["assembly_name"]] = {"chr": loc.get("chr"), "start": int(loc["start"])}
    return {
        "clinvar_variation_id": str(rec.get("uid")),
        "clinvar_allele_id": str(vset.get("measure_id")) if vset.get("measure_id") else None,
        "gene_symbol": ";".join(_unique(g.get("symbol") for g in rec.get("genes") or [] if g.get("symbol"))) or None,
        "chrom": chrom, "pos": pos, "ref": ref, "alt": alt,
        "clinical_significance": germ.get("description") or None,
        "review_status": germ.get("review_status") or None,
        "conditions": "|".join(traits) or None,
        "submitter_count": len(rec.get("supporting_submissions", {}).get("scv") or []) or None,
        "last_evaluated": last_eval,
        "clinvar_type": rec.get("obj_type"),
        "name": rec.get("title"),
        "rsid": f"rs{rsids[0]}" if rsids else None,
        "coordinate_source": coordinate_source,
        "locations": locs,
    }


def to_grch37(rec: dict) -> dict:
    """Express an E-utilities ClinVar record (GRCh38 SPDI alleles) in GRCh37 coordinates.

    ClinVar reports the variant's start on both assemblies. Their difference is
    the local GRCh38→GRCh37 coordinate offset, applied to the SPDI-derived
    position; alleles are unchanged (the reference strand is the same). Records
    without both locations, or whose chromosome differs, get no coordinates
    and become *unmatchable* – they are never guessed.
    """
    out = dict(rec)
    locs = rec.get("locations") or {}
    l38, l37 = locs.get("GRCh38"), locs.get("GRCh37")
    if rec.get("pos") is None or not (l38 and l37) or str(l38.get("chr")) != str(l37.get("chr")):
        out.update(pos=None, ref=None, alt=None, coordinate_source=(
            rec.get("coordinate_source") if rec.get("coordinate_source") == "multi_allele_record"
            else "no_grch37_location"))
        return out
    out["pos"] = rec["pos"] + (l37["start"] - l38["start"])
    out["coordinate_source"] = "grch37_location_offset"
    return out


# Shared across clients/threads so concurrent batches still respect NCBI's request-rate policy.
_THROTTLE_LOCK = threading.Lock()
_LAST_START = [0.0]
MAX_IN_FLIGHT = 3


class ClinVarClient:
    service = "ClinVar"
    BATCH = 400

    def __init__(self, cache: DiskCache | None = None):
        self.settings = get_settings()
        self.cache = cache or DiskCache("clinvar")
        # NCBI policy: 3 requests/s without key, 10/s with key.
        self.min_interval = 0.11 if self.settings.ncbi_api_key else 0.35
        self._last = 0.0

    def _params(self, **kw) -> dict:
        p = {"db": "clinvar", "retmode": "json", "tool": "genelens", **kw}
        if self.settings.ncbi_api_key:
            p["api_key"] = self.settings.ncbi_api_key
        if self.settings.ncbi_email:
            p["email"] = self.settings.ncbi_email
        return p

    def _throttle(self):
        """Space request *starts* by ``min_interval`` (NCBI: ≤3 req/s without key, ≤10 with). Thread-safe."""
        with _THROTTLE_LOCK:
            wait = self.min_interval - (time.monotonic() - _LAST_START[0])
            if wait > 0:
                time.sleep(wait)
            _LAST_START[0] = time.monotonic()

    def _get(self, endpoint: str, method: str = "GET", **params) -> dict:
        self._throttle()
        url = f"{self.settings.ncbi_eutils_url}/{endpoint}"
        if method == "POST":
            resp = request_with_retry("POST", url, self.service, data=self._params(**params))
        else:
            resp = request_with_retry("GET", url, self.service, params=self._params(**params))
        try:
            return resp.json()
        except ValueError as exc:
            raise ExternalServiceError(self.service, f"invalid JSON from {endpoint}") from exc

    # -- E-utilities --------------------------------------------------------
    def fetch_gene_eutils(self, symbol: str, progress=None) -> tuple[list[dict], dict]:
        symbol = symbol.upper()
        key = DiskCache.key("eutils_gene_v2", symbol)
        hit = self.cache.get(key)
        if hit:
            return hit["payload"], {**hit["meta"], "access_mode": "cache"}

        try:
            return self._fetch_gene_eutils_live(symbol, key, progress)
        except ExternalServiceError as exc:
            from app.services.gnomad_client import load_snapshot

            record_error("clinvar_eutils", str(exc))
            if exc.status_code == 404:
                raise
            snap = load_snapshot(symbol, "clinvar", "esummary")
            if snap is None:
                raise
            log.warning("NCBI unavailable – using offline ClinVar snapshot for %s", symbol)
            return snap["payload"], {**snap["meta"], "access_mode": "offline_snapshot"}

    def _fetch_gene_eutils_live(self, symbol: str, key: str, progress=None) -> tuple[list[dict], dict]:
        term = f"{symbol}[gene]"
        search = self._get("esearch.fcgi", term=term, usehistory="y", retmax=0)["esearchresult"]
        if "ERROR" in search:
            raise ExternalServiceError(self.service, search["ERROR"])
        total = int(search.get("count", 0))
        webenv, qkey = search.get("webenv"), search.get("querykey")
        # Batches are fetched concurrently (≤3 in flight); the shared throttle keeps request
        # starts within NCBI's rate limit. Results are re-assembled in order.
        starts = list(range(0, total, self.BATCH))
        done = [0]

        def fetch(start: int) -> list[dict]:
            body = self._get("esummary.fcgi", method="POST", WebEnv=webenv, query_key=qkey,
                             retstart=start, retmax=self.BATCH)
            result = body.get("result") or {}
            out = [parse_esummary_record(result[uid]) for uid in result.get("uids", [])]
            done[0] += 1
            if progress:
                progress(min(1.0, done[0] / max(len(starts), 1)))
            return out

        with ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT) as ex:
            records = [r for batch in ex.map(fetch, starts) for r in batch]
        meta = {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "access_mode": "live_api",
            "dataset": "clinvar_esummary",
            "release": f"ClinVar live (E-utilities, retrieved {datetime.now(timezone.utc):%Y-%m-%d})",
            "query": f"esearch db=clinvar term={term}",
            "total_reported": total,
        }
        self.cache.set(key, records, meta)
        record_retrieval("clinvar_eutils", len(records))
        return records, meta

    # -- Bulk TSV ---------------------------------------------------------------
    @property
    def tsv_path(self) -> Path:
        return self.settings.raw_dir / "variant_summary.txt.gz"

    def download_tsv(self, force: bool = False, progress=None, byte_progress=None) -> Path:
        """Stream the official variant_summary.txt.gz to the raw data directory."""
        import httpx

        path = self.tsv_path
        if path.exists() and not force:
            return path
        tmp = path.with_suffix(".part")
        with httpx.stream("GET", self.settings.clinvar_tsv_url, timeout=None, follow_redirects=True) as r:
            if r.status_code != 200:
                raise ExternalServiceError(self.service, f"TSV download HTTP {r.status_code}", r.status_code)
            total = int(r.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(done / total)
                    if byte_progress:
                        byte_progress(done, total or None)
        tmp.replace(path)
        return path

    def fetch_gene_tsv(self, symbol: str, genome: str, tsv_path: Path | None = None,
                       chunksize: int = 200_000) -> tuple[list[dict], dict]:
        symbol = symbol.upper()
        src = tsv_path or self.tsv_path
        if not src.exists():
            raise ExternalServiceError(
                self.service,
                f"variant_summary.txt.gz not found at {src}. Run: python -m scripts.download_clinvar",
                503,
            )
        cache_file = self.settings.processed_dir / f"clinvar_{symbol}_{genome}_{int(src.stat().st_mtime)}.csv.gz"
        if cache_file.exists():
            df = pd.read_csv(cache_file, dtype=str, keep_default_na=False)
            mode = "cache"
        else:
            parts = []
            reader = pd.read_csv(src, sep="\t", usecols=TSV_COLUMNS, dtype=str, chunksize=chunksize,
                                 compression="infer", keep_default_na=False)
            for chunk in reader:
                genes = chunk["GeneSymbol"].str.upper().str.split(";")
                mask = (chunk["Assembly"] == genome) & genes.apply(lambda g: symbol in g)
                if mask.any():
                    parts.append(chunk[mask])
            df = pd.concat(parts) if parts else pd.DataFrame(columns=TSV_COLUMNS)
            df.to_csv(cache_file, index=False)
            mode = "local_tsv"
        records = [tsv_row_to_record(r) for r in df.to_dict("records")]
        if mode == "local_tsv":
            record_retrieval("clinvar_tsv", len(records))
        meta = {
            "retrieved_at": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(),
            "access_mode": mode,
            "dataset": "clinvar_variant_summary",
            "release": f"variant_summary.txt.gz (file date {datetime.fromtimestamp(src.stat().st_mtime):%Y-%m-%d})",
            "query": f"GeneSymbol contains {symbol} AND Assembly == {genome}",
        }
        return records, meta

    def ping(self) -> bool:
        body = self._get("einfo.fcgi")
        return "einforesult" in body


def _na(v):
    return None if v in (None, "", "-", "na", "NA") else v


def tsv_row_to_record(r: dict) -> dict:
    pos = _na(r.get("PositionVCF"))
    rs = _na(r.get("RS# (dbSNP)"))
    n_sub = _na(r.get("NumberSubmitters"))
    ref, alt = _na(r.get("ReferenceAlleleVCF")), _na(r.get("AlternateAlleleVCF"))
    return {
        "clinvar_variation_id": _na(r.get("VariationID")),
        "clinvar_allele_id": _na(r.get("AlleleID")),
        "gene_symbol": _na(r.get("GeneSymbol")),
        "chrom": _na(r.get("Chromosome")),
        "pos": int(pos) if pos and pos.isdigit() and int(pos) > 0 else None,
        "ref": ref, "alt": alt,
        "clinical_significance": _na(r.get("ClinicalSignificance")),
        "review_status": _na(r.get("ReviewStatus")),
        "conditions": _na(r.get("PhenotypeList")),
        "submitter_count": int(n_sub) if n_sub and n_sub.isdigit() else None,
        "last_evaluated": _na(r.get("LastEvaluated")),
        "clinvar_type": _na(r.get("Type")),
        "name": _na(r.get("Name")),
        "rsid": f"rs{rs}" if rs and rs != "-1" else None,
        "coordinate_source": "vcf_columns" if pos and ref and alt else "missing",
    }

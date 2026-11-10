"""UCSC Genome Browser REST API client (https://api.genome.ucsc.edu).

Provides assembly descriptions, RefSeq gene coordinates and cytogenetic bands
for a gene region – used to cross-check gene coordinates between sources.
"""
from __future__ import annotations

from app.services.cache import DiskCache
from app.services.http import ExternalServiceError, request_with_retry
from app.sources.tracking import record_error, record_retrieval

BASE = "https://api.genome.ucsc.edu"
UCSC_DB = {"GRCh38": "hg38", "GRCh37": "hg19"}
GENE_TRACK = {"GRCh38": "ncbiRefSeqSelect", "GRCh37": "ncbiRefSeqCurated"}


class UCSCClient:
    service = "UCSC Genome Browser"
    source_id = "ucsc"

    def __init__(self, cache: DiskCache | None = None):
        self.cache = cache or DiskCache("ucsc")

    def _get(self, path: str, params: dict, cache: bool = True):
        key = DiskCache.key(path, params)
        if cache and (hit := self.cache.get(key)):
            return hit["payload"]
        try:
            # UCSC uses ';' or '&' separated params; httpx '&' encoding is accepted.
            resp = request_with_retry("GET", BASE + path, self.service, params=params)
        except ExternalServiceError as exc:
            record_error(self.source_id, str(exc))
            raise
        data = resp.json()
        if "error" in data:
            raise ExternalServiceError(self.service, data["error"], 400)
        if cache:
            self.cache.set(key, data)
        return data

    def assemblies(self) -> dict:
        d = self._get("/list/ucscGenomes", {}, cache=True)
        return {g: d["ucscGenomes"][db]["description"] for g, db in UCSC_DB.items()}

    def gene_region(self, symbol: str, genome: str, chrom: str, start: int, end: int) -> dict:
        db = UCSC_DB[genome]
        c = chrom if chrom.startswith("chr") else f"chr{chrom}"
        track = GENE_TRACK[genome]
        d = self._get("/getData/track", {"genome": db, "track": track, "chrom": c,
                                         "start": max(0, start - 1000), "end": end + 1000})
        rows = [r for r in d.get(track, []) if r.get("name2", "").upper() == symbol.upper()]
        bands = self._get("/getData/track", {"genome": db, "track": "cytoBand", "chrom": c,
                                             "start": start, "end": end}).get("cytoBand", [])
        record_retrieval(self.source_id, len(rows) + len(bands))
        tx = [{"name": r["name"], "strand": r["strand"], "tx_start": r["txStart"] + 1, "tx_end": r["txEnd"],
               "exons": r.get("exonCount")} for r in rows]
        return {
            "source": "UCSC", "genome": genome, "ucsc_db": db, "track": track, "transcripts": tx,
            "start": min((t["tx_start"] for t in tx), default=None), "end": max((t["tx_end"] for t in tx), default=None),
            "cytoband": f"{c.replace('chr', '')}{bands[0]['name']}" if bands else None,
            "data_time": d.get("dataTime"),
        }

"""Ensembl REST API client (https://rest.ensembl.org, GRCh37: https://grch37.rest.ensembl.org).

Used for gene identifiers/names/coordinates/transcripts and on-demand VEP
variant annotation. Ensembl allows 15 requests/s; responses are cached.
"""
from __future__ import annotations

from app.pipeline.normalization import minimal_representation
from app.services.cache import DiskCache
from app.services.http import ExternalServiceError, request_with_retry
from app.sources.tracking import record_error, record_retrieval

BASES = {"GRCh38": "https://rest.ensembl.org", "GRCh37": "https://grch37.rest.ensembl.org"}
JSON = {"Content-Type": "application/json", "Accept": "application/json"}


class EnsemblClient:
    service = "Ensembl"
    source_id = "ensembl"

    def __init__(self, cache: DiskCache | None = None):
        self.cache = cache or DiskCache("ensembl")

    def _get(self, path: str, genome: str = "GRCh38", params: dict | None = None, cache: bool = True):
        key = DiskCache.key(genome, path, params)
        if cache and (hit := self.cache.get(key)):
            return hit["payload"]
        try:
            resp = request_with_retry("GET", BASES[genome] + path, self.service, params=params, headers=JSON)
        except ExternalServiceError as exc:
            record_error(self.source_id, str(exc))
            raise
        data = resp.json()
        if cache:
            self.cache.set(key, data)
        return data

    def release(self) -> str:
        rel = self._get("/info/data", cache=False).get("releases", ["?"])
        return f"Ensembl release {rel[0]}"

    def lookup_gene(self, symbol: str, genome: str = "GRCh38") -> dict:
        d = self._get(f"/lookup/symbol/homo_sapiens/{symbol.upper()}", genome, {"expand": 0})
        record_retrieval(self.source_id, 1)
        desc = (d.get("description") or "")
        return {
            "source": "Ensembl", "genome": genome, "ensembl_id": d.get("id"), "symbol": d.get("display_name"),
            "name": desc.split(" [Source")[0] or None, "biotype": d.get("biotype"),
            "chrom": d.get("seq_region_name"), "start": d.get("start"), "end": d.get("end"),
            "strand": d.get("strand"), "canonical_transcript": d.get("canonical_transcript"),
            "assembly": d.get("assembly_name"),
        }

    def vep(self, chrom: str, pos: int, ref: str, alt: str, genome: str = "GRCh38") -> dict:
        """Annotate one allele with Ensembl VEP (region notation, works for SNVs and indels)."""
        s0, r, a = minimal_representation(pos, ref, alt)
        start, end = s0 + 1, s0 + len(r)  # insertion: end = start - 1 (Ensembl convention)
        path = f"/vep/human/region/{chrom}:{start}-{end}:1/{a or '-'}"
        data = self._get(path, genome)
        record_retrieval(self.source_id, 1)
        hit = data[0] if isinstance(data, list) and data else {}
        tcs = hit.get("transcript_consequences") or []
        canonical = [t for t in tcs if t.get("canonical")] or tcs
        top = canonical[0] if canonical else {}
        return {
            "source": "Ensembl VEP", "genome": genome, "most_severe_consequence": hit.get("most_severe_consequence"),
            "transcript": top.get("transcript_id"), "gene": top.get("gene_symbol"),
            "consequences": top.get("consequence_terms"), "impact": top.get("impact"),
            "amino_acids": top.get("amino_acids"), "protein_position": top.get("protein_start"),
            "sift": top.get("sift_prediction"), "polyphen": top.get("polyphen_prediction"),
            "colocated": [c.get("id") for c in hit.get("colocated_variants") or []][:10],
            "n_transcripts": len(tcs),
        }

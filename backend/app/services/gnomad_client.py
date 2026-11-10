"""gnomAD GraphQL client.

The query fields used here were verified against the live schema by
introspection (see ``scripts/inspect_gnomad_schema.py``). Verified on
2026-11-10: ``gene(gene_symbol, reference_genome)`` exposes
``gnomad_constraint`` and ``variants(dataset)``; each ``Variant`` exposes
``exome``/``genome``/``joint`` sequencing data with ``ac``, ``an``,
``filters`` and ``populations{id ac an homozygote_count}``.

Note: the gene-level ``variants`` resolver returns all variants in one
response (no cursor pagination exists for this field), so pagination is
done by GeneLens itself when serving data to the frontend.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.services.cache import DiskCache
from app.services.http import ExternalServiceError, request_with_retry
from app.sources.tracking import record_error, record_retrieval

log = logging.getLogger(__name__)

# Which reference genome each gnomAD dataset is aligned to.
DATASET_GENOME = {
    "gnomad_r4": "GRCh38",
    "gnomad_r4_non_ukb": "GRCh38",
    "gnomad_r3": "GRCh38",
    "gnomad_r3_non_cancer": "GRCh38",
    "gnomad_r2_1": "GRCh37",
    "gnomad_r2_1_non_cancer": "GRCh37",
    "exac": "GRCh37",
}
DATASET_LABEL = {
    "gnomad_r4": "gnomAD v4 (exomes + genomes)",
    "gnomad_r4_non_ukb": "gnomAD v4 non-UKB subset",
    "gnomad_r3": "gnomAD v3 (genomes)",
    "gnomad_r3_non_cancer": "gnomAD v3 non-cancer",
    "gnomad_r2_1": "gnomAD v2.1 (exomes + genomes)",
    "gnomad_r2_1_non_cancer": "gnomAD v2.1 non-cancer",
    "exac": "ExAC",
}

GENE_QUERY = """
query GeneVariants($symbol: String!, $genome: ReferenceGenomeId!, $dataset: DatasetId!) {
  gene(gene_symbol: $symbol, reference_genome: $genome) {
    gene_id symbol name chrom start stop strand canonical_transcript_id
    mane_select_transcript { ensembl_id ensembl_version }
    gnomad_constraint {
      exp_lof obs_lof oe_lof oe_lof_lower oe_lof_upper pli lof_z
      exp_mis obs_mis oe_mis oe_mis_lower oe_mis_upper mis_z
      exp_syn obs_syn oe_syn oe_syn_lower oe_syn_upper syn_z flags
    }
    variants(dataset: $dataset) {
      variant_id chrom pos ref alt rsids consequence hgvsc hgvsp lof flags
      exome  { ac an af homozygote_count filters populations { id ac an homozygote_count } }
      genome { ac an af homozygote_count filters populations { id ac an homozygote_count } }
      joint  { ac an homozygote_count filters populations { id ac an homozygote_count } }
    }
  }
}
"""

CONSTRAINT_QUERY = """
query Constraint($symbol: String!, $genome: ReferenceGenomeId!) {
  gene(gene_symbol: $symbol, reference_genome: $genome) {
    gene_id symbol name chrom start stop canonical_transcript_id
    mane_select_transcript { ensembl_id ensembl_version }
    gnomad_constraint {
      exp_lof obs_lof oe_lof oe_lof_lower oe_lof_upper pli lof_z
      exp_mis obs_mis oe_mis oe_mis_lower oe_mis_upper mis_z
      exp_syn obs_syn oe_syn oe_syn_lower oe_syn_upper syn_z flags
    }
  }
}
"""

SEARCH_QUERY = """
query Search($q: String!, $genome: ReferenceGenomeId!) {
  gene_search(query: $q, reference_genome: $genome) { ensembl_id symbol }
}
"""

META_QUERY = "{ meta { clinvar_release_date } }"


class GnomadClient:
    service = "gnomAD"

    def __init__(self, cache: DiskCache | None = None):
        self.settings = get_settings()
        self.cache = cache or DiskCache("gnomad")

    # -- low level -----------------------------------------------------
    def _post(self, query: str, variables: dict | None = None) -> dict:
        resp = request_with_retry(
            "POST", self.settings.gnomad_api_url, self.service,
            json={"query": query, "variables": variables or {}},
            headers={"Content-Type": "application/json"},
        )
        body = resp.json()
        if body.get("errors"):
            msgs = "; ".join(e.get("message", "?") for e in body["errors"])
            # gnomAD reports unknown genes as GraphQL errors
            raise ExternalServiceError(self.service, msgs, 404 if "not found" in msgs.lower() else 400)
        return body["data"]

    def _cached(self, name: str, query: str, variables: dict) -> tuple[dict, dict]:
        key = DiskCache.key(name, variables)
        hit = self.cache.get(key)
        if hit:
            return hit["payload"], {**hit["meta"], "access_mode": "cache"}
        try:
            data = self._post(query, variables)
        except ExternalServiceError as exc:
            record_error("gnomad", str(exc))
            raise
        meta = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "access_mode": "live_api"}
        self.cache.set(key, data, meta)
        gene = data.get("gene") if isinstance(data, dict) else None
        record_retrieval("gnomad", len((gene or {}).get("variants") or []) or 1)
        return data, meta

    # -- public API ------------------------------------------------------
    def search_genes(self, q: str, genome: str = "GRCh38") -> list[dict]:
        data, _ = self._cached("search", SEARCH_QUERY, {"q": q, "genome": genome})
        return data.get("gene_search") or []

    def fetch_gene_variants(self, symbol: str, dataset: str) -> tuple[dict, dict]:
        """Return (gene_payload, provenance_meta). Falls back to an offline snapshot."""
        genome = DATASET_GENOME.get(dataset)
        if genome is None:
            raise ValueError(f"Unsupported gnomAD dataset '{dataset}'")
        variables = {"symbol": symbol.upper(), "genome": genome, "dataset": dataset}
        try:
            data, meta = self._cached("gene_variants", GENE_QUERY, variables)
        except ExternalServiceError as exc:
            if exc.status_code in (400, 404):
                raise
            snap = load_snapshot(symbol, "gnomad", dataset)
            if snap is None:
                raise
            log.warning("gnomAD unavailable – using offline snapshot for %s", symbol)
            data, meta = snap["payload"], {**snap["meta"], "access_mode": "offline_snapshot"}
        gene = data.get("gene")
        if not gene:
            raise ExternalServiceError(self.service, f"gene '{symbol}' not found", 404)
        meta.update({"dataset": dataset, "dataset_label": DATASET_LABEL.get(dataset, dataset),
                     "reference_genome": genome, "query": f"gene({symbol}).variants(dataset:{dataset})"})
        return gene, meta

    def fetch_constraint(self, symbol: str, genome: str = "GRCh38") -> tuple[dict, dict]:
        data, meta = self._cached("constraint", CONSTRAINT_QUERY, {"symbol": symbol.upper(), "genome": genome})
        gene = data.get("gene")
        if not gene:
            raise ExternalServiceError(self.service, f"gene '{symbol}' not found", 404)
        return gene, meta

    def ping(self) -> dict:
        data = self._post(META_QUERY)
        return data.get("meta") or {}


def constraint_release(genome: str) -> str:
    # The gnomAD browser serves v4 constraint for GRCh38 genes and v2.1.1 for GRCh37.
    return "gnomAD v4 constraint (browser API)" if genome == "GRCh38" else "gnomAD v2.1.1 constraint (browser API)"


# --------------------------------------------------------------------------
# Offline snapshots: real API responses saved to disk with their original
# retrieval date. Used ONLY when the live API is unreachable, and always
# labelled access_mode="offline_snapshot" in provenance metadata.
# --------------------------------------------------------------------------
def snapshot_path(symbol: str, source: str, dataset: str) -> Path:
    return get_settings().snapshot_dir / f"{symbol.upper()}_{source}_{dataset}.json.gz"


def load_snapshot(symbol: str, source: str, dataset: str) -> dict | None:
    p = snapshot_path(symbol, source, dataset)
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(symbol: str, source: str, dataset: str, payload, meta: dict) -> Path:
    p = snapshot_path(symbol, source, dataset)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump({"meta": meta, "payload": payload}, fh, separators=(",", ":"))
    return p

"""Save REAL gnomAD + ClinVar responses for a gene as an offline snapshot.

Snapshots let the app keep working when the public APIs are unreachable.
They contain genuine records and keep their original retrieval date; the UI
labels them "offline snapshot" so they are never mistaken for a live query.

Usage:  python -m scripts.create_snapshot --gene HBB
"""
from __future__ import annotations

import argparse

from app.services.clinvar_client import ClinVarClient
from app.services.gnomad_client import GnomadClient, save_snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gene", required=True)
    ap.add_argument("--dataset", default="gnomad_r4")
    args = ap.parse_args()
    gene, gmeta = GnomadClient().fetch_gene_variants(args.gene, args.dataset)
    p1 = save_snapshot(args.gene, "gnomad", args.dataset, {"gene": gene}, gmeta)
    records, cmeta = ClinVarClient().fetch_gene_eutils(args.gene)
    p2 = save_snapshot(args.gene, "clinvar", "esummary", records, cmeta)
    print(f"Saved {len(gene['variants'])} gnomAD variants -> {p1}")
    print(f"Saved {len(records)} ClinVar records -> {p2}")


if __name__ == "__main__":
    main()

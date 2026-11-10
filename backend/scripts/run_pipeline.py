"""Run the full research pipeline from the command line (no web server needed).

Usage:  python -m scripts.run_pipeline --gene HBB [--dataset gnomad_r4] [--clinvar-source eutils|tsv]
"""
from __future__ import annotations

import argparse
import json
import logging

from app.database import SessionLocal, init_db
from app.datasets import BY_ID as DATASET_BY_ID
from app.models import AnalysisSession
from app.pipeline.runner import run_analysis


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gene", required=True)
    ap.add_argument("--dataset", default="gnomad_r4", choices=sorted(DATASET_BY_ID))
    ap.add_argument("--clinvar-source", default="eutils", choices=["eutils", "tsv"])
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    with SessionLocal() as db:
        a = AnalysisSession(gene_symbol=args.gene.upper(), dataset=args.dataset,
                            reference_genome=DATASET_BY_ID[args.dataset].assembly,
                            clinvar_source=args.clinvar_source, parameters={})
        db.add(a)
        db.commit()
        a = run_analysis(db, a.id)
        print(json.dumps({"id": a.id, "status": a.status, "error": a.error,
                          "matching": (a.results or {}).get("matching"),
                          "anomalies": (a.results or {}).get("anomaly_summary"),
                          "findings": (a.results or {}).get("interpretation", {}).get("findings")}, indent=2))


if __name__ == "__main__":
    main()

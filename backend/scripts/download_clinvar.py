"""Download the official ClinVar variant_summary.txt.gz (~450 MB) into the raw data directory.

Only needed for the bulk-TSV ClinVar mode (required for GRCh37 analyses).
Usage:  python -m scripts.download_clinvar [--force]
"""
from __future__ import annotations

import argparse
import sys

from app.services.clinvar_client import ClinVarClient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if the file exists")
    args = ap.parse_args()
    client = ClinVarClient()

    def progress(f):
        sys.stdout.write(f"\rDownloading variant_summary.txt.gz … {f:6.1%}")
        sys.stdout.flush()

    path = client.download_tsv(force=args.force, progress=progress)
    print(f"\nSaved to {path} ({path.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()

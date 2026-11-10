"""Introspect the live gnomAD GraphQL schema for the types GeneLens queries.

Run this if a gnomAD query starts failing – it prints the fields that
currently exist so app/services/gnomad_client.py can be updated.
Usage:  python -m scripts.inspect_gnomad_schema
"""
from __future__ import annotations

import httpx

from app.config import get_settings

TYPES = ["Gene", "GnomadConstraint", "Variant", "VariantSequencingTypeData", "VariantJointSequencingTypeData",
         "VariantPopulation", "DatasetId"]
Q = "query($n: String!) { __type(name: $n) { name fields { name } enumValues { name } } }"


def main():
    url = get_settings().gnomad_api_url
    for t in TYPES:
        r = httpx.post(url, json={"query": Q, "variables": {"n": t}}, timeout=60).json()
        ty = (r.get("data") or {}).get("__type") or {}
        names = [f["name"] for f in ty.get("fields") or []] or [e["name"] for e in ty.get("enumValues") or []]
        print(f"{t}: {', '.join(names)}\n")


if __name__ == "__main__":
    main()

"""Measure API latency for the endpoints the UI calls (cold first call + warm median).

Usage (backend running on :8000):
    python -m scripts.perf_benchmark --analysis <id> [--analysis <id> ...] [--compare HBB,CFTR] [--out perf.json]

Cold = first request after the server started (run right after a restart to
measure it); warm = median of 3 repeats. Numbers are wall-clock, client-side.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time

import httpx


def timed(client: httpx.Client, method: str, url: str, **kw) -> tuple[float, int, int]:
    t = time.perf_counter()
    r = client.request(method, url, **kw)
    return (time.perf_counter() - t) * 1000, r.status_code, len(r.content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000/api")
    ap.add_argument("--analysis", action="append", required=True)
    ap.add_argument("--compare", default="HBB,CFTR")
    ap.add_argument("--out")
    args = ap.parse_args()
    b = args.base
    genes = args.compare.split(",")
    cmp_body = {"genes": genes, "dataset": "gnomad_r4", "af_threshold": 0.001}
    wi_body = {**cmp_body, "baseline": {"pathogenic_af": 0.001}, "scenario": {"pathogenic_af": 0.005}}
    cases = [("datasets", "GET", f"{b}/datasets", {}), ("sources", "GET", f"{b}/sources", {}),
             ("genes/suggest (empty)", "GET", f"{b}/genes/suggest", {}),
             ("genes/suggest q=brc", "GET", f"{b}/genes/suggest?q=brc", {})]
    for a in args.analysis:
        cases += [
            (f"[{a}] analysis detail", "GET", f"{b}/analysis/{a}", {}),
            (f"[{a}] dashboard REAL", "GET", f"{b}/dashboard?analysis_id={a}&provenance=REAL", {}),
            (f"[{a}] statistics REAL", "GET", f"{b}/analysis/statistics?analysis_id={a}&provenance=REAL", {}),
            (f"[{a}] statistics BOTH", "GET", f"{b}/analysis/statistics?analysis_id={a}&provenance=BOTH", {}),
            (f"[{a}] populations REAL", "GET", f"{b}/analysis/populations?analysis_id={a}&provenance=REAL", {}),
            (f"[{a}] variants page", "GET", f"{b}/variants?analysis_id={a}&page_size=50", {}),
            (f"[{a}] variants sorted AF", "GET", f"{b}/variants?analysis_id={a}&page_size=50&sort=af&order=desc", {}),
            (f"[{a}] anomalies page", "GET", f"{b}/anomalies?analysis_id={a}&page_size=30", {}),
        ]
    cases += [("compare/run", "POST", f"{b}/compare/run", {"json": cmp_body}),
              ("compare/whatif", "POST", f"{b}/compare/whatif", {"json": wi_body})]
    out = []
    with httpx.Client(timeout=300) as c:
        for name, m, url, kw in cases:
            cold, code, size = timed(c, m, url, **kw)
            warm = statistics.median(timed(c, m, url, **kw)[0] for _ in range(3))
            out.append({"endpoint": name, "status": code, "cold_ms": round(cold), "warm_ms": round(warm), "bytes": size})
            print(f"{name:45s} {code}  cold {cold:8.0f} ms   warm {warm:8.0f} ms   {size/1024:8.1f} kB")
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()

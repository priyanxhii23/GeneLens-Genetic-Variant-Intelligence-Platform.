"""Module completions: synthetic options, JSON report, pathogenicity extras, population overview, TSV stages."""
import json

from app.pipeline import synthetic as syn
from tests.test_api import _run


def test_synthetic_duplicates_af_range_and_gene_label():
    p = syn.SyntheticParams(n_records=400, seed=7, duplicate_rate=0.1, gene_label="HBB", af_min=1e-4, af_max=0.01)
    recs = syn.generate(p, dict(syn.DEFAULT_MODEL), "job1")
    dups = [r for r in recs if "simulated_duplicate" in r["qc_flags"]]
    assert len(dups) == 40
    keys = [(r["pos"], r["ref"], r["alt"]) for r in recs]
    assert len(set(keys)) == 400 - 40
    assert all(r["gene_symbol"] == "SYN:HBB" and r["provenance"] == "SYNTHETIC" for r in recs)
    # AF is re-derived from sampled AC/AN, so check the sampled log-AF range loosely via the generator's clip
    afs = [r["af"] for r in recs if r["af"]]
    assert max(afs) < 0.05 and min(afs) > 1e-6
    # same seed => identical output
    assert syn.generate(p, dict(syn.DEFAULT_MODEL), "job1")[5] == recs[5]


def test_synthetic_param_validation(client):
    r = client.post("/api/synthetic/generate", json={"n_records": 10, "af_min": 0.1, "af_max": 0.01})
    assert r.status_code == 422
    r = client.post("/api/synthetic/generate", json={"n_records": 10, "duplicate_rate": 0.9})
    assert r.status_code == 422


def test_json_report_and_extras(client):
    aid = _run(client)
    rec = client.post("/api/reports/generate", json={"analysis_id": aid, "format": "json"}).json()
    body = client.get(f"/api/reports/{rec['id']}/download")
    assert body.headers["content-type"].startswith("application/json")
    data = json.loads(body.content)
    assert data["provenance"]["data"] == "REAL" and "statistics" in data["results"]
    assert all("evidence" not in f for f in data["flags"])

    ex = client.get("/api/analysis/pathogenicity", params={"analysis_id": aid}).json()
    assert ex["vus"]["n_vus"] >= 1 and "label" in ex["history"]
    pops = client.get("/api/analysis/populations", params={"analysis_id": aid}).json()
    assert pops["overview"]["variants_with_population_data"] >= 1
    assert any(g["max_af"] is not None for g in pops["groups"])

"""End-to-end API tests (external sources replaced by labelled test fixtures)."""
import time


def _run(client, gene="TESTG"):
    r = client.post("/api/analysis/run", json={"gene": gene})
    assert r.status_code == 202, r.text
    aid = r.json()["id"]
    for _ in range(50):
        s = client.get(f"/api/analysis/{aid}/status").json()
        if s["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert s["status"] == "completed", s.get("error")
    return aid


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_validation_errors(client):
    assert client.post("/api/analysis/run", json={"gene": "BAD GENE!"}).status_code == 422
    assert client.post("/api/analysis/run", json={"gene": "HBB", "dataset": "nope"}).status_code == 422
    # dbSNP is only offered with live ClinVar (E-utilities); GRCh37 + E-utilities is now supported
    assert client.post("/api/analysis/run", json={"gene": "HBB", "dataset": "dbsnp_refsnp",
                                                  "clinvar_source": "tsv"}).status_code == 422
    assert client.get("/api/analysis/doesnotexist/status").status_code == 404


def test_full_workflow(client):
    aid = _run(client)
    detail = client.get(f"/api/analysis/{aid}").json()
    assert detail["results"]["matching"]["status_counts"]["exact"] >= 1
    assert {d["source"] for d in detail["datasets"]} >= {"gnomAD", "ClinVar", "gnomAD-constraint"}

    dash = client.get("/api/dashboard", params={"analysis_id": aid}).json()
    assert dash["metrics"]["pathogenic"] > 0 and dash["metrics"]["matched"] > 0

    page = client.get("/api/variants", params={"analysis_id": aid, "page_size": 5, "sort": "af",
                                               "order": "desc"}).json()
    assert page["total"] > 5 and len(page["items"]) == 5
    afs = [i["af"] for i in page["items"] if i["af"] is not None]
    assert afs == sorted(afs, reverse=True)
    assert all(i["provenance"] == "REAL" for i in page["items"])

    filtered = client.get("/api/variants", params={"analysis_id": aid, "coarse_class": "P_LP"}).json()
    assert all(i["coarse_class"] == "P_LP" for i in filtered["items"])

    vid = page["items"][0]["id"]
    assert client.get(f"/api/variants/{vid}").json()["id"] == vid

    csv = client.get("/api/variants/export", params={"analysis_id": aid})
    assert csv.status_code == 200 and "provenance" in csv.text.splitlines()[1]

    stats = client.get("/api/analysis/statistics", params={"analysis_id": aid}).json()
    assert "tests" in stats
    stats2 = client.get("/api/analysis/statistics", params={"analysis_id": aid, "include_ambiguous": True}).json()
    assert stats2["sample"]["include_ambiguous"] is True

    assert client.get("/api/analysis/populations", params={"analysis_id": aid}).json()["groups"]
    assert client.get("/api/analysis/constraint", params={"analysis_id": aid}).json()["available"]

    an = client.post("/api/anomalies/detect", json={"analysis_id": aid, "thresholds": {"pathogenic_af": 0.0001}})
    assert an.status_code == 200
    flags = client.get("/api/anomalies", params={"analysis_id": aid}).json()
    assert flags["total"] > 0 and flags["items"][0]["explanation"]

    # synthetic data stays separate from real data
    job = client.post("/api/synthetic/generate", json={"source_analysis_id": aid, "n_records": 200,
                                                        "seed": 5, "unusual_rate": 0.1}).json()
    assert job["provenance"] == "SYNTHETIC" and job["stored_records"] == 200
    real_only = client.get("/api/variants", params={"analysis_id": aid, "page_size": 500}).json()
    assert all(i["provenance"] == "REAL" for i in real_only["items"])
    syn_only = client.get("/api/variants", params={"synthetic_job_id": job["id"], "provenance": "SYNTHETIC"}).json()
    assert syn_only["total"] == 200 and all(i["provenance"] == "SYNTHETIC" for i in syn_only["items"])
    both = client.get("/api/variants", params={"analysis_id": aid, "provenance": "ALL"}).json()
    assert both["total"] == real_only["total"] + 200
    stats_after = client.get("/api/analysis/statistics", params={"analysis_id": aid, "include_ambiguous": False}).json()
    assert stats_after["sample"]["total_rows"] == stats["sample"]["total_rows"]  # synthetic never enters real stats

    pdf = client.post("/api/reports/generate", json={"analysis_id": aid, "format": "pdf"}).json()
    dl = client.get(f"/api/reports/{pdf['id']}/download")
    assert dl.status_code == 200 and dl.content[:4] == b"%PDF"
    csvr = client.post("/api/reports/generate", json={"analysis_id": aid, "format": "csv"}).json()
    assert client.get(f"/api/reports/{csvr['id']}/download").text.startswith("analysis_id,gene,provenance")

    hist = client.get(f"/api/history/{aid}").json()
    assert len(hist["exports"]) >= 3 and hist["synthetic_jobs"]
    assert any(h["id"] == aid for h in client.get("/api/history").json())

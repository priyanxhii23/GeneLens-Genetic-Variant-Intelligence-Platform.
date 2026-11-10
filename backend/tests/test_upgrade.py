"""Tests for the data-ecosystem / provenance / comparison upgrade."""
import gzip
import struct
import time
import zlib

import pytest

from app.datasets import BY_ID, DATASETS
from app.pipeline import comparison as cmp
from app.pipeline.anomalies import CATEGORY_TEXT, detect_anomalies
from app.services.clinvar_client import to_grch37
from app.services.dbsnp_client import parse_maf, snp_summary_to_rows
from app.services.igsr_client import vcf_line_to_rows, vcf_url
from app.services.tabix import TabixIndex, bgzf_decompress_counted, reg2bins


# --------------------------------------------------------------------------- registry
def test_ten_datasets_with_distinct_types():
    assert len(DATASETS) == 10 and len(BY_ID) == 10
    types = {d.data_type for d in DATASETS}
    assert types == {"population_frequency", "clinical_annotation", "variant_catalogue"}
    assert {d.id for d in DATASETS if d.assembly == "GRCh37"} == {
        "gnomad_r2_1", "gnomad_r2_1_non_cancer", "exac", "igsr_1000g_phase3"}
    for d in DATASETS:
        assert d.name and d.provider and d.description and d.release and d.source_ids


def test_seven_sources_registered():
    from app.sources.registry import SOURCES

    assert [s.id for s in SOURCES] == ["gnomad", "clinvar_eutils", "clinvar_tsv", "ensembl", "dbsnp", "igsr", "ucsc"]


def test_unreachable_source_reported_honestly(monkeypatch, fake_clients):
    from app.sources.registry import BY_ID as SRC

    src = SRC["ucsc"]
    import httpx

    monkeypatch.setattr(type(src), "probe", lambda self: (_ for _ in ()).throw(httpx.ConnectError("[Errno -2] blocked")))
    out = src.check()
    assert out["available"] is False and out["detail"].startswith("Could not connect")
    assert "Errno" not in out["detail"]  # raw exception text is logged, never shown


# --------------------------------------------------------------------------- GRCh37 ClinVar
def test_grch37_offset_uses_clinvar_locations():
    rec = {"chrom": "11", "pos": 5227002, "ref": "T", "alt": "A", "coordinate_source": "canonical_spdi",
           "locations": {"GRCh38": {"chr": "11", "start": 5227002}, "GRCh37": {"chr": "11", "start": 5248232}}}
    out = to_grch37(rec)
    assert out["pos"] == 5248232 and out["ref"] == "T" and out["coordinate_source"] == "grch37_location_offset"


def test_grch37_without_location_is_not_guessed():
    out = to_grch37({"pos": 10, "ref": "A", "alt": "G", "locations": {"GRCh38": {"chr": "1", "start": 10}}})
    assert out["pos"] is None and out["coordinate_source"] == "no_grch37_location"


# --------------------------------------------------------------------------- dbSNP
def test_parse_maf():
    assert parse_maf("A=0.027356/137") == ("A", 0.027356, 137)
    assert parse_maf("garbage") is None


def test_dbsnp_rows_derive_an_and_keep_other_alleles_unreported():
    doc = {"snp_id": 334, "spdi": "NC_000011.10:5227001:T:A,NC_000011.10:5227001:T:C",
           "global_mafs": [{"study": "1000Genomes", "freq": "A=0.027356/137"}], "genes": [{"name": "HBB"}],
           "fxn_class": "missense_variant"}
    a, c = snp_summary_to_rows(doc)
    assert (a["pos"], a["ref"], a["alt"], a["ac"], a["an"]) == (5227002, "T", "A", 137, 5008)
    assert "an_derived_from_study_frequency" in a["qc_flags"]
    assert c["af"] is None and "frequency_not_reported_for_allele" in c["qc_flags"]


def test_dbsnp_reference_allele_frequency_converted_for_biallelic():
    doc = {"snp_id": 1, "spdi": "NC_000001.11:99:G:A", "global_mafs": [{"study": "ALFA", "freq": "G=0.9/90"}]}
    (r,) = snp_summary_to_rows(doc)
    assert r["an"] == 100 and r["ac"] == 10 and abs(r["af"] - 0.1) < 1e-9


# --------------------------------------------------------------------------- 1000 Genomes
def test_1000g_vcf_line_multiallelic_and_symbolic():
    line = ("11\t5248232\trs334\tT\tA,<DEL>\t100\tPASS\tAC=137,2;AF=0.0273562,0.0004;AN=5008;"
            "EAS_AF=0,0;AMR_AF=0.0072,0;AFR_AF=0.0998,0;EUR_AF=0,0;SAS_AF=0,0;VT=SNP\tGT\t0|0")
    rows = vcf_line_to_rows(line, {"AFR": 661, "AMR": 347, "EAS": 504, "EUR": 503, "SAS": 489}, "HBB")
    assert len(rows) == 1  # symbolic <DEL> skipped
    r = rows[0]
    assert r["ac"] == 137 and r["an"] == 5008 and abs(r["af"] - 137 / 5008) < 1e-12
    afr = next(p for p in r["populations"] if p["id"] == "afr")
    assert afr["an"] == 1322 and afr["ac"] == round(0.0998 * 1322)
    assert r["popmax_population"] == "afr"


def test_vcf_url_mapping():
    assert vcf_url("X").endswith("chrX.phase3_shapeit2_mvncall_integrated_v1c.20130502.genotypes.vcf.gz")
    assert "chr11.phase3_shapeit2_mvncall_integrated_v5b" in vcf_url("11")


# --------------------------------------------------------------------------- tabix / BGZF
def _bgzf(data: bytes) -> bytes:
    c = zlib.compressobj(6, zlib.DEFLATED, 31)
    return c.compress(data) + c.flush()


def test_bgzf_partial_trailing_block_not_consumed():
    a, b = _bgzf(b"line1\n"), _bgzf(b"line2\n")
    data, used = bgzf_decompress_counted(a + b[:5])
    assert data == b"line1\n" and used == len(a)
    data, used = bgzf_decompress_counted(a + b)
    assert data == b"line1\nline2\n" and used == len(a) + len(b)


def test_reg2bins_contains_level0_and_leaf():
    bins = reg2bins(0, 100)
    assert 0 in bins and 4681 in bins


def test_tabix_linear_index_falls_back_over_empty_windows():
    name = b"11\x00"
    header = b"TBI\x01" + struct.pack("<8i", 1, 2, 1, 2, 2, 35, 0, len(name)) + name
    body = struct.pack("<i", 0) + struct.pack("<i", 3) + struct.pack("<3Q", 100 << 16, 0, 300 << 16)
    idx = TabixIndex(gzip.compress(header + body))
    assert idx.names == ["11"]
    assert idx.start_offset("11", 1 << 14) >> 16 == 100     # empty window → previous non-zero entry
    assert idx.start_offset("11", 2 << 14) >> 16 == 300
    assert idx.start_offset("12", 0) is None


# --------------------------------------------------------------------------- explanations
def test_every_category_has_plain_language_text():
    for cat, (headline, why, rec) in CATEGORY_TEXT.items():
        assert headline and len(why) > 60 and rec, cat


def test_frequent_pathogenic_reason_names_the_crossed_threshold():
    rows = [{"vcf_key": "k", "in_gnomad": True, "in_clinvar": True, "match_status": "exact", "ac": 4, "an": 1500,
             "af": 0.0027, "popmax_af": 0.049, "popmax_population": "afr", "coarse_class": "P_LP",
             "clinical_significance": "Pathogenic", "qc_flags": []}]
    f = detect_anomalies(rows, {"use_isolation_forest": False})["flags"][0]
    assert "afr group" in f["reason"] and "population threshold" in f["reason"]
    assert "exceeds the 0.50% screening threshold" not in f["reason"]
    assert f["recommendation"] and f["why_it_matters"]


# --------------------------------------------------------------------------- comparison
def _row(**kw):
    base = {"vcf_key": "k", "in_gnomad": True, "in_clinvar": True, "match_status": "exact", "coarse_class": "P_LP",
            "clinical_significance": "Pathogenic", "gold_stars": 2, "af": 0.002, "ac": 2, "an": 1000, "qc_flags": [],
            "populations": [{"id": "afr", "ac": 2, "an": 100}, {"id": "nfe", "ac": 0, "an": 900}]}
    return {**base, **kw}


def test_effective_rows_population_af_and_star_gating():
    (e,) = cmp.effective_rows([_row()], ["afr"], 0)
    assert e["af"] == pytest.approx(0.02) and e["popmax_population"] == "afr"
    (e,) = cmp.effective_rows([_row(gold_stars=1)], None, 2)
    assert e["coarse_class"] == "BELOW_REVIEW_THRESHOLD"


def test_whatif_raising_threshold_reduces_flags():
    rows = [_row(vcf_key=f"k{i}", af=0.002 * (i + 1), popmax_af=None) for i in range(5)]  # 0.2% … 1.0%
    w = cmp.whatif(rows, {"pathogenic_af": 0.001}, {"pathogenic_af": 0.005})
    assert w["baseline"]["total"] == 5 and w["scenario"]["total"] == 3   # 0.6, 0.8, 1.0 % remain ≥ 0.5 %
    assert w["difference"] == -2 and w["percent_change"] == -40.0


# --------------------------------------------------------------------------- API
def _run(client, gene):
    aid = client.post("/api/analysis/run", json={"gene": gene}).json()["id"]
    for _ in range(50):
        if client.get(f"/api/analysis/{aid}/status").json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
    return aid


def test_provenance_modes_are_separate(client):
    aid = _run(client, "TESTG")
    client.post("/api/synthetic/generate", json={"source_analysis_id": aid, "n_records": 150, "seed": 3})
    real = client.get("/api/analysis/statistics", params={"analysis_id": aid, "provenance": "REAL"}).json()
    syn = client.get("/api/analysis/statistics", params={"analysis_id": aid, "provenance": "SYNTHETIC"}).json()
    both = client.get("/api/analysis/statistics", params={"analysis_id": aid, "provenance": "BOTH"}).json()
    assert set(real["groups"]) == {"REAL"} and set(syn["groups"]) == {"SYNTHETIC"}
    assert set(both["groups"]) == {"REAL", "SYNTHETIC"}
    assert syn["groups"]["SYNTHETIC"]["sample"]["total_rows"] == 150
    assert both["groups"]["REAL"]["sample"] == real["groups"]["REAL"]["sample"]
    d = client.get("/api/dashboard", params={"analysis_id": aid, "provenance": "BOTH"}).json()
    assert d["groups"]["SYNTHETIC"]["total_records"] == 150
    assert d["groups"]["REAL"]["total_records"] == real["groups"]["REAL"]["sample"]["total_rows"]
    for mode, expect in (("REAL", {"REAL"}), ("SYNTHETIC", {"SYNTHETIC"}), ("BOTH", {"REAL", "SYNTHETIC"})):
        items = client.get("/api/variants", params={"analysis_id": aid, "provenance": mode, "page_size": 500}).json()
        assert {i["provenance"] for i in items["items"]} == expect
    an = client.get("/api/anomalies", params={"analysis_id": aid, "provenance": "SYNTHETIC"}).json()
    assert all(i["provenance"] == "SYNTHETIC" for i in an["items"])
    real_flags = client.get("/api/anomalies", params={"analysis_id": aid}).json()
    it = real_flags["items"][0]
    assert it["provenance"] == "REAL" and it["headline"] and it["reason"] and it["recommendation"]


def test_compare_whatif_and_saved(client):
    _run(client, "TESTG")
    _run(client, "TESTH")
    p = {"genes": ["TESTG", "TESTH"], "dataset": "gnomad_r4", "af_threshold": 0.001}
    r = client.post("/api/compare/run", json=p).json()
    assert [g["status"] for g in r["genes"]] == ["ok", "ok"] and r["genes"][0]["pli"] == 0.95
    miss = client.post("/api/compare/run", json={**p, "genes": ["TESTG", "NOPE1"]}).json()
    assert miss["genes"][1]["status"] == "missing"
    assert client.post("/api/compare/run", json={**p, "genes": ["TESTG"]}).status_code == 422
    w = client.post("/api/compare/whatif", json={**p, "baseline": {"pathogenic_af": 0.001},
                                                 "scenario": {"pathogenic_af": 0.5}}).json()
    assert w["total"]["scenario"] <= w["total"]["baseline"] and "screening parameters" in w["explanation"]
    s = client.post("/api/compare/saved", json={"name": "test", "params": p, "results": r, "whatif": w}).json()
    assert any(x["id"] == s["id"] for x in client.get("/api/compare/saved").json())
    csv = client.get(f"/api/compare/saved/{s['id']}/export").text
    assert csv.startswith("# GeneLens comparison") and "TESTG" in csv
    assert client.delete(f"/api/compare/saved/{s['id']}").status_code == 204


def test_gene_suggestions_before_typing(client, monkeypatch):
    from app.services.gnomad_client import GnomadClient
    from app.services.http import ExternalServiceError

    monkeypatch.setattr(GnomadClient, "search_genes", lambda self, q, g="GRCh38": (_ for _ in ()).throw(
        ExternalServiceError("gnomAD", "offline", 503)))
    r = client.get("/api/genes/suggest").json()
    assert [g["symbol"] for g in r["results"]] == ["HBB", "CFTR", "BRCA1", "BRCA2", "TP53", "LDLR", "G6PD", "PAH"]
    assert all(g["name"] and g["description"] for g in r["results"])
    r = client.get("/api/genes/suggest", params={"q": "brc"}).json()
    assert {"BRCA1", "BRCA2"} <= {g["symbol"] for g in r["results"]}
    assert r["live_search"].startswith("unavailable")


def test_sources_endpoint_reports_stats(client, monkeypatch):
    from app.sources import registry
    from app.sources.tracking import record_retrieval

    from app.sources import status_cache

    for s in registry.SOURCES:
        monkeypatch.setattr(type(s), "probe", lambda self: {"detail": "stub", "release": "r1"})
    monkeypatch.setattr(status_cache, "fetch_gnomad_enum", lambda: {"gnomad_r4"})
    record_retrieval("ensembl", 7)
    rows = {r["id"]: r for r in client.get("/api/sources", params={"refresh": True}).json()}
    assert len(rows) == 7 and rows["ensembl"]["records_retrieved"] >= 7 and rows["ensembl"]["available"]
    assert client.post("/api/sources/ucsc/refresh").json()["release"] == "r1"
    assert client.post("/api/sources/nope/refresh").status_code == 404


def test_ensure_columns_upgrades_old_database(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    import app.database as dbmod

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE anomaly_results (id INTEGER PRIMARY KEY, analysis_id VARCHAR(16))"))
    orig = dbmod.engine
    dbmod.engine = eng
    try:
        dbmod.ensure_columns()
    finally:
        dbmod.engine = orig
    cols = {c["name"] for c in inspect(eng).get_columns("anomaly_results")}
    assert {"headline", "reason", "why_it_matters", "recommendation"} <= cols

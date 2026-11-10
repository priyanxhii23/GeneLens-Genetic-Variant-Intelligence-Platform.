"""Anomaly screening: categories, kinds, thresholds and explanations."""
from app.pipeline.anomalies import detect_anomalies
from app.pipeline.matching import match_variants
from app.pipeline.preprocessing import preprocess_clinvar, preprocess_gnomad
from tests.fixtures.sample_data import clinvar_records, gnomad_gene


def _rows():
    rows, _ = match_variants(preprocess_gnomad(gnomad_gene()), preprocess_clinvar(clinvar_records()),
                             "GRCh38", "GRCh38")
    return rows


def _row(**kw):
    base = {"vcf_key": "1-1-A-G", "in_gnomad": True, "in_clinvar": True, "match_status": "exact",
            "ac": 1, "an": 100_000, "af": 1e-5, "popmax_af": None, "coarse_class": "B_LB",
            "clinical_significance": "Benign", "qc_flags": []}
    return {**base, **kw}


def test_frequent_pathogenic_is_biological_interest_not_error():
    out = detect_anomalies([_row(coarse_class="P_LP", clinical_significance="Pathogenic", af=0.02, ac=2000)],
                           {"use_isolation_forest": False})
    f = next(f for f in out["flags"] if f["category"] == "frequent_pathogenic")
    assert f["kind"] == "biological_interest"
    assert "does not mean the variant is misclassified" in f["explanation"]
    assert f["evidence"]["af"] == 0.02


def test_threshold_is_configurable():
    r = [_row(coarse_class="P_LP", clinical_significance="Pathogenic", af=0.002, ac=200)]
    assert not any(f["category"] == "frequent_pathogenic" for f in detect_anomalies(r)["flags"])
    out = detect_anomalies(r, {"pathogenic_af": 0.001})
    assert any(f["category"] == "frequent_pathogenic" for f in out["flags"])


def test_rare_benign_and_conflicting():
    out = detect_anomalies([_row(af=1e-6), _row(vcf_key="x", coarse_class="CONFLICTING",
                                                clinical_significance="Conflicting")])
    cats = {f["category"] for f in out["flags"]}
    assert {"rare_benign", "conflicting_interpretation"} <= cats


def test_data_quality_flags():
    out = detect_anomalies(_rows(), {"use_isolation_forest": False})
    kinds = {(f["category"], f["kind"]) for f in out["flags"]}
    assert ("incomplete_frequency_record", "data_quality") in kinds   # AN = 0 fixture
    assert ("gnomad_qc_filter", "data_quality") in kinds
    assert ("ambiguous_match", "data_quality") in kinds
    assert ("conflicting_interpretation", "biological_interest") in kinds
    for f in out["flags"]:
        assert f["explanation"] and f["priority"] in {"high", "medium", "low"}


def test_count_inconsistency_detected():
    out = detect_anomalies([_row(qc_flags=["ac_exceeds_an"], ac=10, an=5)])
    f = next(f for f in out["flags"] if f["category"] == "count_inconsistency")
    assert f["kind"] == "data_quality" and f["priority"] == "high"


def test_robust_outlier():
    rows = [_row(vcf_key=f"k{i}", af=1e-5 * (1 + i % 3)) for i in range(30)] + [_row(vcf_key="out", af=0.3)]
    out = detect_anomalies(rows, {"use_isolation_forest": False})
    assert any(f["variant_key"] == "out" and f["category"] == "frequency_outlier_within_class" for f in out["flags"])


def test_isolation_forest_is_reproducible():
    rows = [_row(vcf_key=f"k{i}", af=10 ** (-6 + (i % 40) / 10), an=100_000 + i) for i in range(120)]
    a = detect_anomalies(rows, {"seed": 7})
    b = detect_anomalies(rows, {"seed": 7})
    assert [f["variant_key"] for f in a["flags"]] == [f["variant_key"] for f in b["flags"]]

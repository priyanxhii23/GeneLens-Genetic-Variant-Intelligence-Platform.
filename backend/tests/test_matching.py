"""Variant normalisation and gnomAD↔ClinVar matching."""
import pytest

from app.pipeline.matching import AssemblyMismatchError, match_variants
from app.pipeline.normalization import minimal_representation, normalize_record, variant_type
from app.pipeline.preprocessing import preprocess_clinvar, preprocess_gnomad
from app.services.clinvar_client import spdi_to_vcf
from tests.fixtures.sample_data import clinvar_records, gnomad_gene


@pytest.fixture
def matched():
    rows, summary = match_variants(preprocess_gnomad(gnomad_gene()), preprocess_clinvar(clinvar_records()),
                                   "GRCh38", "GRCh38")
    return {r["vcf_key"]: r for r in rows if r.get("in_gnomad")}, rows, summary


def test_spdi_conversion():
    assert spdi_to_vcf("NC_000017.11:43045766:G:A") == ("17", 43045767, "G", "A")
    assert spdi_to_vcf("NC_000023.11:10:A:T")[0] == "X"
    assert spdi_to_vcf("NC_000001.11:200:TT:T") == ("1", 201, "TT", "T")
    assert spdi_to_vcf("garbage") is None


def test_minimal_representation():
    assert minimal_representation(100, "A", "G") == (99, "A", "G")
    assert minimal_representation(200, "CT", "C") == (200, "T", "")
    assert minimal_representation(201, "TT", "T") == (200, "T", "")
    assert minimal_representation(10, "A", "AGG") == (10, "", "GG")


def test_variant_type():
    assert variant_type("A", "G") == "SNV"
    assert variant_type("AC", "GT") == "MNV"
    assert variant_type("CT", "C") == "deletion"
    assert variant_type("C", "CAA") == "insertion"
    assert variant_type("ACG", "TT") == "complex"


def test_normalize_record_rejects_bad_input():
    assert normalize_record({"chrom": "chr1", "pos": 5, "ref": "a", "alt": "g"})["vcf_key"] == "1-5-A-G"
    assert not normalize_record({"chrom": "1", "pos": 5, "ref": "A", "alt": "A"})["coords_valid"]
    assert not normalize_record({"chrom": "1", "pos": 5, "ref": "A", "alt": "<DEL>"})["coords_valid"]
    assert not normalize_record({"chrom": "chrUn", "pos": 5, "ref": "A", "alt": "G"})["coords_valid"]


def test_exact_match(matched):
    by_key, _, _ = matched
    r = by_key["1-100-A-G"]
    assert r["match_status"] == "exact" and r["match_confidence"] == 1.0
    assert r["clinvar_variation_id"] == "1"


def test_indel_matched_by_minimal_representation(matched):
    r = matched[0]["1-200-CT-C"]
    assert r["match_status"] == "normalized" and r["clinvar_variation_id"] == "2"


def test_discordant_duplicates_are_ambiguous(matched):
    r = matched[0]["1-600-A-C"]
    assert r["match_status"] == "ambiguous"
    assert "ambiguous_match" in r["qc_flags"]
    # the secondary record is kept visible, not dropped
    assert any(x["match_status"] == "secondary_clinvar" for x in matched[1])


def test_unmatched_and_unmatchable_kept_visible(matched):
    _, rows, summary = matched
    statuses = {r["match_status"] for r in rows}
    assert {"gnomad_only", "clinvar_only", "unmatchable"} <= statuses
    hap = next(r for r in rows if r.get("clinvar_variation_id") == "5")
    assert hap["match_status"] == "unmatchable"
    assert summary["clinvar_records"] == len(clinvar_records())
    assert summary["gnomad_records"] == len(gnomad_gene()["variants"])


def test_no_join_by_gene_name_only():
    g = preprocess_gnomad(gnomad_gene())
    c = preprocess_clinvar(clinvar_records())
    for r in c:  # same gene, different position
        if r["coords_valid"]:
            r["pos"] += 100_000  # same gene symbol, positions that exist nowhere in gnomAD
            r.update(normalize_record(r))
    rows, summary = match_variants(g, c, "GRCh38", "GRCh38")
    assert summary["matched_variants"] == 0


def test_assembly_mismatch_rejected():
    with pytest.raises(AssemblyMismatchError):
        match_variants([], [], "GRCh38", "GRCh37")

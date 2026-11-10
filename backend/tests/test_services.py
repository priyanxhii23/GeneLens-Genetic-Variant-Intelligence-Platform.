"""External-service clients: caching, snapshot fallback and explicit failure."""
import pytest

from app.services import gnomad_client as gc
from app.services.cache import DiskCache
from app.services.clinvar_client import ClinVarClient, parse_esummary_record, refseq_to_chrom, tsv_row_to_record
from app.services.http import ExternalServiceError
from tests.fixtures.sample_data import clinvar_raw, gnomad_gene


def test_disk_cache_roundtrip(tmp_path):
    c = DiskCache("t", root=tmp_path)
    k = DiskCache.key("a", {"b": 1})
    assert c.get(k) is None
    c.set(k, {"x": 1}, {"retrieved_at": "now"})
    assert c.get(k)["payload"] == {"x": 1}


def test_gnomad_uses_labelled_snapshot_when_api_down(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "snapshot_path", lambda s, src, d: tmp_path / f"{s}_{src}_{d}.json.gz")
    gc.save_snapshot("TESTG", "gnomad", "gnomad_r4", {"gene": gnomad_gene()}, {"retrieved_at": "2026-01-01"})
    client = gc.GnomadClient(cache=DiskCache("g", root=tmp_path))

    def down(*a, **k):
        raise ExternalServiceError("gnomAD", "unavailable", 503)

    monkeypatch.setattr(client, "_post", down)
    gene, meta = client.fetch_gene_variants("TESTG", "gnomad_r4")
    assert meta["access_mode"] == "offline_snapshot"
    assert meta["retrieved_at"] == "2026-01-01"  # original date preserved
    assert len(gene["variants"]) == len(gnomad_gene()["variants"])


def test_gnomad_fails_explicitly_without_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "snapshot_path", lambda s, src, d: tmp_path / "missing.json.gz")
    client = gc.GnomadClient(cache=DiskCache("g2", root=tmp_path))
    monkeypatch.setattr(client, "_post", lambda *a, **k: (_ for _ in ()).throw(ExternalServiceError("gnomAD", "down", 503)))
    with pytest.raises(ExternalServiceError):
        client.fetch_gene_variants("NOPE", "gnomad_r4")


def test_unsupported_dataset_rejected():
    with pytest.raises(ValueError):
        gc.GnomadClient().fetch_gene_variants("HBB", "not_a_dataset")


def test_esummary_parsing_dedupes_and_converts():
    rec = parse_esummary_record(clinvar_raw()[0])
    assert (rec["chrom"], rec["pos"], rec["ref"], rec["alt"]) == ("1", 100, "A", "G")
    assert rec["coordinate_source"] == "canonical_spdi" and rec["conditions"] == "Test condition"


def test_refseq_mapping():
    assert refseq_to_chrom("NC_000011.10") == "11"
    assert refseq_to_chrom("NC_000024.10") == "Y"
    assert refseq_to_chrom("NT_187361.1") is None


def test_tsv_row_mapping_and_tsv_filtering(tmp_path):
    import gzip
    header = ["AlleleID", "Type", "Name", "GeneSymbol", "ClinicalSignificance", "LastEvaluated", "RS# (dbSNP)",
              "PhenotypeList", "Assembly", "Chromosome", "ReviewStatus", "NumberSubmitters", "VariationID",
              "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF", "Extra"]
    rows = [["1", "single nucleotide variant", "x", "TESTG", "Pathogenic", "-", "334", "cond", "GRCh38", "1",
             "reviewed by expert panel", "3", "10", "100", "A", "G", "z"],
            ["1", "single nucleotide variant", "x", "TESTG", "Pathogenic", "-", "334", "cond", "GRCh37", "1",
             "reviewed by expert panel", "3", "10", "90", "A", "G", "z"],
            ["2", "Deletion", "y", "OTHER;TESTG2", "Benign", "-", "-1", "-", "GRCh38", "1", "single", "1", "11",
             "-1", "na", "na", "z"]]
    p = tmp_path / "vs.txt.gz"
    with gzip.open(p, "wt") as fh:
        fh.write("\t".join(header) + "\n" + "\n".join("\t".join(r) for r in rows) + "\n")
    recs, meta = ClinVarClient().fetch_gene_tsv("TESTG", "GRCh38", tsv_path=p)
    assert len(recs) == 1 and recs[0]["pos"] == 100 and recs[0]["rsid"] == "rs334"
    assert meta["access_mode"] == "local_tsv"
    r = tsv_row_to_record(dict(zip(header, rows[2])))
    assert r["pos"] is None and r["rsid"] is None and r["coordinate_source"] == "missing"

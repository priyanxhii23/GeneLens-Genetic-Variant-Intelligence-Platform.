"""Custom Dataset Lab: formats, inspection, mapping, assembly handling, separation and processing."""
from __future__ import annotations

import gzip
import json

import pytest

from tests.conftest import FakeClinVar

CSV = (b"Chromosome,Position,Ref,Alt,Gene,AC,AN,AF_nfe,AF_afr,ClinicalSignificance\n"
       b"1,100,A,G,TESTG,40,1000,0.05,0.002,Pathogenic\n"
       b"1,100,A,G,TESTG,40,1000,0.05,0.002,Pathogenic\n"
       b"1,400,C,T,TESTG,1,2000,,0.001,Benign\n"
       b"1,500,C,C,TESTG,1,2000,,,Uncertain significance\n"
       b"1,800,G,C,TESTG,5,,0.01,,Likely benign\n")
VCF = (b"##fileformat=VCFv4.2\n##reference=GRCh38\n"
       b'##INFO=<ID=AC,Number=A,Type=Integer,Description="x">\n##INFO=<ID=AN,Number=1,Type=Integer,Description="x">\n'
       b'##INFO=<ID=GENEINFO,Number=1,Type=String,Description="x">\n'
       b"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n"
       b"1\t100\trs1\tA\tG,T\t.\tPASS\tAC=3,1;AN=100;GENEINFO=TESTG\n"
       b"1\t400\t.\tC\tT\t.\tPASS\tAC=0;AN=100\n")


@pytest.fixture
def cv(monkeypatch):
    import app.services.clinvar_client as mod

    monkeypatch.setattr(mod, "ClinVarClient", FakeClinVar)


def upload(client, name, data):
    return client.post("/api/custom-datasets", files={"file": (name, data, "application/octet-stream")})


def process(client, ds_id):
    assert client.post(f"/api/custom-datasets/{ds_id}/process").status_code == 202
    return client.get(f"/api/custom-datasets/{ds_id}").json()


def test_csv_inspection_mapping_and_preview(client):
    d = upload(client, "my.csv", CSV).json()
    assert d["file_format"] == "csv" and d["provenance"] == "CUSTOM"
    m = d["mapping"]
    assert (m["chrom"], m["pos"], m["ref"], m["alt"], m["ac"], m["an"]) == ("Chromosome", "Position", "Ref", "Alt", "AC", "AN")
    assert m["clinical_significance"] == "ClinicalSignificance"
    assert d["inspection"]["population_columns"] == {"nfe": {"af": "AF_nfe"}, "afr": {"af": "AF_afr"}}
    assert d["inspection"]["row_count"] == 5 and len(d["inspection"]["preview"]) == 5
    assert d["inspection"]["missing_by_column"]["AN"] == 1


def test_assembly_is_never_guessed(client):
    d = upload(client, "my.csv", CSV).json()
    assert d["assembly"] == "unknown" and d["assembly_source"] is None
    v = upload(client, "my.vcf", VCF).json()
    assert v["assembly"] == "GRCh38" and v["assembly_source"] == "file_header"


def test_processing_counts_duplicates_invalid_and_missing(client, cv):
    d = upload(client, "my.csv", CSV).json()
    client.patch(f"/api/custom-datasets/{d['id']}", json={"assembly": "GRCh38", "clinvar": False})
    s = process(client, d["id"])
    assert s["status"] == "completed", s["error"]
    t = s["summary"]["totals"]
    assert (t["rows"], t["valid"], t["invalid"], t["duplicates"], t["unique_valid"]) == (5, 4, 1, 1, 3)
    # AF needs AC and AN: the record without AN has no AF (missing, never 0)
    assert s["summary"]["af_distribution"]["af_missing"] == 1
    assert s["summary"]["field_status"]["classification"] == "from uploaded file"
    assert s["summary"]["clinvar"]["status"] == "skipped"
    for f in s["summary"]["anomalies"]:
        assert "in ClinVar" not in f["reason"] and "evidence" not in f


def test_clinvar_unavailable_without_assembly(client, cv):
    d = upload(client, "my.csv", CSV).json()
    s = process(client, d["id"])
    assert s["summary"]["clinvar"]["status"] == "unavailable"
    assert "assembly is unknown" in s["summary"]["clinvar"]["reason"]


def test_vcf_multiallelic_and_clinvar_annotation(client, cv):
    d = upload(client, "my.vcf", VCF).json()
    assert d["inspection"]["row_count"] == 3  # G and T split into two allele records
    s = process(client, d["id"])
    cvm = s["summary"]["clinvar"]
    assert cvm["mode"] == "annotation" and cvm["matched_exact"] == 2  # 1-100-A-G and 1-400-C-T
    assert s["summary"]["field_status"]["classification"] == "retrieved from ClinVar (exact allele matches)"
    items = client.get(f"/api/variants?custom_dataset_id={d['id']}&page_size=50").json()["items"]
    by_key = {i["variant_key"]: i for i in items}
    assert by_key["1-100-A-G"]["coarse_class"] == "P_LP"
    assert by_key["1-100-A-T"]["coarse_class"] == "NOT_IN_CLINVAR"  # different allele – never matched by position
    assert by_key["1-400-C-T"]["af"] == 0  # AC=0 with AN=100 is a real zero


def test_own_classification_is_never_overwritten(client, cv):
    d = upload(client, "my.csv", CSV).json()
    client.patch(f"/api/custom-datasets/{d['id']}", json={"assembly": "GRCh38"})
    s = process(client, d["id"])
    assert s["summary"]["clinvar"]["mode"] == "concordance"
    items = client.get(f"/api/variants?custom_dataset_id={d['id']}&page_size=50").json()["items"]
    benign = next(i for i in items if i["variant_key"] == "1-400-C-T")
    assert benign["clinical_significance"] == "Benign"


def test_vcf_gz_tsv_and_json(client):
    assert upload(client, "a.vcf.gz", gzip.compress(VCF)).json()["file_format"] == "vcf.gz"
    tsv = CSV.replace(b",", b"\t")
    assert upload(client, "a.tsv", tsv).json()["mapping"]["chrom"] == "Chromosome"
    js = json.dumps({"variants": [{"variant_id": "1-100-A-G", "af": 0.1}, {"variant_id": "1-400-C-T", "af": 0.2}]})
    d = upload(client, "a.json", js.encode()).json()
    assert d["file_format"] == "json" and d["mapping"]["variant_id"] == "variant_id"
    s = process(client, d["id"])
    assert s["summary"]["totals"]["valid"] == 2
    assert s["summary"]["field_status"]["allele_frequency"] == "reported in file"


@pytest.mark.parametrize("name,data,msg", [
    ("x.exe", b"MZ\x00", "Unsupported file type"),
    ("x.vcf", b"chrom,pos\n1,2\n", "##fileformat=VCF"),
    ("x.vcf.gz", b"not gzip", "not gzip"),
    ("x.json", b"{\"a\": 1}", "list of variant records"),
    ("x.csv", b"", "empty"),
])
def test_invalid_files_rejected_with_clear_message(client, name, data, msg):
    r = upload(client, name, data)
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_mapping_validation_and_missing_coordinates(client):
    d = upload(client, "my.csv", CSV).json()
    r = client.patch(f"/api/custom-datasets/{d['id']}", json={"mapping": {"chrom": "Nope"}})
    assert r.status_code == 422
    r = client.patch(f"/api/custom-datasets/{d['id']}", json={"mapping": {"chrom": "Gene", "pos": "Gene"}})
    assert r.status_code == 422 and "only one field" in r.json()["detail"]
    client.patch(f"/api/custom-datasets/{d['id']}", json={"mapping": {"gene": "Gene"}})
    s = process(client, d["id"])
    assert s["status"] == "failed" and "Map the chromosome" in s["error"]


def test_custom_data_is_separate_and_deleted(client, cv):
    d = upload(client, "my.csv", CSV).json()
    process(client, d["id"])
    from app.database import SessionLocal
    from app.models import Variant

    with SessionLocal() as db:
        rows = db.query(Variant).filter(Variant.custom_dataset_id == d["id"]).all()
        assert rows and all(r.provenance == "CUSTOM" and r.analysis_id is None for r in rows)
    assert client.get(f"/api/custom-datasets/{d['id']}/cleaned.csv").text.startswith("# GeneLens cleaned export of CUSTOM")
    exp = client.get(f"/api/custom-datasets/{d['id']}/export?format=json").json()
    assert exp["metadata"]["provenance"] == "CUSTOM"
    assert client.delete(f"/api/custom-datasets/{d['id']}").status_code == 204
    with SessionLocal() as db:
        assert db.query(Variant).filter(Variant.custom_dataset_id == d["id"]).count() == 0

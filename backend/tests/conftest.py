"""Shared fixtures. A temporary data directory is configured BEFORE the app is imported."""
from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="genelens_test_")
os.environ["GENELENS_DATA_DIR"] = _TMP

import pytest  # noqa: E402

from tests.fixtures.sample_data import clinvar_records, gnomad_gene  # noqa: E402


class FakeGnomad:
    def fetch_gene_variants(self, symbol, dataset):
        return gnomad_gene(), {"retrieved_at": "2026-01-01T00:00:00+00:00", "access_mode": "test_fixture",
                               "dataset": dataset, "dataset_label": "TEST FIXTURE", "query": "fixture"}

    def search_genes(self, q, genome="GRCh38"):
        return [{"ensembl_id": "ENSGTEST", "symbol": "TESTG"}]


class FakeClinVar:
    def fetch_gene_eutils(self, symbol, progress=None):
        return clinvar_records(), {"retrieved_at": "2026-01-01T00:00:00+00:00", "access_mode": "test_fixture",
                                   "dataset": "clinvar_fixture", "release": "TEST FIXTURE", "query": "fixture"}


@pytest.fixture
def fake_clients(monkeypatch):
    import app.pipeline.runner as runner

    monkeypatch.setattr(runner, "GnomadClient", FakeGnomad)
    monkeypatch.setattr(runner, "ClinVarClient", FakeClinVar)
    # gene annotation calls Ensembl/UCSC; tests must stay offline
    monkeypatch.setattr(runner, "_annotate_gene", lambda *a, **k: {"sources": {}, "test_fixture": True})
    return FakeGnomad(), FakeClinVar()


@pytest.fixture
def client(fake_clients):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c

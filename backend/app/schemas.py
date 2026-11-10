"""Pydantic request/response models (validated automatically by FastAPI)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.datasets import BY_ID as DATASET_BY_ID


class AnomalyThresholdsIn(BaseModel):
    pathogenic_af: float = Field(0.005, gt=0, le=1)
    pathogenic_popmax_af: float = Field(0.01, gt=0, le=1)
    ba1_af: float = Field(0.05, gt=0, le=1)
    rare_benign_af: float = Field(1e-5, gt=0, le=1)
    low_an_fraction: float = Field(0.5, gt=0, le=1)
    mad_z: float = Field(3.5, gt=0, le=20)
    use_isolation_forest: bool = True
    isolation_contamination: float = Field(0.02, gt=0, le=0.5)
    seed: int = 42


class AnalysisRunRequest(BaseModel):
    gene: str = Field(..., min_length=1, max_length=32, examples=["HBB"])
    dataset: str = Field("gnomad_r4", examples=["gnomad_r4"])
    clinvar_source: Literal["eutils", "tsv"] = "eutils"
    include_ambiguous: bool = False
    seed: int = 0
    anomaly_thresholds: AnomalyThresholdsIn | None = None

    @field_validator("gene")
    @classmethod
    def _gene(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.replace("-", "").replace(".", "").isalnum():
            raise ValueError("gene symbol may contain only letters, digits, '-' and '.'")
        return v

    @field_validator("dataset")
    @classmethod
    def _dataset(cls, v: str) -> str:
        if v not in DATASET_BY_ID:
            raise ValueError(f"dataset must be one of {sorted(DATASET_BY_ID)}")
        return v


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    gene_symbol: str
    dataset: str
    reference_genome: str
    clinvar_source: str
    status: str
    stage: str | None
    progress: float
    error: str | None
    real_count: int
    synthetic_count: int
    parameters: dict
    created_at: datetime
    completed_at: datetime | None


class DatasetMetaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    dataset: str
    release: str | None
    reference_genome: str | None
    access_mode: str
    query: str | None
    record_count: int
    retrieved_at: datetime
    notes: str | None


class AnomalyDetectRequest(BaseModel):
    analysis_id: str
    thresholds: AnomalyThresholdsIn = AnomalyThresholdsIn()


class SyntheticRequest(BaseModel):
    source_analysis_id: str | None = None
    n_records: int = Field(1000, ge=1, le=100_000)
    seed: int = 42
    class_distribution: dict[str, float] | None = None
    missing_rate: float = Field(0.0, ge=0, le=0.5)
    conflicting_rate: float = Field(0.0, ge=0, le=0.5)
    unusual_rate: float = Field(0.0, ge=0, le=0.5)
    duplicate_rate: float = Field(0.0, ge=0, le=0.5)
    gene_label: str | None = Field(None, max_length=20, pattern=r"^[A-Za-z0-9\-_.]*$")
    af_min: float | None = Field(None, gt=0, le=1)
    af_max: float | None = Field(None, gt=0, le=1)
    populations: list[str] = Field(default_factory=lambda: ["afr", "amr", "asj", "eas", "fin", "mid", "nfe",
                                                            "sas", "remaining"])


class ReportRequest(BaseModel):
    analysis_id: str
    format: Literal["pdf", "csv", "json"] = "pdf"


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_id: str | None
    synthetic_job_id: str | None
    kind: str
    filename: str
    size_bytes: int
    parameters: dict | None
    created_at: datetime

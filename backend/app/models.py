"""SQLAlchemy ORM models.

Every variant row carries a permanent ``provenance`` column (REAL or
SYNTHETIC) and every dataset is linked to a ``DatasetMetadata`` row that
records source, release and retrieval date.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Gene(Base):
    __tablename__ = "genes"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    reference_genome: Mapped[str] = mapped_column(String(16))
    ensembl_id: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(256))
    chrom: Mapped[str | None] = mapped_column(String(8))
    start: Mapped[int | None] = mapped_column(Integer)
    stop: Mapped[int | None] = mapped_column(Integer)
    canonical_transcript_id: Mapped[str | None] = mapped_column(String(32))
    mane_select_transcript: Mapped[str | None] = mapped_column(String(64))
    constraint: Mapped[dict | None] = mapped_column(JSON)
    constraint_source: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DatasetMetadata(Base):
    __tablename__ = "dataset_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(32))  # gnomAD | ClinVar | gnomAD-constraint | Synthetic
    dataset: Mapped[str] = mapped_column(String(64))  # e.g. gnomad_r4, variant_summary, esummary
    release: Mapped[str | None] = mapped_column(String(64))
    reference_genome: Mapped[str | None] = mapped_column(String(16))
    access_mode: Mapped[str] = mapped_column(String(32))  # live_api | cache | offline_snapshot | local_tsv | generated
    query: Mapped[str | None] = mapped_column(Text)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str | None] = mapped_column(Text)


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    gene_symbol: Mapped[str] = mapped_column(String(32), index=True)
    dataset: Mapped[str] = mapped_column(String(64))
    reference_genome: Mapped[str] = mapped_column(String(16))
    clinvar_source: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|completed|failed
    stage: Mapped[str | None] = mapped_column(String(64))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    real_count: Mapped[int] = mapped_column(Integer, default=0)
    synthetic_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    datasets: Mapped[list[DatasetMetadata]] = relationship(cascade="all, delete-orphan")


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        Index("ix_variant_analysis_class", "analysis_id", "coarse_class"),
        Index("ix_variant_analysis_key", "analysis_id", "variant_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True)
    synthetic_job_id: Mapped[str | None] = mapped_column(ForeignKey("synthetic_jobs.id", ondelete="CASCADE"), index=True)
    provenance: Mapped[str] = mapped_column(String(10), index=True)  # REAL | SYNTHETIC
    variant_key: Mapped[str] = mapped_column(String(512))  # chrom-pos-ref-alt or SYN-xxxx
    minimal_key: Mapped[str | None] = mapped_column(String(512))
    gene_symbol: Mapped[str | None] = mapped_column(String(32))
    chrom: Mapped[str | None] = mapped_column(String(8))
    pos: Mapped[int | None] = mapped_column(Integer)
    ref: Mapped[str | None] = mapped_column(Text)
    alt: Mapped[str | None] = mapped_column(Text)
    variant_type: Mapped[str | None] = mapped_column(String(16))
    rsid: Mapped[str | None] = mapped_column(String(32))
    consequence: Mapped[str | None] = mapped_column(String(64))
    hgvsc: Mapped[str | None] = mapped_column(String(256))
    hgvsp: Mapped[str | None] = mapped_column(String(256))
    # gnomAD
    in_gnomad: Mapped[bool] = mapped_column(Boolean, default=False)
    ac: Mapped[int | None] = mapped_column(Integer)
    an: Mapped[int | None] = mapped_column(Integer)
    af: Mapped[float | None] = mapped_column(Float)
    af_exome: Mapped[float | None] = mapped_column(Float)
    af_genome: Mapped[float | None] = mapped_column(Float)
    popmax_af: Mapped[float | None] = mapped_column(Float)
    popmax_population: Mapped[str | None] = mapped_column(String(16))
    homozygote_count: Mapped[int | None] = mapped_column(Integer)
    populations: Mapped[list | None] = mapped_column(JSON)
    gnomad_filters: Mapped[list | None] = mapped_column(JSON)
    gnomad_flags: Mapped[list | None] = mapped_column(JSON)
    # ClinVar
    in_clinvar: Mapped[bool] = mapped_column(Boolean, default=False)
    clinvar_variation_id: Mapped[str | None] = mapped_column(String(32))
    clinvar_allele_id: Mapped[str | None] = mapped_column(String(32))
    clinical_significance: Mapped[str | None] = mapped_column(String(256))
    classification: Mapped[str | None] = mapped_column(String(48))
    coarse_class: Mapped[str] = mapped_column(String(16), default="NOT_IN_CLINVAR")
    review_status: Mapped[str | None] = mapped_column(String(128))
    gold_stars: Mapped[int | None] = mapped_column(Integer)
    conditions: Mapped[str | None] = mapped_column(Text)
    submitter_count: Mapped[int | None] = mapped_column(Integer)
    last_evaluated: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(Text)  # ClinVar preferred name (HGVS)
    clinvar_type: Mapped[str | None] = mapped_column(String(64))
    # Matching
    match_status: Mapped[str] = mapped_column(String(24))  # exact|normalized|ambiguous|gnomad_only|clinvar_only|synthetic
    match_method: Mapped[str | None] = mapped_column(String(64))
    match_confidence: Mapped[float | None] = mapped_column(Float)
    qc_flags: Mapped[list | None] = mapped_column(JSON)


class AnomalyResult(Base):
    __tablename__ = "anomaly_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(16), index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id", ondelete="CASCADE"))
    variant_key: Mapped[str] = mapped_column(String(512))
    provenance: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(48))
    kind: Mapped[str] = mapped_column(String(32))  # data_quality | biological_interest | statistical_outlier
    priority: Mapped[str] = mapped_column(String(8))  # high | medium | low
    score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyntheticJob(Base):
    __tablename__ = "synthetic_jobs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    source_analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="SET NULL"))
    n_records: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    fitted_model: Mapped[dict | None] = mapped_column(JSON)
    comparison: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExportRecord(Base):
    """Every report or CSV export is logged here (Module 10 export history)."""
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default=_uuid)
    analysis_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="CASCADE"), index=True)
    synthetic_job_id: Mapped[str | None] = mapped_column(ForeignKey("synthetic_jobs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))  # pdf_report | csv_report | variants_csv | synthetic_csv | anomalies_csv
    filename: Mapped[str] = mapped_column(String(256))
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

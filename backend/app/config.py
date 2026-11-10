"""Central configuration for GeneLens.

All settings can be overridden with environment variables prefixed with
``GENELENS_`` or via a ``.env`` file in the ``backend/`` directory.
Example: ``GENELENS_DATA_DIR=/mnt/genomics`` moves every data file.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GENELENS_", env_file=BACKEND_DIR / ".env", extra="ignore"
    )

    app_name: str = "GeneLens – Genetic Variant Intelligence Platform"
    environment: str = "development"
    log_level: str = "INFO"

    # Storage -----------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "data"
    database_url: str | None = None  # defaults to SQLite inside data_dir

    # External services ---------------------------------------------------
    gnomad_api_url: str = "https://gnomad.broadinstitute.org/api"
    gnomad_default_dataset: str = "gnomad_r4"
    reference_genome: str = "GRCh38"
    ncbi_eutils_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    clinvar_tsv_url: str = (
        "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
    )
    # Optional NCBI key raises the E-utilities limit from 3 to 10 requests/s.
    # Keep it in backend/.env – it is never sent to the browser.
    ncbi_api_key: str | None = None
    ncbi_email: str | None = None
    http_timeout_seconds: float = 60.0
    http_max_retries: int = 4
    cache_ttl_hours: int = 24 * 7

    # Frontend ----------------------------------------------------------
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Derived paths -------------------------------------------------------
    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def snapshot_dir(self) -> Path:
        return BACKEND_DIR / "data" / "snapshots"

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'genelens.db').as_posix()}"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.cache_dir, self.raw_dir, self.processed_dir,
                  self.reports_dir, self.exports_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s

"""Database engine and session management (SQLAlchemy 2.0).

SQLite is used for local development. Because all access goes through
SQLAlchemy, switching to PostgreSQL only requires setting
``GENELENS_DATABASE_URL=postgresql+psycopg://user:pass@host/db``.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_is_sqlite = _settings.sqlalchemy_url.startswith("sqlite")
engine = create_engine(
    _settings.sqlalchemy_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    future=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401 - registers tables

    Base.metadata.create_all(bind=engine)
    ensure_columns()


def ensure_columns() -> None:
    """Add columns introduced after a database was first created.

    ``create_all`` creates missing *tables* but never alters existing ones, so a
    database made by an older GeneLens version would lack new columns. Each
    missing nullable column is added with ``ALTER TABLE … ADD COLUMN`` (safe on
    SQLite and PostgreSQL). Alembic migrations in ``migrations/`` describe the
    same changes for deployments that manage the schema explicitly.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing and col.nullable:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ddl}'))

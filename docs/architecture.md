# GeneLens architecture

## Overview
GeneLens is a two-tier web application:

* **Backend** – a FastAPI service (`backend/app`) that owns all data access, the research pipeline, statistics and report generation. It is the only component that talks to gnomAD and NCBI, and the only place secrets (e.g. an NCBI API key) live.
* **Frontend** – a React + TypeScript single-page app (`frontend/src`) built with Vite. In development, Vite proxies `/api/*` to the backend, so the browser never needs CORS or a hard-coded API URL.

Large datasets never travel to the browser: the frontend asks for paginated variant pages, pre-aggregated statistics and chart-ready summaries.

## Folder structure
```
GeneLens-Genetic-Variant-Intelligence-Platform./
├── README.md · LICENSE · DEVELOPMENT_STATUS.md · .gitignore
├── .github/workflows/ci.yml          # pytest + frontend build on every push
├── .vscode/                          # interpreter, test and debug configuration
├── docs/
│   ├── architecture.md · methodology.md · data_sources.md
│   └── screenshots/
├── backend/
│   ├── requirements.txt · .env.example · pytest.ini · alembic.ini
│   ├── app/
│   │   ├── main.py                   # FastAPI app, CORS, gzip, central error handlers
│   │   ├── config.py                 # pydantic-settings (GENELENS_* env vars)
│   │   ├── database.py               # engine, session, Base (SQLite → PostgreSQL ready)
│   │   ├── models.py                 # ORM: Gene, DatasetMetadata, AnalysisSession, Variant,
│   │   │                             #      AnomalyResult, SyntheticJob, ExportRecord
│   │   ├── schemas.py                # Pydantic request/response models
│   │   ├── utils.py                  # strict-JSON sanitiser (NaN/inf → null)
│   │   ├── services/                 # external data access
│   │   │   ├── http.py               # retries, back-off, Retry-After, typed errors
│   │   │   ├── cache.py              # gzip-JSON disk cache with TTL
│   │   │   ├── gnomad_client.py      # GraphQL queries, datasets, offline snapshots
│   │   │   └── clinvar_client.py     # E-utilities, SPDI → VCF, bulk TSV streaming
│   │   ├── pipeline/                 # one module per research stage (pure functions)
│   │   │   ├── validation.py         # AF = AC/AN, count checks, record checks
│   │   │   ├── preprocessing.py      # gnomAD flattening, classification vocabulary, stars
│   │   │   ├── normalization.py      # chrom/allele cleaning, minimal representation
│   │   │   ├── matching.py           # gnomAD ↔ ClinVar matching engine
│   │   │   ├── statistics.py         # descriptives, tests, effect sizes, FDR
│   │   │   ├── anomalies.py          # rules, robust outliers, Isolation Forest
│   │   │   ├── populations.py        # population summaries and matrices
│   │   │   ├── constraint.py         # constraint interpretation + metric docs
│   │   │   ├── synthetic.py          # fit / generate / compare
│   │   │   ├── interpretation.py     # findings derived from computed values only
│   │   │   ├── reports.py            # PDF + CSV reports with charts
│   │   │   └── runner.py             # orchestrates stages, persists, reports progress
│   │   └── api/                      # routers: system, analysis, variants, anomalies,
│   │                                 #          synthetic, reports, history
│   ├── migrations/                   # Alembic environment + initial schema
│   ├── scripts/                      # run_pipeline, download_clinvar, create_snapshot,
│   │                                 # inspect_gnomad_schema
│   ├── data/snapshots/               # real HBB snapshot (offline fallback, labelled)
│   └── tests/                        # 78 pytest tests + labelled fixtures
└── frontend/
    ├── package.json · vite.config.ts · tailwind.config.js · tsconfig.json · index.html
    └── src/
        ├── main.tsx                  # routes; each module lazily loaded
        ├── index.css                 # design tokens (light/dark), components
        ├── lib/                      # api client, types, formatting, theme, analysis context
        ├── components/               # DnaHelix, Plot, Sidebar, Workspace, ui kit
        └── pages/                    # Landing + workspace/<10 modules>
```

## Request lifecycle of an analysis
1. `POST /api/analysis/run` validates the request (gene symbol, dataset, ClinVar source, genome-build compatibility), creates an `AnalysisSession` (status `queued`) and schedules `run_analysis` as a FastAPI background task. It returns **202** immediately.
2. The runner executes the stages, updating `stage` and `progress` on the session row. The UI polls `GET /api/analysis/{id}/status`.
3. Collected datasets are recorded in `DatasetMetadata` (source, dataset, release, genome build, access mode `live_api | cache | offline_snapshot | local_tsv | generated`, query, record count, retrieval date).
4. Matched rows are bulk-inserted into `variants` with `provenance = REAL`.
5. Statistics, anomaly summary, population summary, constraint interpretation and computed findings are stored as JSON on the session (`results`), so reopening an analysis is instant and reproducible. Individual flags go to `anomaly_results`.
6. Any exception marks the session `failed` with the error message (shown in the UI and history). Nothing is half-reported as success.

## Data model
| Table | Purpose | Key provenance fields |
|-------|---------|----------------------|
| `analysis_sessions` | One research run | gene, dataset, genome build, ClinVar source, parameters, status, timestamps, real/synthetic counts, results JSON |
| `dataset_metadata` | Every dataset that fed an analysis | source, release, access mode, query, record count, retrieved_at |
| `genes` | Gene annotation + constraint | Ensembl ID, coordinates, canonical/MANE transcript, constraint source |
| `variants` | REAL and SYNTHETIC records | **provenance**, match_status / method / confidence, QC flags, all gnomAD and ClinVar fields |
| `anomaly_results` | Screening flags | run_id, category, kind, priority, evidence JSON, explanation |
| `synthetic_jobs` | Generator runs | seed, parameters, fitted model (summary parameters only), comparison |
| `exports` | Reports and CSV exports | kind, filename, size, parameters, timestamp |

Real and synthetic variants share one table but are separated by both `provenance` and foreign key (`analysis_id` for REAL, `synthetic_job_id` for SYNTHETIC). Statistics load rows with `analysis_id = … AND provenance = 'REAL'`.

### PostgreSQL
Set `GENELENS_DATABASE_URL=postgresql+psycopg://…` and install `psycopg[binary]`. All queries go through SQLAlchemy and use portable column types (JSON, DateTime with time zone). For schema changes use Alembic:
```bash
alembic revision --autogenerate -m "describe change"
```
```bash
alembic upgrade head
```
A database created by the app on first start (`create_all`) can be brought under Alembic control with `alembic stamp head`.

## Frontend design system
* **Tokens** are CSS variables (RGB triplets) on `:root[data-theme]`, consumed by Tailwind (`bg-surface`, `text-muted`, `bg-plp/10`…). The theme is applied before first paint by an inline script, persisted in `localStorage`, and toggled with a smooth colour transition.
* **Classification colours** (P/LP, VUS, B/LB, conflicting) were checked with a colour-vision-deficiency palette validator on both surfaces; identity is never conveyed by colour alone (badges always carry labels; charts carry legends or direct labels).
* **Synthetic data** is always visually distinct: violet, diagonal hatching, a `SYNTHETIC` badge and dashed/patterned chart marks.
* **Charts**: one `Plot` wrapper applies theme-aware layout defaults (recessive grids, legends above the plot, monospace hover labels) and lazy-loads Plotly's cartesian bundle (~470 kB gzipped) only when a chart first renders.
* **Motion**: Framer Motion page transitions, staggered entrances, counters and layout animations; the canvas helix pauses off-screen; `prefers-reduced-motion` disables animation globally.
* **Layout**: responsive from 390 px phones (off-canvas sidebar) to wide desktops; tables scroll inside their panels instead of the page.

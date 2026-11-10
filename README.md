# GeneLens – Genetic Variant Intelligence Platform

> A research platform that integrates **population allele frequencies** (gnomAD, 1000 Genomes, dbSNP) with **ClinVar clinical classifications**, cross-checked against **Ensembl** and **UCSC** – with explainable anomaly screening, rigorous statistics, a provenance-labelled synthetic data lab, a gene comparison lab and downloadable research reports.

![GeneLens landing page](docs/screenshots/landing.png)

> ⚠️ **Research and education only.** GeneLens is not a medical device and must not be used for diagnosis, screening or clinical decision-making. Flags are prompts for expert review, never verdicts.

---

## Table of contents
**Part A – Getting started (Windows + VS Code)**
1. [Extract the ZIP](#1-extract-the-zip) · 2. [Open it in VS Code](#2-open-it-in-vs-code) · 3. [Virtual environment](#3-create-the-python-virtual-environment) · 4. [Backend dependencies](#4-install-backend-dependencies) · 5. [Frontend dependencies](#5-install-frontend-dependencies) · 6. [Environment variables](#6-configure-environment-variables-backendenv) · 7. [Database](#7-initialise-the-database) · 8. [Run the backend](#8-run-the-backend-terminal-1) · 9. [Run the frontend](#9-run-the-frontend-terminal-2) · 10. [Open the app](#10-open-the-application) · 11. [Troubleshooting](#11-troubleshooting) · 12. [Datasets](#12-configure-and-retrieve-datasets) · 13. [Tests](#13-run-the-tests)

**Part B – The project**
14. [Research problem & objectives](#14-research-problem--objectives) · 15. [Features](#15-features--twelve-modules) · 16. [Data ecosystem](#16-data-ecosystem--10-datasets-7-sources-custom-data) · 17. [Technology stack](#17-technology-stack) · 18. [Architecture](#18-architecture) · 19. [Statistical methodology](#19-statistical-methodology) · 20. [Synthetic data methodology](#20-synthetic-data-methodology) · 21. [Screenshots](#21-screenshots) · 22. [API](#22-api-documentation) · 23. [Performance](#23-performance) · 24. [Limitations](#24-limitations) · 25. [Future work](#25-future-enhancements) · 26. [References](#26-references-and-data-attribution)

---

# Part A – Getting started (Windows + VS Code)

The steps below are written for **Windows 10/11 with VS Code**; macOS/Linux differences are noted where they exist. You need:

| Tool | Version | Where to get it |
|---|---|---|
| Python | **3.11 or newer** (3.12 recommended) | python.org – during setup tick **"Add python.exe to PATH"** |
| Node.js | **18 or newer** (20 LTS recommended) | nodejs.org – default options |
| VS Code | any recent version | code.visualstudio.com |

Check the versions in a terminal (**Windows key → type `cmd` → Enter**):
```bash
python --version
```
```bash
node --version
```

> **Why two terminals?** GeneLens is two programs that run at the same time: the **backend** (Python/FastAPI, the scientific engine and database, port 8000) and the **frontend** (React/Vite, the web interface, port 5173). Each runs in its **own VS Code terminal** and both must stay open while you use the app. Closing a terminal stops that program.

## 1. Extract the ZIP
Right-click `GeneLens_Final_Complete_Project.zip` → **Extract All…** → choose a short path such as `C:\Users\<you>\GeneLens` → **Extract**. You get a folder called **`GeneLens`** containing `backend\`, `frontend\`, `docs\`, `README.md`, `DATA_SOURCES.md`, `PERFORMANCE_REPORT.md` and `DEVELOPMENT_STATUS.md`.

Avoid OneDrive-synced folders and paths with special characters – long synced paths are the most common cause of `npm install` failures on Windows.

*(Cloning with Git instead? The repository name ends with a dot, which Windows does not allow as a folder name, so clone into a folder called `GeneLens`:)*
```bash
git clone https://github.com/priyanxhii23/GeneLens-Genetic-Variant-Intelligence-Platform. GeneLens
```

## 2. Open it in VS Code
**File → Open Folder…** → select the **`GeneLens`** folder itself (not `backend` or `frontend`) → **Select Folder**. If asked *"Do you trust the authors?"* choose **Yes, I trust the authors**. Accept the popup to install the **recommended extensions** (Python, Pylance, Python Debugger, Tailwind CSS).

VS Code is pre-configured (`.vscode\`):
* **Terminal → Run Task… → Setup: install everything (first time)** performs steps 3–5 for you.
* **Ctrl+Shift+B** → *GeneLens: start everything* (backend + frontend in two terminal tabs – steps 8 and 9).
* **Run and Debug** (Ctrl+Shift+D) → *GeneLens API (debug)* to set breakpoints in backend code.
* **Testing** (beaker icon) → run the backend test suite.

The manual steps follow; they are what those tasks do.

## 3. Create the Python virtual environment
Open the first terminal: **Terminal → New Terminal** (it opens in the `GeneLens` folder). Then:
```bash
cd backend
```
```bash
python -m venv .venv
```
Activate it – **Windows PowerShell** (VS Code's default terminal on Windows):
```bash
.venv\Scripts\Activate.ps1
```
Windows Command Prompt instead:
```bash
.venv\Scripts\activate.bat
```
macOS / Linux:
```bash
source .venv/bin/activate
```
Your prompt now starts with `(.venv)`. If PowerShell says *running scripts is disabled on this system*, run this once, answer `Y`, then activate again:
```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Tell VS Code to use this interpreter: **Ctrl+Shift+P → "Python: Select Interpreter" → `.\backend\.venv\Scripts\python.exe`**.

## 4. Install backend dependencies
Still in terminal 1, inside `backend`, with `(.venv)` showing:
```bash
pip install -r requirements.txt
```
This takes a few minutes (pandas, SciPy, scikit-learn, Matplotlib…) and ends with `Successfully installed …`.

## 5. Install frontend dependencies
Open a **second terminal** with the **`+`** button in the terminal panel (it starts in the `GeneLens` folder):
```bash
cd frontend
```
```bash
npm install
```
Takes 1–3 minutes. Yellow `npm warn` lines are normal.

## 6. Configure environment variables (`backend\.env`)
GeneLens runs **without any configuration** – there are no mandatory variables. To customise, copy the template (in the `GeneLens` folder; Windows):
```bash
copy backend\.env.example backend\.env
```
macOS / Linux:
```bash
cp backend/.env.example backend/.env
```
Then edit `backend\.env` in VS Code and remove the `#` in front of the lines you want.

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| *(none)* | **Mandatory: none** | – | Every setting has a safe default |
| `GENELENS_NCBI_API_KEY` | Optional (recommended) | none | Raises NCBI's limit from 3 to 10 requests/s – faster ClinVar and dbSNP. Free at ncbi.nlm.nih.gov/account/settings |
| `GENELENS_NCBI_EMAIL` | Optional | none | Contact e-mail NCBI asks API users to send |
| `GENELENS_DATA_DIR` | Optional | `backend\data` | Where the database, caches, uploads, downloads and reports are stored |
| `GENELENS_DATABASE_URL` | Optional | SQLite file in the data dir | PostgreSQL instead (`postgresql+psycopg://user:pass@host:5432/genelens`, then `pip install "psycopg[binary]"`) |
| `GENELENS_GNOMAD_DEFAULT_DATASET` | Optional | `gnomad_r4` | Default dataset |
| `GENELENS_HTTP_TIMEOUT_SECONDS` | Optional | `60` | Timeout for external API calls |
| `GENELENS_CACHE_TTL_HOURS` | Optional | `168` | How long API responses are cached (7 days) |
| `GENELENS_LOG_LEVEL` | Optional | `INFO` | `DEBUG` for more detail in terminal 1 |

`backend\.env` is git-ignored and read **only by the backend**; nothing in it is ever sent to the browser. `frontend\.env` is optional and only holds `VITE_API_TARGET` if the backend runs on a port other than 8000 (see Troubleshooting).

## 7. Initialise the database
**Nothing to do for a normal start:** on its first start the backend creates `backend\data\genelens.db` (SQLite) with all tables and indexes, and on later starts it adds any new columns/tables/indexes automatically, so an older database keeps working after an upgrade.

Optional – manage the schema explicitly with Alembic migrations (terminal 1, inside `backend`, venv active). Useful for PostgreSQL or to verify the schema:
```bash
alembic upgrade head
```
Check that the database matches the code (prints *No new upgrade operations detected*):
```bash
alembic check
```

## 8. Run the backend (terminal 1)
Inside `backend`, with `(.venv)` active:
```bash
uvicorn app.main:app --reload --port 8000
```
Ready when it prints `Application startup complete.` (the first start takes 10–20 s while scientific libraries load; it then checks the seven data sources in the background). Leave this terminal running. Visiting `http://localhost:8000/` shows `404 Not Found` – that is expected; the API lives under `/api` and its interactive documentation at **http://localhost:8000/docs**.

## 9. Run the frontend (terminal 2)
Inside `frontend`:
```bash
npm run dev
```
Ready when it prints `Local: http://localhost:5173/`. Leave this terminal running too.

## 10. Open the application
Open **http://localhost:5173** in your browser → **Enter Research Workspace**. Click the gene search box – eight suggested genes appear immediately – choose **HBB**, keep the dataset **gnomAD v4 – Exomes + Genomes**, and press **Run research pipeline**. The first HBB run takes about 15–40 s (ClinVar is rate-limited); repeats take seconds from cache.

Then explore the modules in the left sidebar; use the **Real · Synthetic · Both** switch at the top to change which records every module displays, and the **Custom Dataset Lab** to upload your own variant file (CSV, TSV, TXT, VCF, VCF.GZ or JSON).

To stop GeneLens press **Ctrl+C** in each terminal. Next time you only need steps 8 and 9 (activate the venv first in terminal 1), or simply **Ctrl+Shift+B**.

## 11. Troubleshooting
| Symptom | Cause / fix |
|---|---|
| **Port already in use** – `[Errno 10048]` / `address already in use` on 8000, or Vite picks 5174 | Another program (often an old GeneLens terminal) uses the port. Close the old terminal, or find the process: `netstat -ano \| findstr :8000` then `taskkill /PID <pid> /F`. Alternatively run `uvicorn app.main:app --reload --port 8001` and create `frontend\.env` containing `VITE_API_TARGET=http://127.0.0.1:8001`, then restart `npm run dev`. |
| **Dependency installation fails** (`pip install`) | Make sure `(.venv)` is active and Python ≥ 3.11 (`python --version`). Upgrade pip with `python -m pip install --upgrade pip` and retry. "Microsoft Visual C++ 14.0 is required" means your Python is too new/old for the pinned wheels – install Python 3.12. |
| **Dependency installation fails** (`npm install`) | Use Node 18/20 (`node --version`). Delete `frontend\node_modules` and `frontend\package-lock.json` only if `npm install` keeps failing, then retry. Move the project out of OneDrive if you see `EPERM`/`EBUSY`. |
| `'uvicorn' / 'pip' is not recognized` | Activate the virtual environment first (step 3). |
| `ModuleNotFoundError: No module named 'app'` | Run uvicorn from inside `backend`. |
| PowerShell refuses `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y`. |
| `python` / `npm` not recognized | Install Python / Node.js (top of Part A), then open a **new** terminal (or restart VS Code). |
| **Database connection failure** (`database: error` at `/api/health`, `unable to open database file`, `OperationalError`) | The data folder is not writable or `GENELENS_DATA_DIR` points to a missing drive – fix or remove that line in `backend\.env`. For PostgreSQL check `GENELENS_DATABASE_URL`, that the server is running and that `psycopg[binary]` is installed. To start from a clean SQLite database stop the backend and delete `backend\data\genelens.db`. |
| **API timeout** (an analysis or a source shows *No response within 10 seconds*) | A public API is slow or your network blocks it. Open **Source Manager → Refresh**. Analyses retry automatically; raise `GENELENS_HTTP_TIMEOUT_SECONDS` for slow connections. Corporate firewalls often block FTP/EBI hosts. |
| HTTP 429 / *rate-limiting* | NCBI limits anonymous use to 3 requests/s. Wait a minute, or add `GENELENS_NCBI_API_KEY`. |
| **Invalid environment variable** – backend stops at start with a `ValidationError` naming a `GENELENS_…` setting | A value in `backend\.env` has the wrong type (e.g. text where a number is expected, or a quote left open). Fix or comment out that line with `#` and restart. |
| **Upload failure** in the Custom Dataset Lab | The message names the problem: unsupported extension, empty file, not UTF-8 text, VCF without `##fileformat=VCF`, `.vcf.gz` that is not gzip-compressed, JSON that is not a list of records, or a file over 200 MB. Fix the file and upload again. *Cannot reach the backend* means terminal 1 is not running. |
| **Custom dataset fails to process** | Usually no chromosome/position/REF/ALT mapping – map them in *Column mapping* and press **Run GeneLens Analysis** again. ClinVar matching needs a known assembly (GRCh37/GRCh38). |
| **Frontend build failure** (`npm run build`) | TypeScript errors are printed with file and line. Run `npm install` again after pulling new code, and make sure you are in `frontend`. |
| UI says *Cannot reach the GeneLens backend* | Terminal 1 is not running or crashed – look at its last lines. |
| `git clone` fails with *Invalid argument* | Clone into a folder without a trailing dot (step 1). |
| Ctrl+Shift+B says *No build task* | You opened `backend` or `frontend` instead of the `GeneLens` folder. |
| An analysis fails with *has no record* | Use an official gene symbol – the search box suggests valid ones. |

Technical details of any error are written to **terminal 1** (the backend log); the browser shows only a readable message and, for unexpected errors, a short reference code you can search for in that log.

## 12. Configure and retrieve datasets
Everything is retrieved **live, per gene**, the first time it is needed, then cached in `backend\data\cache\`. Choose the dataset in the Command Center's **Dataset** selector:

| # | Dataset | Assembly | What is fetched for a gene |
|---|---|---|---|
| 1–4 | gnomAD v4 (exomes+genomes, non-UKB), v3 (genomes, non-cancer) | GRCh38 | all variants with AC/AN/AF + populations (gnomAD GraphQL) |
| 5–7 | gnomAD v2.1 (exomes+genomes, non-cancer), ExAC | GRCh37 | same, older assembly |
| 8 | 1000 Genomes Project – Phase 3 | GRCh37 | records in the gene region read from the official tabix-indexed VCFs (IGSR) |
| 9 | ClinVar Variant Summary – NCBI | GRCh38 | clinical classifications only (no frequencies) |
| 10 | dbSNP RefSNP Dataset – NCBI | GRCh38 | all RefSNPs annotated to the gene with alleles + per-study frequencies |

ClinVar is always retrieved alongside (NCBI E-utilities by default). The optional bulk ClinVar file (~450 MB) can be downloaded from **Source Manager → ClinVar Bulk TSV → Download now**, or in terminal 1:
```bash
python -m scripts.download_clinvar
```
then choose *ClinVar source → variant_summary TSV*. Endpoints, formats, limits and assemblies of all seven sources are documented in [DATA_SOURCES.md](DATA_SOURCES.md).

Other utilities (terminal 1, inside `backend`):
```bash
python -m scripts.run_pipeline --gene CFTR --dataset gnomad_r4
```
```bash
python -m scripts.create_snapshot --gene CFTR
```
```bash
python -m scripts.perf_benchmark --analysis <analysis-id> --out perf.json
```
The repository ships a real **offline snapshot for HBB** (gnomAD v4 + ClinVar, retrieved 2026-11-10), used only if those APIs are unreachable and always labelled `offline snapshot`.

## 13. Run the tests
**Backend** – 117 tests (data cleaning, AF = AC/AN, matching, statistics validated against hand calculations, anomaly engine, synthetic generator incl. duplicates and AF range, connectors, tabix reader, provenance separation, comparison lab, custom datasets for every format, JSON reports, API). Terminal 1, inside `backend`, venv active:
```bash
python -m pytest
```
**Frontend** – unit tests (formatting of missing values, Wilson intervals, request de-duplication and caching, readable errors), then type-check + production build. Terminal 2, inside `frontend`:
```bash
npm test
```
```bash
npm run build
```
**End-to-end acceptance checks** (optional, ~95 browser checks – gene search, dropdown stacking, datasets, real/synthetic modes, explanations, anomaly cards, population content, comparison lab, custom upload flow, no raw JSON on any page, themes, no horizontal overflow on all 12 pages at 1280/1024/768 px). With both servers running, an HBB + CFTR gnomAD v4 analysis and one synthetic job created:
```bash
npm i -D playwright
```
```bash
npx playwright install chromium
```
```bash
node e2e/smoke.cjs <HBB-analysis-id> <screenshot-folder> <variant-file.csv>
```

---

# Part B – The project

## 14. Research problem & objectives
A variant classified as *pathogenic* for a rare Mendelian disease is usually rare in the general population. When a pathogenic variant is common – or a *benign* one is extremely rare – the combination deserves attention. Explanations include **biology** (recessive carrier frequency, reduced penetrance, founder effects, balancing selection such as the sickle-cell allele), **data quality** (low coverage, failed filters, incomplete records, ambiguous matching) or an **interpretation that merits review**.

Objectives: retrieve real data with full provenance; normalise and match records allele by allele (never by gene name); compare frequencies across P / LP / VUS / LB / B with appropriate statistics; screen for unusual combinations with explainable rules, separating data-quality issues from biologically interesting observations; describe population frequencies and gene constraint without inferring individual risk; generate clearly labelled synthetic data to evaluate the screening engine; compare genes and screening scenarios; produce reproducible reports.

## 15. Features – twelve modules
| # | Module | Highlights |
|---|---|---|
| 01 | **Genomic Command Center** | Gene search with suggestions before typing, 10-dataset picker, 7-source status, provenance-aware metrics, gene annotation cross-check (gnomAD / Ensembl / UCSC), recent analyses (open / delete) |
| 02 | **Variant Explorer** | Server-side search / filter (class, match, AF range, type, highest-AF population) / sort / pagination up to 500 rows with windowed rendering; Real · Synthetic · Both modes; structured detail drawer (identity, population frequency, classification, matching & provenance – "Not available in source record." for missing values) with on-demand **Ensembl VEP** and **dbSNP**; CSV export |
| 03 | **Pathogenicity Intelligence Lab** | Classification distribution, log-AF box plots & distributions, review stars, conflicts, **VUS analysis** (share with Wilson CI, frequency bands, VUS common in a population), **classifications by year of last evaluation**, unusual-combination flags |
| 04 | **Population Observatory** | Overview metrics, population × variant heatmap, per-group counts by class, **highest AF per group**, grpmax, missing-data indicators, filters, source metadata |
| 05 | **Gene Constraint Observatory** | pLI / LOEUF / missense-Z, o/e with CIs, **all 19 constraint metrics with availability**, multi-gene LOEUF comparison |
| 06 | **Anomaly Detection Engine** | Rules + robust outliers + Isolation Forest; cards with reason, why it matters and recommended investigation |
| 07 | **Statistics Studio** | Mann–Whitney, chi-square, Fisher, Spearman, per-class proportions with Wilson CIs, effect sizes, readable assumption checks, BH-FDR, statistical vs biological significance; invalid analyses labelled *not run*; real and synthetic computed separately |
| 08 | **Synthetic Data Lab** | Seeded generator fitted to real distributions; record count, gene label (`SYN:<gene>`), class mix, AF range, populations, missing / conflicting / unusual / **duplicate** rates; preview, CSV export, real-vs-synthetic comparison, anomaly-engine recovery check |
| 09 | **Gene Comparison Lab** | 2–5 genes side by side; AF threshold, classes, minimum review stars, population selection; what-if screening (previous / updated / difference / % change); save, reopen, export, download charts |
| 10 | **Report Generator** | PDF, CSV and **JSON** reports (synthetic jobs in a separate labelled section); analysis history & full provenance |
| 11 | **Source Manager** | **Section A**: seven live connectors with status, last check, latency, functionality, records retrieved, version, refresh; per-stage ClinVar bulk-file status (reachable / available / downloaded / indexed / imported) with optional download. **Section B**: custom datasets (add, view, process, reprocess, export, delete). Dataset registry |
| 12 | **Custom Dataset Lab** | Upload CSV/TSV/TXT/VCF/VCF.GZ/JSON (drag & drop, real upload progress); automatic inspection (columns, genomic fields, AC/AN/AF, classifications, populations, assembly metadata, missing values, duplicates); 20-row preview; editable column mapping; GRCh37/GRCh38/Unknown (never guessed); full pipeline incl. allele-level ClinVar matching; dashboard; rename, reprocess, delete, history, analysis export, cleaned data. Labelled **CUSTOM DATA**, never mixed with official data |

Every module has a prominent **main reason** explanation and a **"How to read this"** guide with bold terms and glossary tooltips. Light and dark themes persist; the sidebar collapses; layouts adapt from phones to wide desktops; reduced-motion is respected.

## 16. Data ecosystem – 10 datasets, 7 sources, custom data
**Sources** (`backend/app/sources/registry.py`, each with a real `probe()` and persisted statistics):

| Source | Integration | Used for |
|---|---|---|
| gnomAD GraphQL API | GraphQL over HTTPS | datasets 1–7, gene constraint, gene search |
| NCBI ClinVar E-utilities | esearch + esummary | clinical classifications (default); GRCh37 via ClinVar's own GRCh37 locations |
| ClinVar Bulk TSV / FTP | `variant_summary.txt.gz` | offline / large-scale clinical analysis |
| Ensembl REST API | REST (GRCh38 + GRCh37 servers) | gene identifiers, coordinates, canonical transcripts, VEP annotation |
| NCBI dbSNP / Variation API | E-utilities `db=snp` + Variation Services | dataset 10, RefSNP details in the variant drawer |
| International Genome Sample Resource | data-portal API + tabix range requests | dataset 8 (1000 Genomes phase 3), population metadata |
| UCSC Genome Browser API | REST | assembly info, RefSeq gene coordinates, cytoband |

Every dataset's availability is checked against its live provider (e.g. the gnomAD `DatasetId` enum is introspected). Assemblies are never mixed: ClinVar records are converted to GRCh37 using ClinVar's own GRCh37 location, and records without one are kept as *unmatchable* rather than guessed. Details: [DATA_SOURCES.md](DATA_SOURCES.md).

## 17. Technology stack
| Layer | Technologies |
|---|---|
| Frontend | React 18, TypeScript 5, Vite 5, Tailwind CSS 3, Framer Motion 11, Plotly.js (cartesian bundle), Lucide, React Router 6 |
| Typography | DM Serif Display (headings), Manrope (body), IBM Plex Mono (identifiers) |
| Backend | Python 3.11+, FastAPI, Pydantic v2, Uvicorn, httpx |
| Science | pandas, NumPy, SciPy, scikit-learn, Matplotlib, Seaborn |
| Data | SQLAlchemy 2.0, SQLite (PostgreSQL-ready), Alembic migrations + automatic column upgrade |
| Reports | ReportLab |
| Testing | pytest, FastAPI TestClient, Playwright (e2e) |

A small pure-Python **tabix/BGZF reader** (`app/services/tabix.py`) reads gene regions from remote 1000 Genomes VCFs without native dependencies, so it works on Windows. Biopython is not needed because GeneLens works with coordinates and SPDI strings, not sequence files.

## 18. Architecture
```mermaid
flowchart LR
  UI[React + Vite UI<br/>11 modules] -- "/api (Vite proxy)" --> API[FastAPI /api/*]
  API --> PIPE[Research pipeline<br/>app/pipeline/*]
  PIPE --> DS[Dataset registry<br/>app/datasets.py]
  DS --> SRC[Source connectors<br/>app/sources + app/services]
  SRC --> G[(gnomAD)] & C[(ClinVar API / TSV)] & E[(Ensembl)] & D[(dbSNP)] & I[(IGSR / 1000G)] & U[(UCSC)]
  PIPE --> DB[(SQLite / PostgreSQL)]
  API --> DB
```
```
collection → validation → preprocessing → normalisation → matching → statistics
→ anomaly screening → visualisation data → interpretation → report
```
Full design, folder structure and data model: [docs/architecture.md](docs/architecture.md).

## 19. Statistical methodology
One distinct allele per observation; ambiguous matches excluded by default; variants absent from the frequency dataset are not AF = 0. AF = AC / AN only when AN > 0 and 0 ≤ AC ≤ AN. Mann–Whitney U on log10 AF (rank-biserial r, bootstrap CI of the median difference), chi-square (Cochran rule, Cramér's V), Fisher's exact (conditional OR CI), Spearman (Fisher-z CI), Wilson CI, Benjamini–Hochberg FDR + Bonferroni. Real and synthetic data are always computed separately. Every method is validated against independent calculations in `tests/test_statistics.py`. See [docs/methodology.md](docs/methodology.md).

## 20. Synthetic data methodology
Fit summary distributions from real matched variants (class mix, Gaussian mixture over log10 AF per class, AN model, population shares and dispersion – no records copied); sample populations with Binomial counts so AF = AC/AN always holds; optionally inject missingness, conflicts and unusual frequencies as ground truth; label permanently (`SYNTHETIC`, `SYN-` IDs, chromosome `SYN`, no fabricated clinical evidence); seeded and reproducible; compared to real data with KS statistics and total variation distance.

## 21. Screenshots
| | |
|---|---|
| ![Command Center](docs/screenshots/command-center.png) | ![Command Center – light](docs/screenshots/command-center-light.png) |
| ![Gene search](docs/screenshots/gene-search.png) | ![Dataset picker](docs/screenshots/dataset-picker.png) |
| ![Variant Explorer – Both mode](docs/screenshots/variant-explorer-both.png) | ![Anomaly Engine](docs/screenshots/anomaly-engine.png) |
| ![Gene Comparison Lab](docs/screenshots/gene-comparison-lab.png) | ![Source Manager](docs/screenshots/source-manager.png) |
| ![Pathogenicity Lab](docs/screenshots/pathogenicity-lab.png) | ![Population Observatory](docs/screenshots/population-observatory.png) |

All screenshots show real data (HBB / CFTR, gnomAD v4 + ClinVar, retrieved 2026-11-10) except records explicitly labelled SYNTHETIC.

## 22. API documentation
Interactive docs: **http://localhost:8000/docs**. Main endpoints:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health |
| GET | `/api/sources` · POST `/api/sources/{id}/refresh` | Seven connectors with live status + statistics |
| GET | `/api/sources/status` | Compact gnomAD/ClinVar status (landing page) |
| GET | `/api/datasets` | Ten-dataset registry with live availability |
| GET | `/api/genes/suggest?q=` · `/api/genes/search?q=` | Gene suggestions (8 starters, catalogue, live search) |
| POST | `/api/analysis/run` | Start an analysis (any of the 10 datasets) |
| GET | `/api/analysis/{id}` · `/status` | Results / progress |
| GET | `/api/analysis/statistics?analysis_id=&provenance=` | Statistics; with `provenance` returns `{mode, groups}` |
| GET | `/api/analysis/populations?analysis_id=&provenance=` | Population summary (same shape rule) |
| GET | `/api/analysis/constraint` · `/api/constraint/compare` | Constraint |
| GET | `/api/dashboard?analysis_id=&provenance=` | Command-center metrics per provenance group |
| GET | `/api/variants?provenance=REAL|SYNTHETIC|BOTH` · `/export` · `/{id}` · `/{id}/annotation` | Explorer, CSV, detail, live VEP + dbSNP |
| POST/GET | `/api/anomalies/detect` · `/api/anomalies?provenance=` | Screening; flags with headline, reason, why it matters, recommendation |
| POST/GET | `/api/synthetic/generate` · `/api/synthetic` | Synthetic data |
| POST | `/api/compare/run` · `/api/compare/whatif` | Gene comparison and what-if |
| POST/GET/DELETE | `/api/compare/saved` · `/{id}` · `/{id}/export` | Saved comparisons |
| POST/GET | `/api/reports/generate` (`pdf`, `csv`, `json`) · `/api/reports` · `/{id}/download` | Reports |
| GET/DELETE | `/api/history` · `/api/history/{id}` | Analysis history & provenance |
| GET | `/api/analysis/pathogenicity?analysis_id=` | VUS profile and classifications by evaluation year |
| GET/POST | `/api/sources/clinvar_tsv/pipeline` · `/api/sources/clinvar_tsv/download` | ClinVar bulk-file stages; background download with real byte progress |
| POST/GET | `/api/custom-datasets` (multipart upload) · `/api/custom-datasets/{id}` | Upload + inspection (preview, detected mapping, assembly, missing values) · dataset with analysis |
| PATCH/DELETE | `/api/custom-datasets/{id}` | Rename, set mapping / assembly / ClinVar option · delete with all records |
| POST | `/api/custom-datasets/{id}/process` | Run (or re-run) the pipeline in the background |
| GET | `/api/custom-datasets/{id}/export?format=json\|csv` · `/cleaned.csv` | Analysis export · cleaned records |
| GET | `/api/variants?custom_dataset_id=` | Explorer rows of one custom dataset (CUSTOM only) |

**API changes in this version** (backward compatible): `/api/datasets` now returns the full registry objects; `statistics`, `populations`, `dashboard`, `anomalies` and `variants` accept `provenance` (old calls without it behave as before); anomaly items include `headline`, `reason`, `why_it_matters`, `recommendation`; GRCh37 datasets now accept `clinvar_source=eutils`.

## 23. Performance
Measured before/after numbers (cold vs cached navigation, gene suggestions, filtering, analysis runtimes) and the optimisations behind them are in [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md).

## 24. Limitations
* ClinVar classifications are submitted assertions, not ground truth; frequency is itself ACMG/AMP evidence, so frequency–classification associations are partly circular.
* Reference datasets (gnomAD, 1000 Genomes) under-represent many ancestries and are not disease-free.
* Matching relies on both sources being left-aligned (no reference FASTA); haplotypes, large CNVs and IUPAC-ambiguous alleles are reported as unmatchable.
* 1000 Genomes population AC is derived as AF × AN (phase 3 genotypes are complete); dbSNP allele numbers are derived from study count ÷ frequency – both are flagged on every record.
* dbSNP retrieval is capped at 25,000 RefSNPs per gene; very large genes take minutes without an NCBI API key.
* Third-party APIs can rate-limit or change; GeneLens reports this honestly in the Source Manager. All connectors were tested live on 2026-11-10.
* Synthetic data reproduces marginal distributions only, not linkage or function.

## 25. Future enhancements
Reference-FASTA left-alignment; regional missense constraint; per-submission (SCV) ClinVar conflict analysis; Docker Compose with PostgreSQL and a job queue; Playwright tests in CI.

## 26. References and data attribution
* Chen S, et al. *A genomic mutational constraint map using variation in 76,156 human genomes.* Nature 625, 92–100 (2024).
* Karczewski KJ, et al. *The mutational constraint spectrum quantified from variation in 141,456 humans.* Nature 581, 434–443 (2020).
* Landrum MJ, et al. *ClinVar: improvements to accessing data.* Nucleic Acids Res 48, D835–D844 (2020).
* 1000 Genomes Project Consortium. *A global reference for human genetic variation.* Nature 526, 68–74 (2015); Fairley S, et al. *The International Genome Sample Resource (IGSR) collection of open human genomic variation resources.* Nucleic Acids Res 48, D941–D947 (2020).
* Sherry ST, et al. *dbSNP: the NCBI database of genetic variation.* Nucleic Acids Res 29, 308–311 (2001).
* Martin FJ, et al. *Ensembl 2023.* Nucleic Acids Res 51, D933–D941 (2023); McLaren W, et al. *The Ensembl Variant Effect Predictor.* Genome Biol 17, 122 (2016).
* Nassar LR, et al. *The UCSC Genome Browser database: 2023 update.* Nucleic Acids Res 51, D1188–D1195 (2023).
* Richards S, et al. *ACMG/AMP standards and guidelines for the interpretation of sequence variants.* Genet Med 17, 405–424 (2015).
* Benjamini Y, Hochberg Y. J R Stat Soc B 57, 289–300 (1995); Liu FT, Ting KM, Zhou ZH. *Isolation Forest.* ICDM (2008); Li H. *Tabix.* Bioinformatics 27, 718–719 (2011).

Data © their providers (Broad Institute gnomAD, NCBI, EMBL-EBI/IGSR, Ensembl, UCSC); cite them in any work using GeneLens output. Code: MIT – see [LICENSE](LICENSE).

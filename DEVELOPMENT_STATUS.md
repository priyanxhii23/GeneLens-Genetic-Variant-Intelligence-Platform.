# GeneLens – development status

_Last updated: 2026-11-10 (final system completion: bug fixes, Custom Dataset Lab, performance, UI/UX refinement)_

## Summary
This release was built on the existing project; no working feature was removed. Every phase of the brief is implemented and was tested against live public services and in a real browser.

| Phase | Scope | Status |
|---|---|---|
| 1 | Gene Comparison Lab dropdown behind the Explore panel → portal-rendered, collision-aware dropdowns (gene combobox and dataset picker); click-outside, Escape, Tab, arrows, Enter, filtering and scrolling; verified at 1440/1280/1024/768 px in both themes | ✅ |
| 2 | **Custom Dataset Lab** – upload (CSV/TSV/TXT/VCF/VCF.GZ/JSON), inspection, preview, editable mapping, assembly handling, full pipeline, dashboard, management, CUSTOM DATA separation | ✅ |
| 3 | Shared layout system (tokens + `.page .stack .layout-*` classes) applied to all 12 pages; light/dark use the same layout; no horizontal overflow on any page at 1280/1024/768 px | ✅ |
| 4 | Performance (backend and frontend) with before/after measurements – see [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md) | ✅ |
| 5 | No raw JSON, technical evidence, stack traces or exception text in the UI; flags read "Why was this variant flagged? / What this means / Recommended next step"; missing values read "Not available in source record."; diagnostics in the backend log and the developer-only `GET /api/variants/{id}/evidence` | ✅ |
| 6 | Module completion (Population, Constraint, Statistics, Synthetic, Pathogenicity, Variant Explorer, Anomalies, Reports) | ✅ |
| 7 | Source Manager Section A (7 sources) / Section B (custom datasets); ClinVar bulk file stages | ✅ |
| 8 | Visual polish within the existing identity; reduced motion respected | ✅ |
| 9 | Scientific-integrity rules (see below) | ✅ |
| 10 | Testing – backend, frontend unit, end-to-end | ✅ |
| 11 | ZIP `GeneLens_Final_Complete_Project.zip` built from git (no `node_modules`, venvs, caches, databases or secrets) and verified from a clean extraction | ✅ |
| 12–13 | README (Windows + VS Code), DEVELOPMENT_STATUS.md, PERFORMANCE_REPORT.md, DATA_SOURCES.md | ✅ |

## New and changed functionality
* **Custom Dataset Lab** (`backend/app/pipeline/custom_dataset.py`, `backend/app/api/custom_datasets.py`, `frontend/src/pages/workspace/CustomDatasetLab.tsx`)
  * Streaming upload (1 MB chunks, 200 MB limit, SHA-256) with real byte progress.
  * Format detection and validation: delimiter sniffing; VCF header, multi-allelic splitting and INFO `Number=A` expansion; gzip check; JSON list or object.
  * Inspection: 20-row preview, column synonyms, population columns (`AF_nfe`, `afr_AC`, …), missing values per column, schema issues.
  * Assembly is read from explicit header metadata or chosen by the user. It is **never** guessed, an assembly column that conflicts with the choice is rejected, and ClinVar is disabled while the assembly is unknown.
  * Processing in a background job: normalisation, validation, duplicates, AF = AC/AN (or a reported AF, flagged), populations, optional allele-level ClinVar annotation or concordance (the file's own classifications are never overwritten), statistics, population summary and anomaly screening.
  * Each value is labelled as *from file*, *calculated*, *retrieved* or *unavailable*.
  * Outputs: dashboard, processed-records table with variant drawer, rename, reprocess, delete, history, JSON/CSV analysis export and a cleaned CSV.
* **Source Manager**
  * Section A shows last check, latency, functionality and version per source. For the ClinVar bulk file it reports *reachable / remote file available / downloaded / indexed / records imported*, with an optional background download showing real byte progress.
  * Section B lists custom datasets with view, process, reprocess, export and delete.
* **Population Observatory**: overview metrics (variants with population data, groups, median overall AF, highest population AF, records missing some groups), highest AF per group (clickable), source/retrieval metadata, empty states.
* **Constraint Observatory**: table of all 19 gnomAD constraint metrics, each marked *retrieved* or *not available in source record*.
* **Statistics Studio**: per-class proportions and frequency-data coverage with 95 % Wilson intervals, and a "statistical vs biological significance" explanation. Assumptions are shown as readable sentences.
* **Synthetic Lab**: gene label (stored as `SYN:<gene>`), allele-frequency range, duplicate rate (labelled ground truth), alongside the existing count, seed, class mix, populations, missing/conflict/unusual rates, preview and export.
* **Pathogenicity Lab**:
  * VUS analysis: share with Wilson CI, frequency bands, review stars, and VUS that are common in a population.
  * Classifications by year of last evaluation, labelled honestly as such, because ClinVar's APIs expose only the latest evaluation date.
* **Variant Explorer**: highest-AF-population filter, page sizes up to 500 with windowed rendering, structured drawer (identity, population frequency, classification, matching & provenance) without raw evidence.
* **Reports**: JSON export. Synthetic jobs appear in a separate, labelled section, and flags are written in plain language.
* **Errors**: every user-facing error is a readable sentence (`app/utils.user_message`). Unexpected errors show a short reference code that is also written to the backend log.

## Scientific-integrity rules and where they are enforced
| Rule | Enforcement |
|---|---|
| Never fabricate values; missing ≠ zero | Parsers keep `None`; AF only from AC/AN (or an explicitly reported AF, flagged); UI shows "—" / "Not available in source record."; tests `test_processing_counts_duplicates_invalid_and_missing`, frontend `formatting never turns missing into zero` |
| No mixing of real, synthetic and custom data | Separate `provenance` values and foreign keys; `{mode, groups}` API shape; custom rows only reachable via `custom_dataset_id`; test `test_custom_data_is_separate_and_deleted` |
| Assembly preserved, never guessed, never mixed | `detect_assembly` uses header metadata only; conflicting assembly column rejected; ClinVar disabled when unknown; test `test_assembly_is_never_guessed` |
| Allele-level matching only, alleles validated | Exact VCF key then minimal representation; position-only or gene-only matches never made; test `test_vcf_multiallelic_and_clinvar_annotation` (1-100-A-T stays unmatched next to 1-100-A-G) |
| External annotations kept separate | ClinVar annotation of custom data marked by `match_method`; own classifications never overwritten (`test_own_classification_is_never_overwritten`) |
| No misclassification claims from frequency alone | Flag texts and guides state this explicitly |
| Populations are not individual risk | Notes on every population view and in reports |
| Synthetic data identified in every export | `SYN-` keys, `SYN:` gene labels, CSV header notice, JSON report section notice |
| Deterministic, rule-based explanations | `describe_flag` templates; no generative text |

## Tests executed (all actually run, 2026-11-10)
* **Backend** `python -m pytest`: **117 passed**. New tests (17) cover:
  * custom datasets: CSV/TSV/VCF/VCF.GZ/JSON, invalid files, mapping validation, missing values, duplicates, no assembly guessing, ClinVar annotation and concordance, separation and deletion;
  * synthetic duplicates, AF range, labels, determinism and validation;
  * JSON report, VUS/history endpoint and population overview.
* **Frontend** `npm test` (Vitest): **8 passed**. These cover formatting of missing values, Wilson intervals matching the backend, query strings, request de-duplication and caching, no caching of processing status, and readable errors without stack traces.
* **Frontend** `npm run build`: type-check and production build succeed.
* **End-to-end** `node e2e/smoke.cjs <HBB id> <dir> <file.csv>` against live servers: **94/94 checks passed**. It checks:
  * the comparison gene dropdown is on top of every panel (hit test);
  * the variant drawer is structured with no raw evidence;
  * Population Observatory content;
  * the custom upload flow (preview → GRCh38 → live ClinVar matching → dashboard);
  * no raw JSON or traceback on any of the 12 pages;
  * no horizontal overflow on all 12 pages at 1280/1024/768 px in the light theme;
  * plus all earlier checks (search, datasets, REAL/SYNTHETIC/BOTH, explanations, anomaly cards, comparison/what-if, theme persistence, no console errors).
* **Migrations**: `alembic upgrade head` → `downgrade -1` → `upgrade head` → `alembic check` (*No new upgrade operations detected*). The automatic startup upgrade was also tested on a copy of an older database.
* **Live runs**:
  * Cold runs (empty cache): HBB and CFTR on gnomAD v4.
  * Custom datasets: a CSV of 82 real HBB alleles with live ClinVar matching (69 exact matches), plus custom-dataset processing.
  * BRCA1 analyses for the performance work.

### Integrations that could not be fully tested here
1. **ClinVar bulk TSV download (458 MB)**
   * Not tested end-to-end: the HEAD probe, stage reporting, background-download endpoint and per-gene extraction (with a small TSV in unit tests) are tested, but the full file was not downloaded in this container.
   * Why: to avoid a 458 MB transfer.
2. **PostgreSQL**
   * Tested: the SQLAlchemy/Alembic code is database-agnostic.
   * Not tested: everything else; only SQLite was exercised.
3. **Windows**
   * The README steps follow the standard Windows Python/Node/VS Code workflow, and the `.vscode` tasks use cross-platform commands.
   * Not tested: the test runs above, which were all executed on Linux.

## Known limitations
1. ClinVar matching for custom datasets queries at most 10 genes (most frequent in the file) to stay within NCBI rate limits.
2. Classification "history" uses the date of each record's latest evaluation; the full SCV submission history is not available through the APIs used.
3. Explorer text search uses a 200 ms debounce, so end-to-end search latency is ≈ 320 ms (dropdown filters ≈ 120 ms).
4. 1000 Genomes chrX/Y/MT records carry no per-population AN, so population breakdowns are empty for such genes on that dataset.
5. dbSNP retrieval is capped at 25,000 RefSNPs/gene.

## Next steps
1. Run the Playwright e2e suite in CI with a seeded fixture database.
2. Optional reference-FASTA left-alignment for complex indels in uploaded files.
3. Docker Compose (API + PostgreSQL + static frontend).

## How to resume
Terminal 1:
```bash
cd backend
```
```bash
uvicorn app.main:app --reload --port 8000
```
Terminal 2:
```bash
cd frontend
```
```bash
npm run dev
```
Open http://localhost:5173, or press **Ctrl+Shift+B** in VS Code.

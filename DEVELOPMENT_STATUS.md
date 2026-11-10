# GeneLens – development status

_Last updated: 2026-11-10_

## Summary
Phases 1–6 have been implemented in a first full pass. Backend, frontend, documentation and tests are in place, and the application was verified end-to-end against **live** gnomAD v4 and ClinVar data for HBB.

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture, project structure, backend + frontend setup, design system | ✅ done |
| 2 | gnomAD + ClinVar integration, preprocessing, normalisation, matching, validation on real data | ✅ done |
| 3 | Statistics, anomaly detection, constraint analysis, pipeline runner | ✅ done |
| 4 | Synthetic engine, population analysis, reports, research history | ✅ done |
| 5 | All 10 frontend modules, animations, interactive charts, backend integration | ✅ done |
| 6 | Tests, bug fixes, validation, performance, documentation, GitHub readiness | ✅ first pass done |

## Verified
* `python -m pytest` in `backend/` → **78 passed**.
* `npm run build` in `frontend/` → type-check + production build succeed.
* Live HBB analysis via the API and the UI: 868 gnomAD variants, 1,974 ClinVar records, 489 matched (455 exact, 34 normalized), PDF report rendered (7 pages), synthetic job fitted from real data.
* Live CFTR analysis via the CLI pipeline: 7,577 gnomAD variants, 6,600 ClinVar records, 2,912 matched (2,675 exact, 237 normalized) in 92 s on first run (≈85 s is rate-limited ClinVar retrieval without an API key; cached re-runs take seconds).
* All 10 modules + landing page rendered in Chromium (Playwright) in dark and light themes with no console errors; phone width (390 px) has no horizontal overflow.

## Current file structure
See [docs/architecture.md](docs/architecture.md#folder-structure).

## Known issues / remaining work
1. **Large genes**: TTN/BRCA2-scale genes have not been benchmarked in the UI; ClinVar E-utilities retrieval for ~20k records takes about a minute without an NCBI API key.
2. **Indel normalisation** relies on both sources being left-aligned (no reference FASTA). A FASTA-based normaliser would recover remaining complex indels.
3. **GRCh37 path** (gnomAD v2.1 + ClinVar TSV) is implemented and unit-tested with a synthetic TSV, but has not been run against the full 450 MB TSV in this environment.
4. **Background jobs** run in FastAPI's thread pool; a dedicated worker queue would be needed for multi-user deployment.
5. Frontend has no automated UI tests yet (verified manually with Playwright screenshots).
6. Synthetic generator: the lowest-AF tail is slightly under-represented (KS ≈ 0.2–0.26 vs real HBB), because AF granularity depends on AN; reported transparently in the comparison panel.

## Next exact steps
1. Run BRCA1 end-to-end in the UI and record its runtime here.
2. Add Playwright smoke tests for the 10 modules to CI.
3. Add optional reference-FASTA left-alignment to `normalization.py`.
4. Docker Compose (API + PostgreSQL + static frontend).

## How to resume
```bash
cd backend
```
```bash
source .venv/bin/activate
```
```bash
python -m pytest
```
```bash
uvicorn app.main:app --reload --port 8000
```
In a second terminal: `cd frontend && npm run dev`, then open http://localhost:5173.

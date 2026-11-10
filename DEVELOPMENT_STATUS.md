# GeneLens – development status

_Last updated: 2026-11-10 (major UI/UX, data-ecosystem and functionality upgrade)_

## Summary
The upgrade was implemented on top of the existing project (nothing rebuilt from scratch). All earlier modules still work; the standalone History page was folded into the Report Generator with its functionality intact. Every connector was exercised against the **live** public services on 2026-11-10.

| Phase | Scope | Status |
|---|---|---|
| 1 | Inspect existing code, screenshots, and probe all new providers' real APIs | ✅ |
| 2 | Dataset registry (10) + source registry (7 connectors) + pipeline adapters | ✅ |
| 3 | Gene search combobox (suggestions on focus, 8 starters, keyboard, recent) | ✅ |
| 4 | Real / Synthetic / Both modes – stripes removed, gold/pink outlines, filtering of all metrics | ✅ |
| 5 | Explanations (Insight + Guide + glossary), anomaly cards redesign | ✅ |
| 6 | Gene Comparison Lab (replaces History in nav; provenance kept in Report Generator) | ✅ |
| 7 | Logo, typography, glow, animations, collapsible sidebar, Source Manager page | ✅ |
| 8 | Testing (backend + end-to-end in a real browser) | ✅ |
| 9 | Documentation + ZIP | ✅ |

## New functionality
* **Data ecosystem** – `app/datasets.py` (10 datasets with provider, assembly, release, type, live availability); `app/sources/registry.py` (7 connectors: gnomAD GraphQL, ClinVar E-utilities, ClinVar bulk TSV, Ensembl REST, NCBI dbSNP/Variation, IGSR/1000 Genomes, UCSC) with real probes and persisted statistics (`source_status` table).
* **New pipeline adapters** – 1000 Genomes phase 3 via a pure-Python remote tabix/BGZF reader; dbSNP RefSNP catalogue with per-study frequencies; ClinVar-only clinical dataset; GRCh37 ClinVar via E-utilities using ClinVar's own GRCh37 locations.
* **Annotation** – gene cross-check (gnomAD vs Ensembl vs UCSC, cytoband) per analysis; on-demand Ensembl VEP + dbSNP RefSNP record in the variant drawer.
* **Gene suggestions** – `/api/genes/suggest`: 8 starters (HBB, CFTR, BRCA1, BRCA2, TP53, LDLR, G6PD, PAH) + 55-gene catalogue with names and descriptions + live gnomAD search; data-availability and dataset-compatibility badges.
* **Provenance modes** – statistics, populations, dashboard, anomalies and variants accept `provenance=REAL|SYNTHETIC|BOTH`; groups are always computed separately. Synthetic flags are stored per analysis with `provenance=SYNTHETIC`.
* **Explainable flags** – every flag has headline, reason (with the exact threshold crossed), why it matters, recommended investigation.
* **Gene Comparison Lab** – `/api/compare/run`, `/api/compare/whatif`, saved comparisons (save / reopen / export CSV / delete), chart PNG download.
* **Frontend** – DatasetPicker, GeneCombobox, ProvenanceSwitch, Insight, Guide, Term tooltips, PriorityBadge, LogoMark; new pages Source Manager and Gene Comparison Lab; DM Serif Display / Manrope / IBM Plex Mono typography; collapsible sidebar; refined glow and motion; counters that are never stale off-screen.

## Files created
`backend/app/{datasets.py, genes.py}`, `backend/app/sources/{__init__, registry, tracking}.py`, `backend/app/services/{ensembl_client, dbsnp_client, igsr_client, tabix, ucsc_client}.py`, `backend/app/pipeline/comparison.py`, `backend/app/api/compare.py`, `backend/migrations/versions/07dd7158aaa7_*.py`, `backend/tests/test_upgrade.py`, `frontend/src/components/{DatasetPicker, GeneCombobox, ProvenanceSwitch}.tsx`, `frontend/src/lib/{provenance.tsx, glossary.ts}`, `frontend/src/pages/workspace/{GeneComparisonLab, SourceManager, ProvenanceHistory}.tsx`, `frontend/e2e/smoke.cjs`, `.vscode/tasks.json`.

## Files modified
Backend: `models.py`, `database.py` (automatic column upgrade), `schemas.py`, `main.py`, `api/{analysis, anomalies, synthetic, system, variants}.py`, `pipeline/{anomalies, interpretation, matching, preprocessing, reports, runner, statistics}.py`, `services/{clinvar_client, gnomad_client}.py`, `scripts/*`, HBB snapshots (regenerated), tests. Frontend: `index.css`, `tailwind.config.js`, `index.html`, `main.tsx`, `lib/{api, types}.ts`, `components/{ui, Sidebar, Workspace}.tsx`, every workspace page, `Landing.tsx`. Removed: `pages/workspace/History.tsx` (route redirects to Report Generator). Docs: README, architecture, methodology, data_sources.

## Tests executed (all actually run)
* `python -m pytest` (backend): **100 passed** – includes 22 new tests for registries, connector parsers, tabix/BGZF, GRCh37 conversion, dbSNP derivation, 1000G VCF parsing, explanations, provenance separation, comparison/what-if, saved comparisons, gene suggestions, source statistics and database auto-upgrade.
* `npm run build` (frontend): type-check + production build succeed.
* `node e2e/smoke.cjs` against live servers with real HBB + CFTR analyses and a synthetic job: **53/53 checks passed** (logo size, nav, fonts, suggestions before typing, filtering, keyboard selection, Escape, 10 datasets with status, description, REAL/SYNTHETIC/BOTH filtering, gold/pink outlines only in BOTH, no stripes anywhere, record counts and metrics change with mode, explanation font sizes, guides, anomaly cards without raw JSON, technical evidence in details, 7 source cards, comparison + what-if update + save, provenance history, theme persistence, no horizontal overflow at 1280/1024/768 px, no console errors).
* Live pipeline runs: HBB on gnomAD v4 / v2.1 (GRCh37, E-utilities), 1000 Genomes, dbSNP, ClinVar-only; CFTR on gnomAD v4. All completed.

Bugs found and fixed during testing: frequency rows with invalid alleles had no key (dbSNP IUPAC codes); flag reason misstated which threshold triggered; Source Manager card footer overflowed at 1280 px; Comparison Lab listed "Synthetic" as a real data source; animated counters could show stale values when updated off-screen; what-if panel now shows a "Recalculating…" state.

## Known issues / limitations
1. Comparison and what-if requests load each gene's stored rows (~1–2.5 s for CFTR-sized genes); an in-memory row cache would speed this up.
2. 1000 Genomes chrX/Y/MT records carry no per-population AN (haploid/mixed ploidy), so population breakdowns are empty for genes such as G6PD on that dataset.
3. GRCh37 conversion of E-utilities ClinVar records assumes no assembly-level indel within the variant; such rare records may fall back to *unmatchable*.
4. dbSNP retrieval is capped at 25,000 RefSNPs/gene and takes minutes for large genes without an NCBI API key.
5. The full 450 MB ClinVar TSV route is unit-tested with a small file but was not downloaded end-to-end in this environment.
6. The Playwright e2e script is not yet part of CI.

## Remaining / next steps
1. Add the e2e script to GitHub Actions with a seeded fixture database.
2. Cache analysis rows in memory for the Comparison Lab.
3. Optional reference-FASTA left-alignment for complex indels.
4. Docker Compose (API + PostgreSQL + static frontend).

## How to resume
```bash
cd backend
```
```bash
python -m pytest
```
```bash
uvicorn app.main:app --reload --port 8000
```
Second terminal: `cd frontend` then `npm run dev`, open http://localhost:5173 – or press **Ctrl+Shift+B** in VS Code.

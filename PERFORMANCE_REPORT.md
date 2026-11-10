# GeneLens – performance report

_Measured 2026-11-10 on the development container (4 vCPU, SQLite, live public APIs). All numbers are real measurements, not estimates. "Before" was measured before the optimisation work of this release, "after" on the final code. External API timings depend on the providers and the network on the day._

## How it was measured
* **Backend API** – `python -m scripts.perf_benchmark --analysis <id> … --out perf.json` (in `backend/`). Each endpoint is called twice: **cold** = first request after a backend restart, **warm** = immediately repeated. Analyses used: HBB (2,353 variants), CFTR (11,265) and BRCA1 (19,690), all gnomAD v4 + ClinVar.
* **End-to-end analysis runtime** – `python -m scripts.run_pipeline --gene <G> --dataset gnomad_r4` in an **empty data directory** (nothing cached, every source queried live), wall-clock time.
* **Browser** – Playwright (Chromium) script that clicks through the sidebar and types into the search boxes, timing from the user action until the page's main content is on screen. Navigation times include the deliberate 0.35 s page transition animation.

## 1. Backend endpoints (milliseconds)
| Endpoint | Before – cold | Before – warm | After – cold | After – warm |
|---|---|---|---|---|
| `GET /datasets` (10 datasets, live availability) | **5,602** | 2 | **1,596** ¹ | 2 |
| `GET /sources` (7 live connectors) | **4,715** | 6 | **6** ¹ | 5 |
| `GET /genes/suggest` (empty / `q=brc`) | 8 / 5 | 3 / 3 | 5 / 4 | 3 / 4 |
| HBB – statistics (REAL) | 111 | 170 | **9** | 9 |
| HBB – statistics (BOTH, real + synthetic) | 375 | 347 | 329 | 228 |
| HBB – populations (REAL) | 116 | 110 | **15** | 14 |
| HBB – dashboard | 110 | 76 | 42 | 30 |
| CFTR – statistics (REAL) | 746 | – | **22** | 20 |
| BRCA1 – statistics (REAL) | **1,266** | – | **28** | 27 |
| BRCA1 – populations (REAL) | **1,162** | – | **18** | 18 |
| BRCA1 – dashboard | – | – | 151 | 97 |
| Variant page / sorted / anomalies (all genes) | 10–18 | 10–11 | 17–45 | 12–46 |
| `POST /compare/run` (HBB vs CFTR) | – | 903 | 252 | **88** |
| `POST /compare/whatif` | – | 1,011 | 136 | **123** |

¹ After a restart the backend checks all seven sources **in parallel** in the background (≈ 1.6 s once); results are then served from a stale-while-revalidate cache (5 min) and refreshed in the background, so `/sources` answers in milliseconds and *Refresh* still performs a real live check.
CFTR populations took 932 ms once in the final run because that analysis was stored before the new population overview existed; it is computed once, saved, and then served in 17 ms.

**Population Observatory "stuck on Loading" – root cause and fix.** The page fired the same request three times (React StrictMode double mount plus a dependency change). Each request re-read every variant row of the gene (≈ 0.7–1.2 s for BRCA1) and SQLite serialised them, so the spinner could run for several seconds or appear to hang. Now: identical in-flight GETs are shared in the browser, population and statistics results computed during the analysis are returned without touching variant rows, and rows needed elsewhere come from an in-memory row cache. BRCA1 populations: **1,162 → 18 ms**.

## 2. Full analysis runtime (cold, live APIs, nothing cached)
| Gene | Before | After | Main change |
|---|---|---|---|
| HBB (gnomAD v4 + ClinVar) | 33.7 s | **22.4 s** | keep-alive HTTP connections; concurrent ClinVar batches |
| CFTR | 105.6 s | **53.7 s** | as above (ClinVar dominates) |
| BRCA1 | 212.3 s | not re-run cold ² | as above |
| ClinVar retrieval alone, HBB | 24.6 s | **10.8 s** | up to 3 E-utilities batches in flight behind one shared, thread-safe rate limiter (3 req/s without key, 10 with `GENELENS_NCBI_API_KEY`) |
| Custom dataset, 82 records incl. ClinVar matching | – | 0.5 s processing + ClinVar retrieval | streamed parsing, batched inserts |

² BRCA1's runtime is dominated by ~16,000 ClinVar records fetched at NCBI's anonymous rate limit; with an NCBI API key the limit is 3.3× higher.

## 3. Browser (milliseconds, from click/keystroke to content on screen)
| Interaction | Target | Measured |
|---|---|---|
| Gene suggestions after typing `cf` / `ldl` | < 300 | **59 / 42** |
| Variant Explorer – dropdown filter (match status) | < 300 | **116** |
| Variant Explorer – text search (includes a 200 ms typing debounce) | < 300 | **323** (results appear ≈ 120 ms after typing stops) |
| Cached revisit – Variant Explorer / Statistics / Constraint | < 1,000 | **263 / 301 / 317** |
| Cached revisit – Population Observatory / Pathogenicity Lab | < 1,000 | **442 / 569** |
| First visit of a module (lazy chunk + data) | – | 399 – 1,197 |

The text-search debounce was lowered from 350 ms to 200 ms during this measurement; it still prevents a request per keystroke.

## 4. What was changed
**Backend**
* Parallel source probes (thread pool), a 10 s probe timeout without retries, stale-while-revalidate status cache and a warm-up at startup.
* One shared keep-alive `httpx` client for all connectors.
* Concurrent ClinVar/dbSNP E-utilities batches with a single shared rate limiter.
* Results computed during the analysis (statistics, populations) are returned without reloading variants; an in-memory LRU row cache (12 entries, invalidated on every write) serves the rest.
* Composite indexes: `variants(analysis_id, provenance)`, `variants(synthetic_job_id, provenance)`, `variants(custom_dataset_id, provenance)`, `anomaly_results(analysis_id, provenance)` – created automatically at startup and by the Alembic migration.
* Cached data is keyed by the analysis (one gene + dataset + assembly + parameter set), by the custom dataset, or by the full request (gene, dataset, assembly, query), so results are never mixed across them; provenance groups (REAL / SYNTHETIC / CUSTOM) have separate cache entries.
* Background jobs for analyses, custom-dataset processing and the ClinVar bulk download; chunked file reading (uploads in 1 MB chunks, tables in 50,000-row chunks, ClinVar TSV in 200,000-row chunks); batched inserts (2,000 rows).

**Frontend**
* Every module is a lazily loaded chunk; Plotly is split into its own chunk and loaded on first chart.
* Identical GET requests in flight are de-duplicated; successful GETs are cached briefly (60 s for datasets/sources, 20 s for analysis data, never for status or processing endpoints); every write clears the cache.
* Debounced search inputs; memoised chart data; windowed rendering of large Variant Explorer pages (only visible rows are in the DOM).
* Honest loading states: skeletons, stage names reported by the backend (no invented percentages – the only percentage bars are real upload/download byte counts), and previous results stay visible while new ones load.

## 5. Reproduce
Terminal 1 (backend running), inside `backend`:
```bash
python -m scripts.perf_benchmark --analysis <analysis-id> --compare HBB,CFTR --out perf.json
```

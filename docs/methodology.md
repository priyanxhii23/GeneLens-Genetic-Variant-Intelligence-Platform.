# Research methodology

GeneLens implements a ten-stage pipeline. Each stage is a separate module in `backend/app/pipeline/` and can be tested without the web server.

```
DATA COLLECTION → DATA VALIDATION → DATA PREPROCESSING → VARIANT NORMALIZATION → GNOMAD–CLINVAR MATCHING
→ STATISTICAL ANALYSIS → ANOMALY SCREENING → DATA VISUALIZATION → RESEARCH INTERPRETATION → REPORT GENERATION
```

## 1. Data collection (`services/`)
gnomAD variants and constraint for one gene and dataset, plus ClinVar records for the same gene (E-utilities or bulk TSV). See [data_sources.md](data_sources.md). Provenance is stored for every dataset.

## 2. Data validation (`validation.py`)
* `AF = AC / AN` is defined only when `AN > 0` and `0 ≤ AC ≤ AN`; otherwise it is `None`.
* QC codes: `missing_ac_an`, `zero_an`, `negative_count`, `ac_exceeds_an`, `af_inconsistent` (reported AF differs from AC/AN by more than max(1e-6, 0.1 % relative)), `af_out_of_range`.
* ClinVar checks: `missing_variation_id`, `missing_classification`, `missing_alleles`, `multi_allele_record`, `invalid_coordinates`.
* Records are **flagged, never silently dropped**.

## 3. Preprocessing (`preprocessing.py`)
### gnomAD
Nested exome/genome/joint blocks are flattened to one row: AC, AN, AF (joint, or exome + genome), AF per sequencing type, homozygotes, ancestry-group populations (each with AF = AC/AN), grpmax, filters (prefixed by call set) and flags. Variants with `AC0` filters or failing other filters are flagged (`ac0_after_qc`, `failed_gnomad_filter`).

### ClinVar classification vocabulary
| ClinVar text (first germline term) | Fine class | Coarse class |
|---|---|---|
| Pathogenic (incl. "low penetrance") | pathogenic | P_LP |
| Likely pathogenic | likely_pathogenic | P_LP |
| Pathogenic/Likely pathogenic | pathogenic_likely_pathogenic | P_LP |
| Uncertain significance | uncertain_significance | VUS |
| Likely benign | likely_benign | B_LB |
| Benign | benign | B_LB |
| Benign/Likely benign | benign_likely_benign | B_LB |
| Conflicting classifications / interpretations of pathogenicity | conflicting | CONFLICTING |
| risk factor, drug response, association, other… | other | OTHER |
| not provided / no classification | not_provided | OTHER |

Secondary terms after `;` or `,` (e.g. "Pathogenic; other") do not change the primary class; the raw string is preserved.

### Review stars
practice guideline = 4 · expert panel = 3 · multiple submitters, no conflicts = 2 · single submitter or conflicting = 1 · no assertion criteria = 0.

## 4. Variant normalisation (`normalization.py`)
* Chromosome: strip `chr`, `M → MT`; only 1–22, X, Y, MT accepted.
* Alleles: upper-case, `[ACGTN]*`; symbolic alleles (`<DEL>`) are invalid.
* **VCF key** `chrom-pos-ref-alt` as reported.
* **Minimal key**: trim the common suffix, then the common prefix (empty alleles allowed), in 0-based interbase coordinates. Because gnomAD (left-aligned VCF) and ClinVar (fully justified SPDI / left-aligned VCF columns) both start at the leftmost position of a repeat, suffix-first trimming yields the same key without needing the reference sequence. Example: gnomAD `1-200-CT-C` and SPDI `NC_000001.11:200:TT:T` → both `1:200:T:-`.
* Variant type: SNV, MNV, insertion, deletion, complex.

## 5. Matching (`matching.py`)
| Status | Rule | Confidence | Used in statistics |
|---|---|---|---|
| exact | identical VCF key | 1.0 | yes |
| normalized | identical minimal key, single gnomAD candidate | 0.9 | yes |
| ambiguous | several ClinVar records with *different* coarse classes for one allele, or one minimal key → several gnomAD records | 0.5 | optional toggle |
| clinvar_only | allele not in this gnomAD dataset (**not** AF = 0) | – | no |
| unmatchable | no allele-level coordinates (haplotype, CNV, missing alleles) | – | no |
| gnomad_only | no ClinVar record | – | descriptive only |
| secondary_clinvar | extra concordant ClinVar record for an already-matched allele | – | no (never double counted) |

When several ClinVar records map to one allele, the primary is the one with most review stars, then most recent evaluation, then most submitters. Records are **never joined by gene symbol**, and the gnomAD and ClinVar genome builds must be identical (`AssemblyMismatchError` otherwise).

**Real-data validation (HBB, gnomAD v4 + ClinVar, 2026-11-10):** 868 gnomAD variants, 1,974 ClinVar records (1,833 with allele coordinates), 455 exact + 34 normalized matches (all 34 normalized matches are indels whose anchor bases differ between sources). The sickle-cell allele (rs334, `11-5227002-T-A`, Pathogenic) matched exactly, with AF 0.27 % overall and 4.9 % in the African/African-American group.

## 6. Statistical analysis (`statistics.py`)
Sample: exact + normalized matches with gnomAD AF > 0 (ambiguous optional).

| Analysis | Method | Effect size / interval | Assumption checks |
|---|---|---|---|
| Descriptives | n, mean, median, SD (ddof=1), min/max, Q1/Q3, IQR on AF and log10 AF | – | – |
| P/LP vs B/LB, P/LP vs VUS, VUS vs B/LB | Mann–Whitney U, two-sided, on log10 AF; groups need n ≥ 5 | rank-biserial r (positive = first group more frequent), common-language effect size, bootstrap (2,000 resamples, seeded) 95 % CI of the median difference | Shapiro–Wilk per group (≤5,000 sampled), Levene (median-centred) |
| Classification × AF bin (<0.001 %, 0.001–0.01 %, 0.01–0.1 %, 0.1–1 %, ≥1 %) | Pearson chi-square (Yates for 2×2) | Cramér's V | Cochran: ≥80 % of expected counts ≥5, none <1; warning if violated |
| P/LP vs B/LB × (AF < 0.1 %) | Fisher's exact, two-sided | sample odds ratio; conditional MLE 95 % CI | exact – valid for any cell size |
| log10 AF vs review stars | Spearman ρ | Fisher-z 95 % CI | monotonic relationship; ties noted |
| P/LP share of ClinVar records | proportion | Wilson score 95 % CI | – |

**Multiple testing:** all p-values from tests that ran are adjusted together with Benjamini–Hochberg (step-up, monotone; primary, FDR 5 %) and Bonferroni. Significance badges use the BH-adjusted value.

**Interpretation caveats** shown in the UI and reports: variants within one gene are not fully independent; frequency is part of the ACMG/AMP evidence used to classify variants, so frequency–classification associations are partly circular.

**Validation:** `tests/test_statistics.py` checks each method against independent calculations – a hand-worked BH example, a reference Wilson interval (8/10 → 0.4902–0.9433), the exact Mann–Whitney p for complete separation (2/252), a hypergeometric Fisher p-value computed from binomial coefficients, and a manually computed Yates chi-square.

## 7. Anomaly screening (`anomalies.py`)
Default thresholds (all configurable in the UI / API):

| Category | Kind | Trigger (default) | Priority |
|---|---|---|---|
| frequent_pathogenic | biological interest | P/LP with AF ≥ 0.5 % or grpmax AF ≥ 1 % | high if ≥ BA1 (5 %), else medium |
| ba1_frequency_non_benign | biological interest | VUS/conflicting with AF or grpmax ≥ 5 % | high |
| rare_benign | biological interest | B/LB with AF < 1e-5 | low (usually expected) |
| conflicting_interpretation | biological interest | ClinVar conflicting | high if AF ≥ 0.5 %, else medium |
| incomplete_frequency_record | data quality | AN missing or 0 | medium |
| count_inconsistency | data quality | AC > AN, AF ≠ AC/AN, AF out of range | high |
| gnomad_qc_filter | data quality | non-AC0 filter failed | medium if matched |
| low_allele_number | data quality | AN < 50 % of gene median | low |
| incomplete_clinvar_record | data quality | no allele-level coordinates | low |
| ambiguous_match | data quality | discordant duplicate records | medium |
| frequency_outlier_within_class | statistical outlier | robust z = 0.6745·(x − median)/MAD of log10 AF ≥ 3.5 (class n ≥ 10) | medium if ≥ 5, else low |
| multivariate_outlier | statistical outlier | Isolation Forest (200 trees, contamination 2 %, seed 42) on log10 AF, log10 AN, log10 grpmax/AF, class ordinal, stars | low |

Every flag stores its evidence (values and thresholds) and a plain-language explanation. Explanations for biological-interest flags list possible explanations (recessive carriers, reduced penetrance, founder effects, balancing selection) and state explicitly that the flag does not mean a variant is misclassified.

## 8. Visualisation
The backend precomputes chart-ready summaries (histograms on fixed log10 AF bins, box data for matched variants, population matrices, review-star crosstabs), so the browser never loads full datasets.

## 9. Interpretation (`interpretation.py`)
Findings are generated from templates filled with computed values (counts, p-values, effect sizes, thresholds). If a test did not run, the text says why. Fixed limitations and a disclaimer are always attached.

## 10. Reports (`reports.py`)
* **PDF:** ReportLab document with Matplotlib/Seaborn charts – dataset table, methodology, matching statistics, classification and AF charts, descriptive table, population and constraint charts, statistical results with BH-adjusted p-values, top 25 flags, interpretation, limitations, citations and disclaimer.
* **CSV:** flat table (`section, item, metric, value, detail`) with `analysis_id`, `gene` and `provenance` columns.
* Every export is logged in the `exports` table.

## Synthetic data (`synthetic.py`)
See README §12. The anomaly engine is evaluated on every synthetic job: injected unusual-frequency records (half P/LP at AF 1–10 %, half B/LB at AF ≈ 3e-7–5e-6) and injected conflicts are known by construction, and GeneLens reports how many are recovered under default thresholds (for HBB-fitted data with seed 7, 90/100 unusual and 99/100 conflicts; the misses are records whose classification was later blanked by the missingness scenario).

## Reproducibility
* Every analysis stores its parameters, dataset releases and retrieval dates.
* Seeds: bootstrap (analysis seed), Isolation Forest (`seed` threshold), synthetic generation (job seed).
* Cached API responses keep their original retrieval timestamp.

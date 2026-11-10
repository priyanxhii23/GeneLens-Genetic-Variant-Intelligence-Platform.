# Data sources

GeneLens uses only public data, retrieved at analysis time, and records exactly how and when every dataset was obtained.

## gnomAD (Genome Aggregation Database)
* **Access:** gnomAD browser GraphQL API, `https://gnomad.broadinstitute.org/api`.
* **Schema verification:** the fields used were confirmed by GraphQL introspection on 2026-11-10. Re-check at any time with `python -m scripts.inspect_gnomad_schema`. If gnomAD renames a field, the client raises an explicit error rather than silently returning empty data.
* **Query** (`app/services/gnomad_client.py`): `gene(gene_symbol, reference_genome) { gnomad_constraint {…} variants(dataset) { variant_id chrom pos ref alt rsids consequence hgvsc hgvsp lof flags exome{…} genome{…} joint{…} } }`, with `ac`, `an`, `af`, `homozygote_count`, `filters` and `populations { id ac an homozygote_count }` per sequencing type.
* **Datasets supported:** `gnomad_r4` (default, GRCh38, exomes + genomes), `gnomad_r4_non_ukb`, `gnomad_r3`, `gnomad_r3_non_cancer` (GRCh38); `gnomad_r2_1`, `gnomad_r2_1_non_cancer`, `exac` (GRCh37).
* **Counts used:** gnomAD v4 *joint* (exome + genome) AC/AN when available, otherwise the sum of exome and genome. AF is always recomputed as AC/AN and checked against the reported exome/genome AF.
* **Populations:** genetic-ancestry groups `afr, ami, amr, asj, eas, fin, mid, nfe, sas, remaining`. Sex-stratified entries (`XX`, `XY`, `afr_XX`, …) are excluded. *grpmax* excludes `ami, asj, fin, mid, remaining`, mirroring gnomAD.
* **Constraint:** `gnomad_constraint` (GRCh38 → gnomAD v4 constraint; GRCh37 → v2.1.1): pLI, LOEUF (`oe_lof_upper`), o/e with 90 % CIs, observed/expected counts and Z-scores for LoF, missense and synonymous variants, for the canonical transcript recorded in the dataset notes.
* **Pagination:** the gene-level `variants` field has no cursor; the full gene is returned in one response (~1.5 s for BRCA1's 7,287 variants). GeneLens paginates when serving the browser.
* **Rate limiting:** responses are cached on disk (default 7 days). 429/5xx responses are retried with exponential back-off, honouring `Retry-After`.

## ClinVar (NCBI)
### Route 1 – E-utilities (default)
* `esearch.fcgi?db=clinvar&term=<GENE>[gene]&usehistory=y`, then batched `esummary.fcgi` (400 IDs per POST) with the history server.
* Rate limit: 3 requests/s without a key, 10 with `GENELENS_NCBI_API_KEY` (backend only).
* Fields: variation ID (`uid`), accession, allele ID (`variation_set[].measure_id`), **canonical SPDI**, germline classification (`description`, `review_status`, `last_evaluated`, `trait_set`), supporting submissions, genes, molecular type.
* **SPDI → VCF:** SPDI positions are 0-based interbase on RefSeq accessions (`NC_000017.11:43045766:G:A`). GeneLens maps the accession to a chromosome, converts to 1-based, and keeps indel context for minimal-representation matching. SPDI is provided for GRCh38 only, so GRCh37 analyses require Route 2.
* **Haplotypes / compound records** (more than one allele in `variation_set`) are never assigned single-allele coordinates; they are kept as *unmatchable* records.

### Route 2 – `variant_summary.txt.gz`
* `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz` (~450 MB compressed, updated weekly).
* Downloaded once by `python -m scripts.download_clinvar`, streamed to disk, then read in 200,000-row chunks with pandas, keeping only the requested gene and assembly. The per-gene extract is cached in `data/processed/`.
* Uses the VCF-normalised columns `PositionVCF`, `ReferenceAlleleVCF`, `AlternateAlleleVCF`, plus `AlleleID`, `VariationID`, `ClinicalSignificance`, `ReviewStatus`, `PhenotypeList`, `NumberSubmitters`, `LastEvaluated`.
* The full ClinVar XML is never downloaded – the TSV contains everything GeneLens needs.

## Offline snapshots
`backend/data/snapshots/HBB_*.json.gz` are **real** gnomAD and ClinVar responses for HBB retrieved on 2026-11-10 (≈180 kB). They are used only when the live API is unreachable, and the dataset is then marked `offline_snapshot` with its original retrieval date in every view, report and export. Create more with `python -m scripts.create_snapshot --gene <SYMBOL>`.

## Test fixtures
`backend/tests/fixtures/sample_data.py` contains small **hand-built fixture records** (gene `TESTG`) that exercise edge cases (anchor-base indels, haplotypes, discordant duplicates, AN = 0). They are labelled `TEST FIXTURE` and are only used by the test suite – never shown as real data.

## Terms and citation
gnomAD and ClinVar make their data freely available for research. Check each provider's current terms of use before redistributing data, and cite them in any work that uses GeneLens output:
* gnomAD: Chen S, et al. Nature 625, 92–100 (2024) and Karczewski KJ, et al. Nature 581, 434–443 (2020); https://gnomad.broadinstitute.org/
* ClinVar: Landrum MJ, et al. Nucleic Acids Res 48, D835–D844 (2020); https://www.ncbi.nlm.nih.gov/clinvar/

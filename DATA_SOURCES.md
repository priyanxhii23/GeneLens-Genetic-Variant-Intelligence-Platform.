# Data sources

GeneLens uses only public data, retrieved at analysis time, and records exactly how and when every dataset was obtained. Researcher-uploaded **custom datasets** are a separate category (see the end of this document) and are never merged with these sources.

## The seven integrated sources at a glance
| # | Source | Endpoint(s) | Method | Datasets served | Formats | Limits / notes | Assemblies |
|---|---|---|---|---|---|---|---|
| 1 | **gnomAD GraphQL API** (Broad Institute) | `https://gnomad.broadinstitute.org/api` | GraphQL over HTTPS (POST) | gnomAD v4, v4 non-UKB, v3, v3 non-cancer, v2.1, v2.1 non-cancer, ExAC; gene constraint | JSON | No published rate limit; GeneLens caches responses 7 days and retries 429/5xx with back-off | GRCh38 (v3/v4), GRCh37 (v2.1/ExAC) |
| 2 | **NCBI ClinVar E-utilities** | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` (`esearch`, `esummary`, `einfo`) | REST (GET/POST), history server, 400 IDs per batch, ≤ 3 batches in flight | ClinVar classifications for every analysis; ClinVar Variant Summary dataset | JSON | 3 requests/s without key, 10 with `GENELENS_NCBI_API_KEY`; shared throttle with dbSNP | GRCh38 (SPDI); GRCh37 via ClinVar's own GRCh37 locations |
| 3 | **ClinVar bulk TSV / FTP** | `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz` | HTTPS file download (HEAD probe; optional background download from the Source Manager or `python -m scripts.download_clinvar`) | ClinVar Variant Summary (offline / bulk route) | gzip-compressed TSV (~450 MB) | Updated weekly; read in 200,000-row chunks; per-gene extracts cached in `data/processed/` | GRCh37 and GRCh38 rows (`Assembly` column) |
| 4 | **Ensembl REST API** (EMBL-EBI) | `https://rest.ensembl.org`, `https://grch37.rest.ensembl.org` | REST (GET) | Gene annotation cross-check; GRCh37 gene region for 1000 Genomes; on-demand VEP | JSON | 15 requests/s documented limit; GeneLens issues a handful per analysis | GRCh38, GRCh37 |
| 5 | **NCBI dbSNP / Variation Services** | E-utilities `db=snp`; `https://api.ncbi.nlm.nih.gov/variation/v0/` | REST (GET/POST) | dbSNP RefSNP dataset; variant-drawer RefSNP details | JSON | Shares the NCBI rate limit; capped at 25,000 RefSNPs per gene | GRCh38 |
| 6 | **IGSR / 1000 Genomes** (EMBL-EBI) | `https://www.internationalgenome.org/api/beta/…`; `ftp.1000genomes.ebi.ac.uk` phase 3 VCFs | Data-portal API + tabix index + HTTP range requests (pure-Python BGZF reader) | 1000 Genomes Project phase 3 | JSON, bgzipped VCF + `.tbi` | Only the gene region is read (~130 kB index + a few MB) | GRCh37 |
| 7 | **UCSC Genome Browser API** | `https://api.genome.ucsc.edu` | REST (GET) | Assembly descriptions, RefSeq transcript coordinates, cytogenetic band | JSON | Documented courtesy limit of 1 request/s; GeneLens issues 2–3 per analysis | hg38 (GRCh38), hg19 (GRCh37) |

Source status (connection, last check, latency, version, records retrieved) is measured live and shown in the **Source Manager** – Section A. For the ClinVar bulk file the Source Manager reports each stage separately: *source reachable → remote file available → downloaded → indexed (per-gene extracts) → records imported*.

## Overview: ten datasets, seven sources
| # | Dataset (`id`) | Provider | Assembly | Data type | Source connector(s) |
|---|---|---|---|---|---|
| 1 | gnomAD v4 – Exomes + Genomes (`gnomad_r4`) | Broad Institute | GRCh38 | population frequency | gnomAD GraphQL |
| 2 | gnomAD v4 – Non-UKB Subset (`gnomad_r4_non_ukb`) | Broad Institute | GRCh38 | population frequency | gnomAD GraphQL |
| 3 | gnomAD v3 – Genomes (`gnomad_r3`) | Broad Institute | GRCh38 | population frequency | gnomAD GraphQL |
| 4 | gnomAD v3 – Non-Cancer (`gnomad_r3_non_cancer`) | Broad Institute | GRCh38 | population frequency | gnomAD GraphQL |
| 5 | gnomAD v2.1 – Exomes + Genomes (`gnomad_r2_1`) | Broad Institute | GRCh37 | population frequency | gnomAD GraphQL |
| 6 | gnomAD v2.1 – Non-Cancer (`gnomad_r2_1_non_cancer`) | Broad Institute | GRCh37 | population frequency | gnomAD GraphQL |
| 7 | ExAC (`exac`) | Broad Institute | GRCh37 | population frequency | gnomAD GraphQL |
| 8 | 1000 Genomes Project – Phase 3 (`igsr_1000g_phase3`) | IGSR / EMBL-EBI | GRCh37 | population frequency | IGSR (+ Ensembl GRCh37 for the gene region) |
| 9 | ClinVar Variant Summary – NCBI (`clinvar_variant_summary`) | NCBI | GRCh38 | clinical annotation | ClinVar E-utilities and/or bulk TSV |
| 10 | dbSNP RefSNP Dataset – NCBI (`dbsnp_refsnp`) | NCBI | GRCh38 | variant catalogue | dbSNP E-utilities + Variation Services |

All seven gnomAD-served datasets were verified live on 2026-11-10 (HBB returned 868 / 662 / 287 / 283 / 355 / 350 / 227 variants respectively). gnomAD's API does not publish a release number, so the registry names the release by the dataset ID the API serves rather than guessing a version.

Every analysis always retrieves **ClinVar** for the same gene. Availability shown in the UI comes from live probes (`/api/datasets`, `/api/sources`).

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

### GRCh37 analyses with E-utilities
ClinVar's esummary reports each variant's start on **both** GRCh38 and GRCh37 (`variation_set[].variation_loc`). For GRCh37 datasets GeneLens shifts the SPDI-derived GRCh38 position by the difference between those two starts (the local assembly offset) and keeps the alleles. Records lacking a GRCh37 location, or whose chromosome differs, are kept as *unmatchable*. Validation: gnomAD v2.1 + E-utilities ClinVar for HBB gives 240 exact allele matches, which would be impossible if the conversion were wrong.

### Route 2 – `variant_summary.txt.gz`
* `https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz` (~450 MB compressed, updated weekly).
* Downloaded once by `python -m scripts.download_clinvar`, streamed to disk, then read in 200,000-row chunks with pandas, keeping only the requested gene and assembly. The per-gene extract is cached in `data/processed/`.
* Uses the VCF-normalised columns `PositionVCF`, `ReferenceAlleleVCF`, `AlternateAlleleVCF`, plus `AlleleID`, `VariationID`, `ClinicalSignificance`, `ReviewStatus`, `PhenotypeList`, `NumberSubmitters`, `LastEvaluated`.
* The full ClinVar XML is never downloaded – the TSV contains everything GeneLens needs.

## Ensembl REST API
* `https://rest.ensembl.org` (GRCh38) and `https://grch37.rest.ensembl.org` (GRCh37); release reported by `/info/data` (release 116 on 2026-11-10).
* `/lookup/symbol/homo_sapiens/{symbol}` – stable ID, name, biotype, coordinates, canonical transcript. Used for the gene-annotation cross-check and to obtain the GRCh37 region for 1000 Genomes.
* `/vep/human/region/{chrom}:{start}-{end}:1/{allele}` – on-demand Variant Effect Predictor annotation (consequence, impact, amino-acid change, SIFT/PolyPhen) in the variant drawer.

## NCBI dbSNP / Variation Services
* Gene-level: `esearch db=snp term=<GENE>[gene]` + batched `esummary`. Each RefSNP has canonical SPDI alleles (GRCh38) and `global_mafs` entries such as `1000Genomes: A=0.027356/137` (allele = frequency / allele count). GeneLens uses the first available study in the order **ALFA → gnomAD genomes → 1000 Genomes 30x → 1000 Genomes → ExAC → TOPMed**; allele number is **derived** as count ÷ frequency (e.g. 137 / 0.027356 = 5,008 = 2 × 2,504) and every such record carries the QC flag `an_derived_from_study_frequency`. Alleles without a reported frequency keep AF empty (never zero). IUPAC ambiguity codes (e.g. `Y`) are rejected as invalid alleles. Capped at 25,000 RefSNPs per gene.
* Variant-level: `https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/{id}` – per-study allele and total counts, creation/update dates, merged rsIDs, ClinVar RCV links (variant drawer).

## IGSR / 1000 Genomes phase 3
* Population metadata: IGSR data-portal API (`POST /api/beta/population/_search`) and the phase 3 panel file `integrated_call_samples_v3.20130502.ALL.panel` (2,504 samples: AFR 661, AMR 347, EAS 504, EUR 503, SAS 489).
* Variants: `ALL.chr*.phase3_*.20130502.genotypes.vcf.gz` on `ftp.1000genomes.ebi.ac.uk` (GRCh37). GeneLens downloads the ~130 kB tabix index, locates the gene region via the linear index, and reads it with HTTP range requests (pure-Python BGZF reader – no native dependencies). Only INFO fields (AC, AN, AF, super-population AFs, VT) are kept; genotypes are discarded. HBB: 168 records in ~2 s; BRCA1: 2,057 records in ~3 s.
* Super-population AN = 2 × samples (phase 3 genotypes are complete on autosomes); population AC = round(AF × AN) and is flagged `population_ac_derived_from_af`. Symbolic structural alleles (`<DEL>`, `<CN0>` …) are skipped because they have no sequence to match.

## UCSC Genome Browser API
* `https://api.genome.ucsc.edu` – `/list/ucscGenomes` (assembly descriptions), `/getData/track` with `ncbiRefSeqSelect` (hg38) or `ncbiRefSeqCurated` (hg19) for RefSeq transcript coordinates, and `cytoBand` for the cytogenetic band. Used in the gene-annotation cross-check shown in the Command Center.

## Offline snapshots
`backend/data/snapshots/HBB_*.json.gz` are **real** gnomAD and ClinVar responses for HBB retrieved on 2026-11-10 (≈180 kB). They are used only when the live API is unreachable, and the dataset is then marked `offline_snapshot` with its original retrieval date in every view, report and export. Create more with `python -m scripts.create_snapshot --gene <SYMBOL>`.

## Test fixtures
`backend/tests/fixtures/sample_data.py` contains small **hand-built fixture records** (gene `TESTG`) that exercise edge cases (anchor-base indels, haplotypes, discordant duplicates, AN = 0). They are labelled `TEST FIXTURE` and are only used by the test suite – never shown as real data. All external services are stubbed in tests so the suite runs offline.

## Terms and citation
gnomAD and ClinVar make their data freely available for research. Check each provider's current terms of use before redistributing data, and cite them in any work that uses GeneLens output:
* gnomAD: Chen S, et al. Nature 625, 92–100 (2024) and Karczewski KJ, et al. Nature 581, 434–443 (2020); https://gnomad.broadinstitute.org/
* ClinVar: Landrum MJ, et al. Nucleic Acids Res 48, D835–D844 (2020); https://www.ncbi.nlm.nih.gov/clinvar/

## Custom datasets (Custom Dataset Lab)
Researchers can upload their own variant files. These are **not** an external source and are kept strictly apart from the datasets above:

| Aspect | Behaviour |
|---|---|
| Formats | CSV, TSV, TXT (delimiter detected), VCF, VCF.GZ (multi-allelic sites split per ALT; INFO AC/AN/AF/CLNSIG/GENEINFO read), JSON (a list of records, or an object containing one) |
| Size | Up to 200 MB per file, streamed to disk in 1 MB chunks (`backend/data/uploads/<id>/`) |
| Columns | Detected automatically from common names (chrom/pos/ref/alt, variant id `1-12345-A-G`, AC/AN/AF, gene, rsID, clinical significance, review status, population columns such as `AF_nfe` or `afr_AC`) and editable in a mapping UI |
| Assembly | Read only from explicit metadata (`##reference`, `##contig …assembly=`) or chosen by the user. **Never inferred from coordinates.** Unknown assembly disables ClinVar matching; assemblies are never mixed |
| Frequencies | AF = AC/AN when both exist (checked against a reported AF); otherwise a reported AF is kept and flagged `af_reported_without_counts`. Missing stays missing – never zero |
| Classifications | The file's own classifications are kept. ClinVar (E-utilities, genes taken from the mapped gene column, max 10 genes) is used either to **annotate** records without a classification or, when the file has one, only for a **concordance** comparison. Matching is by exact allele, then minimal representation – never by gene name or position alone |
| Labelling | Stored with `provenance = CUSTOM` and the dataset id; shown with a violet **CUSTOM DATA** badge; every export carries a CUSTOM notice |
| Outputs | Dashboard, cleaned CSV, analysis export (JSON/CSV), processing history |

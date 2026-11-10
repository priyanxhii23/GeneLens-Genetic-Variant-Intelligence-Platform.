export type Provenance = "REAL" | "SYNTHETIC" | "CUSTOM";
export type CoarseClass = "P_LP" | "VUS" | "B_LB" | "CONFLICTING" | "OTHER" | "NOT_IN_CLINVAR";

export interface AnalysisSummary {
  id: string; gene_symbol: string; dataset: string; reference_genome: string; clinvar_source: string;
  status: "queued" | "running" | "completed" | "failed"; stage: string | null; progress: number;
  error: string | null; real_count: number; synthetic_count: number; parameters: Record<string, unknown>;
  created_at: string; completed_at: string | null;
}
export interface DatasetMeta {
  source: string; dataset: string; release: string | null; reference_genome: string | null; access_mode: string;
  query: string | null; record_count: number; retrieved_at: string; notes: string | null;
}
export interface PopulationEntry { id: string; label?: string; ac: number; an: number; af: number | null; homozygote_count?: number }
export interface VariantRow {
  id: number; variant_key: string; provenance: Provenance; gene_symbol: string | null; chrom: string | null;
  pos: number | null; ref: string | null; alt: string | null; variant_type: string | null; rsid: string | null;
  consequence: string | null; hgvsc: string | null; hgvsp: string | null; name: string | null;
  ac: number | null; an: number | null; af: number | null; popmax_af: number | null; popmax_population: string | null;
  clinical_significance: string | null; classification: string | null; coarse_class: CoarseClass;
  review_status: string | null; gold_stars: number | null; match_status: string; match_confidence: number | null;
  in_gnomad: boolean; in_clinvar: boolean; qc_flags: string[] | null; clinvar_variation_id: string | null;
}
export interface VariantDetail extends VariantRow {
  populations: PopulationEntry[] | null; af_exome: number | null; af_genome: number | null;
  homozygote_count: number | null; conditions: string | null; submitter_count: number | null;
  last_evaluated: string | null; match_method: string | null; gnomad_filters: string[] | null;
  gnomad_flags: string[] | null; clinvar_allele_id: string | null;
  anomalies: AnomalyFlag[]; links?: { gnomad?: string; clinvar?: string };
  assembly?: string; frequency_source?: string | null;
}
export interface Page<T> { total: number; page: number; page_size: number; pages?: number; items: T[] }
export interface Describe { n: number; mean?: number; median?: number; std?: number | null; min?: number; max?: number; q1?: number; q3?: number; iqr?: number; log10?: Describe }
export interface StatTest {
  test: string; comparison?: string; variables?: string; ran: boolean; reason?: string; n?: number | Record<string, number>;
  statistic?: number | null; p_value?: number; p_adjusted_bh?: number; p_adjusted_bonferroni?: number;
  "significant_fdr_0.05"?: boolean; effect_size?: { name: string; value: number | null; magnitude?: string; ci95_conditional?: number[] | null; ci95_fisher_z?: number[]; common_language?: number };
  median_difference_log10?: number; median_difference_ci95?: number[]; assumptions?: Record<string, unknown>;
  explanation?: string; contingency_table?: { rows: string[]; columns: string[]; counts: number[][] };
  table?: { rows: string[]; columns: string[]; counts: number[][] }; dof?: number; warning?: string;
}
export interface Statistics {
  sample: { total_rows: number; matched_used: number; matched_with_af: number; include_ambiguous: boolean };
  descriptive: Record<string, Describe>; classification_counts: Record<string, number>; tests: StatTest[];
  multiple_testing: { method: string; m: number; explanation: string };
  proportions: { pathogenic_fraction_of_clinvar: { successes: number; n: number; estimate: number | null; ci95_wilson: number[] | null } };
  af_histogram: { edges: number[]; counts: Record<string, number[]> }; box_data: Record<string, number[]>;
  review_stars_by_class?: Record<string, Record<string, number>>;
  gnomad_presence_by_class?: Record<string, { in_gnomad: number; total: number }>;
}
export interface AnomalySummary { total: number; by_category: Record<string, number>; by_kind: Record<string, number>; by_priority: Record<string, number>; flagged_variants: number }
export interface AnomalyFlag {
  id?: number; variant_id: number | null; variant_key: string; provenance: Provenance; category: string;
  kind: "data_quality" | "biological_interest" | "statistical_outlier"; priority: "high" | "medium" | "low";
  score: number; evidence: Record<string, unknown>; explanation: string;
  headline?: string | null; reason?: string | null; why_it_matters?: string | null; recommendation?: string | null;
}
export interface Thresholds {
  pathogenic_af: number; pathogenic_popmax_af: number; ba1_af: number; rare_benign_af: number;
  low_an_fraction: number; mad_z: number; use_isolation_forest: boolean; isolation_contamination: number; seed: number;
}
export interface PopulationGroup { id: string; label: string; grpmax_eligible: boolean; variants_observed: number; total_ac: number; median_an: number | null; mean_an: number | null; missing: number; missing_fraction: number | null; by_class: Record<string, { observed: number; total_ac: number }> }
export interface PopulationSummary {
  populations: string[]; groups: PopulationGroup[]; n_variants: number; notes: string[];
  matrix: { variant_key: string; id: number; hgvsp: string | null; hgvsc: string | null; coarse_class: CoarseClass; clinical_significance: string | null; af: number; provenance: Provenance; populations: Record<string, { af: number | null; ac: number; an: number } | null> }[];
  pathogenic_popmax_distribution: Record<string, number>;
}
export interface ConstraintMetrics { [k: string]: number | string[] | null | undefined }
export interface Constraint {
  available: boolean; message?: string; metrics?: ConstraintMetrics; interpretation?: string[]; disclaimer?: string;
  observed_expected?: { class: string; observed: number; expected: number; oe: number; oe_lower: number; oe_upper: number; z: number }[];
  docs?: Record<string, { name: string; meaning: string; caveat: string }>; gene?: GeneInfo;
}
export interface GeneInfo { gene_id: string; symbol: string; name: string; chrom: string; start: number; stop: number; strand: string; canonical_transcript_id: string }
export interface Matching { frequency_source?: string | null; gnomad_records: number; clinvar_records: number; clinvar_with_allele_coordinates: number; status_counts: Record<string, number>; matched_variants: number; clinvar_match_rate: number | null; gnomad_annotated_rate: number | null }
export interface GeneAnnotation {
  genome: string; name?: string; cytoband?: string; note?: string; coordinates_agree_within_bp?: number | null;
  sources: Record<string, { chrom: string; start: number; end: number; ensembl_id?: string; biotype?: string;
    canonical_transcript?: string; transcripts?: { name: string; strand: string; tx_start: number; tx_end: number; exons: number }[] }>;
  ensembl_error?: string; ucsc_error?: string;
}
export interface Results {
  dataset?: { id: string; name: string; provider: string; assembly: string; data_type: string; frequency_source: string | null };
  gene_annotation?: GeneAnnotation;
  gene: GeneInfo; matching: Matching; statistics: Statistics; anomaly_summary: AnomalySummary; anomaly_thresholds: Thresholds;
  populations: PopulationSummary; constraint: Constraint;
  interpretation: { findings: string[]; limitations: string[]; disclaimer: string };
  qc: { flag_counts: Record<string, number>; records_with_flags: number }; runtime_seconds: number;
}
export interface AnalysisDetail { analysis: AnalysisSummary; datasets: DatasetMeta[]; results: Results | null }
export interface ExportRecord { id: string; analysis_id: string | null; synthetic_job_id: string | null; kind: string; filename: string; size_bytes: number; parameters: Record<string, unknown> | null; created_at: string }
export interface SourceStatus { gnomad: { available: boolean; detail: string; latency_ms?: number }; clinvar: { available: boolean; detail: string; latency_ms?: number }; clinvar_tsv: { available: boolean; detail: string } }
export interface SyntheticJob {
  id: string; provenance: "SYNTHETIC"; source_analysis_id: string | null; n_records: number; stored_records: number; seed: number;
  parameters: Record<string, unknown>; fitted_model: Record<string, unknown> & { source: string; note?: string };
  comparison: {
    distribution: null | { edges: number[]; classes: Record<string, { n_real: number; n_synthetic: number; real_hist: number[]; synthetic_hist: number[]; real_median_log10: number | null; synthetic_median_log10: number | null; ks?: { statistic: number; p_value: number } }>; class_proportions: Record<string, { real: number | null; synthetic: number | null }>; class_total_variation_distance: number | null; explanation: string };
    anomaly_engine_evaluation: { injected_unusual: number; injected_unusual_flagged: number; injected_conflicts: number; injected_conflicts_flagged: number; note: string };
    screen_summary: AnomalySummary;
  } | null;
  status: string; created_at: string; class_counts: Record<string, number>;
}
export interface Dashboard {
  recent: AnalysisSummary[];
  database: { real_records: number; synthetic_records: number; analyses: number; synthetic_jobs: number };
  analysis?: AnalysisSummary; datasets?: DatasetMeta[]; gene?: GeneInfo; matching?: Matching; anomaly_summary?: AnomalySummary;
  provenance?: ProvMode;
  groups?: Partial<Record<"REAL" | "SYNTHETIC", { total_records: number; gnomad_variants: number; clinvar_records: number; matched: number; pathogenic: number; benign: number; vus: number; conflicting: number; flagged: number; by_match_status: Record<string, number>; by_class: Record<string, number> }>>;
  metrics?: { total_records: number; gnomad_variants: number; clinvar_records: number; matched: number; pathogenic: number; benign: number; vus: number; conflicting: number; flagged: number; real: number; synthetic_linked: number; by_match_status: Record<string, number>; by_class: Record<string, number> };
}

// ---------------------------------------------------------------- upgrade types
export type ProvMode = "REAL" | "SYNTHETIC" | "BOTH";
export interface Groups<T> { mode: ProvMode; groups: Partial<Record<"REAL" | "SYNTHETIC", T | null>> }

export interface DatasetEntry {
  id: string; name: string; provider: string; assembly: string; release: string;
  data_type: "population_frequency" | "clinical_annotation" | "variant_catalogue";
  kind: string; source_ids: string[]; description: string; clinvar_sources: string[];
  status: "available" | "unavailable"; status_detail: string;
}
export interface SourceEntry {
  id: string; name: string; provider: string; method: string; endpoint: string; category: string;
  provides: string[]; used_for: string; homepage: string; available: boolean | null; detail: string | null;
  release: string | null; latency_ms: number | null; last_checked_at: string | null; last_success_at: string | null;
  last_retrieval_at: string | null; records_retrieved: number; last_error: string | null; last_error_at: string | null;
  pipeline?: TsvPipeline;
}
export interface TsvPipeline {
  source_reachable: boolean | null; remote_file_available: boolean | null; remote_size_mb: number | null; downloaded: boolean;
  local_size_mb: number | null; indexed_gene_extracts: number; indexed_genes: string[]; records_imported: number;
  download: { state: "idle" | "running" | "completed" | "failed"; bytes: number; total: number | null; error: string | null };
}
export interface GeneSuggestion {
  symbol: string; name: string | null; chrom: string | null; description: string | null; starter: boolean;
  analysed: number; offline_snapshot: boolean; data_status: string; compatible_datasets: string[];
  in_catalogue: boolean; ensembl_id?: string;
}
export interface FlagItem extends AnomalyFlag {
  clinical_significance: string | null; coarse_class: CoarseClass | null; af: number | null;
  hgvsp: string | null; hgvsc: string | null;
}
export interface Annotation {
  variant_key: string; genome: string;
  vep?: { most_severe_consequence: string; transcript: string; gene: string; consequences: string[]; impact: string;
          amino_acids: string | null; protein_position: number | null; sift: string | null; polyphen: string | null;
          colocated: string[]; n_transcripts: number };
  vep_error?: string;
  dbsnp?: { rsid: string; variant_type: string; created: string; updated: string; build: string;
            frequencies: { study: string; allele: string; ref: string; allele_count: number; total_count: number; af: number }[];
            clinvar_rcv: string[]; merged_rsids: string[] };
  dbsnp_error?: string;
}
export interface CompareGene {
  gene: string; status: "ok" | "missing"; message?: string; analysis_id?: string; completed_at?: string; sources?: string[];
  frequency_records?: number; clinvar_records?: number; matched?: number;
  class_counts?: Record<string, number>; selected_with_af?: number; above_threshold?: number;
  above_threshold_by_class?: Record<string, number>; median_af?: number | null;
  histogram?: { edges: number[]; counts: Record<string, number[]> }; pli?: number | null; loeuf?: number | null; mis_z?: number | null;
}
export interface CompareParams { genes: string[]; dataset: string; af_threshold: number; classes: string[]; min_stars: number; populations: string[] }
export interface WhatIfThresholds { pathogenic_af: number; pathogenic_popmax_af: number; ba1_af: number; rare_benign_af: number }
export interface WhatIfResult {
  baseline_thresholds: WhatIfThresholds; scenario_thresholds: WhatIfThresholds; explanation: string;
  total: { baseline: number; scenario: number; difference: number; percent_change: number | null };
  genes: { gene: string; status: string; baseline?: { total: number; by_category: Record<string, number> };
           scenario?: { total: number; by_category: Record<string, number> }; difference?: number;
           percent_change?: number | null; by_category_difference?: Record<string, number> }[];
}
export interface SavedComparison { id: string; name: string; genes: string[]; dataset: string; parameters: CompareParams; created_at: string;
  results?: { run: { genes: CompareGene[] } | null; whatif: WhatIfResult | null } }

// ---------------------------------------------------------------- Custom Dataset Lab
export type CustomStatus = "inspected" | "queued" | "processing" | "completed" | "failed";
export type Assembly = "GRCh37" | "GRCh38" | "unknown";
export interface CustomInspection {
  columns: string[]; row_count: number; preview: Record<string, string | number | null>[];
  suggested_mapping: Record<string, string | null>; field_labels: Record<string, string>;
  population_columns: Record<string, Partial<Record<"af" | "ac" | "an", string>>>;
  missing_by_column: Record<string, number>;
  assembly: { value: Assembly; source: string | null; evidence: string[]; note?: string }; issues: string[];
}
export interface CustomFlag { variant_id: number | null; variant_key: string; category: string; kind: string; priority: "high" | "medium" | "low"; headline: string; reason: string; why_it_matters: string; recommendation: string }
export interface CustomSummary {
  totals: { rows: number; valid: number; invalid: number; duplicates: number; unique_valid: number; records_with_missing_fields: number };
  missing_by_field: Record<string, number>; invalid_values: Record<string, number>; field_status: Record<string, string>;
  classification_distribution: Record<string, number>; variant_types: Record<string, number>; genes: Record<string, number>;
  af_distribution: { edges: number[]; counts: number[]; with_af: number; af_zero: number; af_missing: number };
  statistics: Statistics; populations: PopulationSummary | null;
  clinvar: { status: string; reason?: string; mode?: string; note?: string; genes_queried?: string[]; clinvar_records_retrieved?: number;
    matched_exact?: number; matched_normalized?: number; ambiguous?: number; no_clinvar_record?: number; errors?: { gene: string; message: string }[];
    concordance?: { compared: number; agree: number; disagree: number; agreement_rate: number | null; pairs: Record<string, number> } };
  quality: { qc_flag_counts: Record<string, number>; records_with_flags: number };
  anomaly_summary: AnomalySummary; anomalies: CustomFlag[]; runtime_seconds: number;
}
export interface CustomDataset {
  id: string; name: string; filename: string; file_format: string; size_bytes: number; assembly: Assembly;
  assembly_source: string | null; status: CustomStatus; stage: string | null; progress: number; error: string | null;
  created_at: string; updated_at: string; provenance: "CUSTOM"; row_count: number | null; has_cleaned: boolean;
  totals?: CustomSummary["totals"];
  inspection?: CustomInspection; mapping?: Record<string, string | null>; options?: { clinvar?: boolean };
  summary?: CustomSummary | null; history?: { at: string; action: string; detail: string | null }[];
}

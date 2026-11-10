export type Provenance = "REAL" | "SYNTHETIC";
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
}
export interface Thresholds {
  pathogenic_af: number; pathogenic_popmax_af: number; ba1_af: number; rare_benign_af: number;
  low_an_fraction: number; mad_z: number; use_isolation_forest: boolean; isolation_contamination: number; seed: number;
}
export interface PopulationGroup { id: string; label: string; grpmax_eligible: boolean; variants_observed: number; total_ac: number; median_an: number; mean_an: number; missing: number; missing_fraction: number | null; by_class: Record<string, { observed: number; total_ac: number }> }
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
export interface Matching { gnomad_records: number; clinvar_records: number; clinvar_with_allele_coordinates: number; status_counts: Record<string, number>; matched_variants: number; clinvar_match_rate: number | null; gnomad_annotated_rate: number | null }
export interface Results {
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
  metrics?: { total_records: number; gnomad_variants: number; clinvar_records: number; matched: number; pathogenic: number; benign: number; vus: number; conflicting: number; flagged: number; real: number; synthetic_linked: number; by_match_status: Record<string, number>; by_class: Record<string, number> };
}

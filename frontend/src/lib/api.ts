/** Thin typed wrapper around the GeneLens FastAPI backend (proxied at /api by Vite). */
import type {
  AnalysisDetail, AnalysisSummary, Constraint, Dashboard, ExportRecord, Page, PopulationSummary, SourceStatus,
  Statistics, SyntheticJob, Thresholds, VariantDetail, VariantRow, AnomalyFlag, AnomalySummary,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

type Query = Record<string, string | number | boolean | string[] | undefined | null>;

export function qs(params: Query = {}): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError("Cannot reach the GeneLens backend. Is it running on port 8000? (see README → Run)", 0);
  }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const body = await res.json(); msg = body.detail ?? msg; } catch { /* non-JSON */ }
    throw new ApiError(typeof msg === "string" ? msg : JSON.stringify(msg), res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string; analyses: number }>("/health"),
  sources: (refresh = false) => request<SourceStatus>(`/sources/status${qs({ refresh })}`),
  datasets: () => request<{ id: string; label: string; reference_genome: string; clinvar_sources: string[] }[]>("/datasets"),
  searchGenes: (q: string) => request<{ results: { ensembl_id: string; symbol: string }[]; error?: string }>(`/genes/search${qs({ q })}`),
  runAnalysis: (body: { gene: string; dataset: string; clinvar_source: string; include_ambiguous?: boolean; anomaly_thresholds?: Partial<Thresholds> }) =>
    post<AnalysisSummary>("/analysis/run", body),
  status: (id: string) => request<AnalysisSummary>(`/analysis/${id}/status`),
  analysis: (id: string) => request<AnalysisDetail>(`/analysis/${id}`),
  dashboard: (analysis_id?: string | null) => request<Dashboard>(`/dashboard${qs({ analysis_id })}`),
  statistics: (analysis_id: string, include_ambiguous?: boolean) => request<Statistics>(`/analysis/statistics${qs({ analysis_id, include_ambiguous })}`),
  populations: (analysis_id: string) => request<PopulationSummary>(`/analysis/populations${qs({ analysis_id })}`),
  constraint: (analysis_id: string) => request<Constraint>(`/analysis/constraint${qs({ analysis_id })}`),
  constraintCompare: (genes: string[]) => request<{ genes: { symbol: string; available: boolean; metrics?: Record<string, number>; error?: string; access_mode?: string }[]; docs: Constraint["docs"] }>(`/constraint/compare${qs({ genes: genes.join(",") })}`),
  variants: (params: Query) => request<Page<VariantRow>>(`/variants${qs(params)}`),
  variantExportUrl: (params: Query) => `/api/variants/export${qs(params)}`,
  variant: (id: number) => request<VariantDetail>(`/variants/${id}`),
  anomalies: (params: Query) => request<Page<AnomalyFlag> & { summary: AnomalySummary; thresholds: Thresholds }>(`/anomalies${qs(params)}`),
  detectAnomalies: (analysis_id: string, thresholds: Thresholds) => post<{ run_id: string; summary: AnomalySummary; thresholds: Thresholds }>("/anomalies/detect", { analysis_id, thresholds }),
  generateSynthetic: (body: Record<string, unknown>) => post<SyntheticJob>("/synthetic/generate", body),
  syntheticJobs: (source_analysis_id?: string) => request<{ id: string; n_records: number; seed: number; created_at: string; model_source: string; source_analysis_id: string | null }[]>(`/synthetic${qs({ source_analysis_id })}`),
  syntheticJob: (id: string) => request<SyntheticJob>(`/synthetic/${id}`),
  generateReport: (analysis_id: string, format: "pdf" | "csv") => post<ExportRecord>("/reports/generate", { analysis_id, format }),
  reports: (analysis_id?: string) => request<ExportRecord[]>(`/reports${qs({ analysis_id })}`),
  downloadUrl: (id: string) => `/api/reports/${id}/download`,
  history: () => request<(AnalysisSummary & { datasets: AnalysisDetail["datasets"]; matched: number | null; flags: number | null })[]>("/history"),
  historyDetail: (id: string) => request<AnalysisDetail & { exports: ExportRecord[]; synthetic_jobs: { id: string; n_records: number; seed: number; created_at: string }[] }>(`/history/${id}`),
  deleteAnalysis: (id: string) => request<void>(`/history/${id}`, { method: "DELETE" }),
};

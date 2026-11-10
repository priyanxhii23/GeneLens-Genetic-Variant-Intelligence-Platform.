/** Thin typed wrapper around the GeneLens FastAPI backend (proxied at /api by Vite). */
import type {
  AnalysisDetail, AnalysisSummary, Constraint, Dashboard, ExportRecord, Page, PopulationSummary, SourceStatus,
  Statistics, SyntheticJob, Thresholds, VariantDetail, VariantRow, AnomalySummary,
  Annotation, CompareGene, CompareParams, DatasetEntry, FlagItem, GeneSuggestion, Groups, ProvMode,
  SavedComparison, SourceEntry, WhatIfResult, WhatIfThresholds,
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

// ---------------------------------------------------------------------------
// Request de-duplication + short-lived response cache (GET only).
// * Identical GETs in flight share one network request (pages, StrictMode
//   double-mounts and sibling components no longer fire duplicates).
// * Successful GETs are reused for a short TTL so navigating back is instant.
// * Any write (POST/PATCH/DELETE) clears the cache, so data is never stale.
// ---------------------------------------------------------------------------
const inflight = new Map<string, Promise<unknown>>();
const cache = new Map<string, { at: number; data: unknown }>();
const ttlFor = (path: string) =>
  /^\/(datasets|sources)/.test(path) ? 60_000 : /status|\/custom-datasets/.test(path) ? 0 : 20_000;
export function clearApiCache() { cache.clear(); }

async function rawRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError("Cannot reach the GeneLens backend. Is it running on port 8000? (see README → Troubleshooting)", 0);
  }
  if (!res.ok) {
    let msg = `The server answered ${res.status} ${res.statusText}`;
    try { const body = await res.json(); if (typeof body.detail === "string") msg = body.detail; } catch { /* non-JSON */ }
    throw new ApiError(msg, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method !== "GET") {
    const out = await rawRequest<T>(path, init);
    cache.clear();
    return out;
  }
  const ttl = ttlFor(path);
  const hit = cache.get(path);
  if (hit && Date.now() - hit.at < ttl) return hit.data as T;
  const pending = inflight.get(path);
  if (pending) return pending as Promise<T>;
  const p = rawRequest<T>(path, init)
    .then((data) => { if (ttl > 0) cache.set(path, { at: Date.now(), data }); return data; })
    .finally(() => inflight.delete(path));
  inflight.set(path, p);
  return p;
}

const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string; analyses: number }>("/health"),
  sources: (refresh = false) => request<SourceStatus>(`/sources/status${qs({ refresh: refresh || undefined })}`),
  datasets: (refresh = false) => request<DatasetEntry[]>(`/datasets${qs({ refresh: refresh || undefined })}`),
  sourceList: (refresh = false) => request<SourceEntry[]>(`/sources${qs({ refresh: refresh || undefined })}`),
  refreshSource: (id: string) => request<SourceEntry>(`/sources/${id}/refresh`, { method: "POST" }),
  suggestGenes: (q: string, live = true) => request<{ query: string; results: GeneSuggestion[]; live_search: string | null }>(`/genes/suggest${qs({ q, live: live ? undefined : false })}`),
  annotation: (id: number) => request<Annotation>(`/variants/${id}/annotation`),
  statisticsFor: (analysis_id: string, provenance: ProvMode, include_ambiguous?: boolean) =>
    request<Groups<Statistics>>(`/analysis/statistics${qs({ analysis_id, provenance, include_ambiguous })}`),
  populationsFor: (analysis_id: string, provenance: ProvMode) =>
    request<Groups<PopulationSummary>>(`/analysis/populations${qs({ analysis_id, provenance })}`),
  compareRun: (p: CompareParams) => post<{ params: CompareParams; genes: CompareGene[]; note: string }>("/compare/run", p),
  compareWhatIf: (p: CompareParams & { baseline: Partial<WhatIfThresholds>; scenario: Partial<WhatIfThresholds> }) => post<WhatIfResult>("/compare/whatif", p),
  savedComparisons: () => request<SavedComparison[]>("/compare/saved"),
  savedComparison: (id: string) => request<SavedComparison>(`/compare/saved/${id}`),
  saveComparison: (body: { name: string; params: CompareParams; results: unknown; whatif: unknown }) => post<SavedComparison>("/compare/saved", body),
  deleteComparison: (id: string) => request<void>(`/compare/saved/${id}`, { method: "DELETE" }),
  comparisonExportUrl: (id: string) => `/api/compare/saved/${id}/export`,
  searchGenes: (q: string) => request<{ results: { ensembl_id: string; symbol: string }[]; error?: string }>(`/genes/search${qs({ q })}`),
  runAnalysis: (body: { gene: string; dataset: string; clinvar_source: string; include_ambiguous?: boolean; anomaly_thresholds?: Partial<Thresholds> }) =>
    post<AnalysisSummary>("/analysis/run", body),
  status: (id: string) => request<AnalysisSummary>(`/analysis/${id}/status`),
  analysis: (id: string) => request<AnalysisDetail>(`/analysis/${id}`),
  dashboard: (analysis_id?: string | null, provenance: ProvMode = "REAL") => request<Dashboard>(`/dashboard${qs({ analysis_id, provenance })}`),
  statistics: (analysis_id: string, include_ambiguous?: boolean) => request<Statistics>(`/analysis/statistics${qs({ analysis_id, include_ambiguous })}`),
  populations: (analysis_id: string) => request<PopulationSummary>(`/analysis/populations${qs({ analysis_id })}`),
  constraint: (analysis_id: string) => request<Constraint>(`/analysis/constraint${qs({ analysis_id })}`),
  constraintCompare: (genes: string[]) => request<{ genes: { symbol: string; available: boolean; metrics?: Record<string, number>; error?: string; access_mode?: string }[]; docs: Constraint["docs"] }>(`/constraint/compare${qs({ genes: genes.join(",") })}`),
  variants: (params: Query) => request<Page<VariantRow>>(`/variants${qs(params)}`),
  variantExportUrl: (params: Query) => `/api/variants/export${qs(params)}`,
  variant: (id: number) => request<VariantDetail>(`/variants/${id}`),
  anomalies: (params: Query) => request<Page<FlagItem> & { summary: AnomalySummary; thresholds: Thresholds; counts_by_provenance: Record<string, number> }>(`/anomalies${qs(params)}`),
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

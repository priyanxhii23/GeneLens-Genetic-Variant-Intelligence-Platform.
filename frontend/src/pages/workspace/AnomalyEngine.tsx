import { motion } from "framer-motion";
import { Bug, ChevronLeft, ChevronRight, Microscope, Radar, RotateCcw, Sigma } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { Disclaimer, ErrorState, Explain, HelixLoader, Metric, NeedsAnalysis, PageHeader, Panel, stagger } from "../../components/ui";
import { VariantDrawer } from "./VariantExplorer";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { fmtInt, token } from "../../lib/format";
import type { Thresholds } from "../../lib/types";

const KIND_META: Record<string, { label: string; color: string; icon: typeof Bug; desc: string }> = {
  biological_interest: { label: "Biological interest", color: "accent", icon: Microscope, desc: "Data look consistent, but the frequency–classification combination is unusual." },
  data_quality: { label: "Data quality", color: "violet", icon: Bug, desc: "The record may be incomplete, inconsistent or poorly covered." },
  statistical_outlier: { label: "Statistical outlier", color: "accent2", icon: Sigma, desc: "Unusual relative to peers; no interpretation implied." },
};
const DEFAULTS: Thresholds = { pathogenic_af: 0.005, pathogenic_popmax_af: 0.01, ba1_af: 0.05, rare_benign_af: 1e-5, low_an_fraction: 0.5, mad_z: 3.5, use_isolation_forest: true, isolation_contamination: 0.02, seed: 42 };
const FIELDS: { k: keyof Thresholds; label: string; help: string; step: number }[] = [
  { k: "pathogenic_af", label: "P/LP overall AF ≥", help: "Flag pathogenic variants at or above this overall frequency", step: 0.001 },
  { k: "pathogenic_popmax_af", label: "P/LP grpmax AF ≥", help: "…or this frequency in any eligible population", step: 0.001 },
  { k: "ba1_af", label: "BA1 frequency", help: "ACMG/AMP stand-alone benign frequency (5%)", step: 0.01 },
  { k: "rare_benign_af", label: "B/LB rarer than", help: "Flag benign variants below this AF", step: 0.000001 },
  { k: "low_an_fraction", label: "Low AN fraction", help: "AN below this fraction of the gene median", step: 0.05 },
  { k: "mad_z", label: "Robust z cut-off", help: "Median/MAD z-score of log10 AF within class", step: 0.5 },
  { k: "isolation_contamination", label: "IF contamination", help: "Expected outlier share for Isolation Forest", step: 0.01 },
];

export default function AnomalyEngine() {
  const { analysisId, detail, refresh } = useAnalysis();
  const [t, setT] = useState<Thresholds>(DEFAULTS);
  const [kind, setKind] = useState("");
  const [priority, setPriority] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => { if (detail?.results?.anomaly_thresholds) setT(detail.results.anomaly_thresholds); }, [detail?.results?.anomaly_thresholds]);
  useEffect(() => setPage(1), [kind, priority, category]);
  const res = useFetch(analysisId && detail?.results ? () => api.anomalies({ analysis_id: analysisId, kind, priority, category, page, page_size: 30 }) : null, [analysisId, kind, priority, category, page, version, detail?.results]);
  const summary = res.data?.summary;

  const catChart = useMemo(() => {
    if (!summary) return [];
    const items = Object.entries(summary.by_category).sort((a, b) => a[1] - b[1]);
    return [{ type: "bar" as const, orientation: "h" as const, y: items.map(([k]) => k.replace(/_/g, " ")), x: items.map(([, v]) => v),
      marker: { color: token("accent") }, text: items.map(([, v]) => fmtInt(v)), textposition: "outside" as const, cliponaxis: false,
      hovertemplate: "%{y}: %{x} flags<extra></extra>" }];
  }, [summary]);

  if (!analysisId) return <NeedsAnalysis />;
  const rerun = async (thr = t) => {
    setBusy(true); setErr(null);
    try { await api.detectAnomalies(analysisId, thr); setVersion((v) => v + 1); await refresh(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="06" title="Variant Anomaly Detection Engine"
        subtitle="Three screening layers – configurable rules, robust within-class outliers and an Isolation Forest – each flag carrying its category, triggering evidence, priority and a plain-language explanation." />
      <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
        <Panel eyebrow="configuration" title="Screening thresholds">
          <div className="space-y-3">
            {FIELDS.map((f) => (
              <label key={f.k} className="block text-xs text-muted" title={f.help}>{f.label}
                <input type="number" step={f.step} min={0} className="input mt-1 font-mono" value={t[f.k] as number}
                  onChange={(e) => setT({ ...t, [f.k]: Number(e.target.value) })} />
              </label>
            ))}
            <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={t.use_isolation_forest} onChange={(e) => setT({ ...t, use_isolation_forest: e.target.checked })} className="accent-[rgb(var(--accent))]" />Use Isolation Forest (seed {t.seed})</label>
            <div className="flex gap-2 pt-1">
              <button className="btn-primary flex-1" disabled={busy} onClick={() => rerun()}><Radar size={15} />{busy ? "Screening…" : "Run screening"}</button>
              <button className="btn-ghost !px-3" title="Reset to defaults" onClick={() => { setT(DEFAULTS); void rerun(DEFAULTS); }}><RotateCcw size={14} /></button>
            </div>
            {busy && <HelixLoader label="Screening variants" />}
            {err && <ErrorState message={err} />}
          </div>
        </Panel>
        <div className="space-y-6">
          {summary && (
            <motion.div variants={stagger} className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Metric label="Total flags" value={summary.total} />
              <Metric label="Flagged variants" value={summary.flagged_variants} tone="violet" />
              <Metric label="High priority" value={summary.by_priority.high ?? 0} tone="bad" />
              <Metric label="Biological interest" value={summary.by_kind.biological_interest ?? 0} tone="accent2" />
            </motion.div>
          )}
          <div className="grid gap-4 md:grid-cols-3">
            {Object.entries(KIND_META).map(([k, m]) => {
              const Icon = m.icon; const on = kind === k;
              return (
                <button key={k} onClick={() => setKind(on ? "" : k)} aria-pressed={on} className={`panel p-4 text-left transition-all hover:-translate-y-0.5 ${on ? `border-${m.color}/60` : ""}`}>
                  <div className="flex items-center justify-between"><Icon size={16} className={`text-${m.color}`} /><span className="data text-xl">{fmtInt(summary?.by_kind[k] ?? 0)}</span></div>
                  <div className="mt-2 text-sm font-medium">{m.label}</div><p className="mt-1 text-xs text-muted">{m.desc}</p>
                </button>
              );
            })}
          </div>
          <Panel eyebrow="by category" title="What triggered the flags">
            <Plot data={catChart} height={Math.max(220, catChart[0]?.y.length * 30 + 50 || 220)} layout={{ margin: { l: 210, r: 50, t: 8, b: 30 }, showlegend: false }} />
          </Panel>
        </div>
      </div>

      <Panel eyebrow="investigation queue" title="Flags ordered by priority" actions={<>
        <select className="input !w-auto !py-1 text-xs" value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Priority"><option value="">All priorities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
        <select className="input !w-auto !py-1 text-xs" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category"><option value="">All categories</option>{Object.keys(summary?.by_category ?? {}).map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}</select>
      </>}>
        {res.error && <ErrorState message={res.error} onRetry={res.reload} />}
        <ul className="space-y-2">
          {res.data?.items.map((f) => {
            const km = KIND_META[f.kind];
            return (
              <li key={f.id} className="rounded-xl border border-line bg-raised/40 p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className={`chip ${f.priority === "high" ? "border-bad/40 text-bad" : f.priority === "medium" ? "border-warn/40 text-warn" : "border-line text-muted"}`}>{f.priority}</span>
                  <span className={`chip border-${km.color}/40 text-${km.color}`}>{km.label}</span>
                  <span className="font-medium">{f.category.replace(/_/g, " ")}</span>
                  <button className="ml-auto font-mono text-accent underline decoration-dotted" onClick={() => f.variant_id && setOpen(f.variant_id)}>{f.variant_key}</button>
                </div>
                <p className="mt-2 text-sm text-muted">{f.explanation}</p>
                <details className="mt-2 text-xs"><summary className="cursor-pointer text-faint">triggering evidence · score {f.score.toFixed(2)}</summary>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-bg/60 p-3 font-mono text-[11px] text-muted scrollbar-thin">{JSON.stringify(f.evidence, null, 2)}</pre></details>
              </li>
            );
          })}
        </ul>
        {res.data && (
          <div className="mt-4 flex items-center justify-between text-sm text-muted">
            <span>{fmtInt(res.data.total)} flags</span>
            <div className="flex gap-2">
              <button className="btn-ghost !px-2 !py-1" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={15} /></button>
              <button className="btn-ghost !px-2 !py-1" disabled={page * 30 >= res.data.total} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={15} /></button>
            </div>
          </div>
        )}
      </Panel>
      <Explain>
        <p><b>Rule-based screening</b> encodes explicit, adjustable criteria (e.g. a P/LP variant with AF ≥ 0.5%).</p>
        <p><b>Robust outliers</b> use the median and median absolute deviation of log10 AF within each class – resistant to the skew that breaks mean/SD z-scores.</p>
        <p><b>Isolation Forest</b> isolates points with random splits; points isolated in few splits have unusual feature combinations. It is seeded for reproducibility.</p>
        <p>A high-frequency pathogenic variant can be entirely genuine – e.g. recessive carrier alleles or the sickle-cell allele, maintained by heterozygote advantage against malaria.</p>
      </Explain>
      <Disclaimer compact />
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

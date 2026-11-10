import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Bug, ChevronDown, ChevronLeft, ChevronRight, Compass, Microscope, Radar, RotateCcw, Sigma } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ClassBadge, Disclaimer, ErrorState, Guide, GuideItem, HelixLoader, Metric, NeedsAnalysis, PageHeader, Panel, PriorityBadge, ProvenanceBadge, stagger, Term } from "../../components/ui";
import { useProvenance } from "../../lib/provenance";
import { VariantDrawer } from "./VariantExplorer";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { fmtAF, fmtInt, token } from "../../lib/format";
import type { FlagItem, Thresholds } from "../../lib/types";

function FlagCard({ f, onOpen, index }: { f: FlagItem; onOpen: () => void; index: number }) {
  const [open, setOpen] = useState(f.priority === "high");
  const km = KIND_META[f.kind];
  const ring = f.priority === "high" ? "border-bad/40 hover:shadow-[0_0_0_1px_rgb(var(--bad)/0.4),0_10px_30px_-14px_rgb(var(--bad)/0.5)]"
    : f.priority === "medium" ? "border-warn/30 hover:shadow-[0_0_0_1px_rgb(var(--warn)/0.35),0_10px_30px_-14px_rgb(var(--warn)/0.45)]" : "hover:border-accent/40";
  return (
    <motion.li layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay: Math.min(index, 12) * 0.035 }}
      className={`panel overflow-hidden transition-shadow ${ring}`}>
      <span className={`absolute inset-y-0 left-0 w-1 ${f.priority === "high" ? "bg-bad" : f.priority === "medium" ? "bg-warn" : "bg-line"}`} aria-hidden />
      <button className="w-full px-5 pb-3 pt-4 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <div className="flex flex-wrap items-center gap-2">
          <PriorityBadge p={f.priority} />
          <span className={`chip border-${km.color}/40 text-${km.color}`}>{km.label}</span>
          {f.coarse_class && <ClassBadge cls={f.coarse_class} label={f.clinical_significance} />}
          <ProvenanceBadge p={f.provenance} />
          <span className="ml-auto font-mono text-[13px] text-muted">{f.variant_key}</span>
        </div>
        <div className="mt-2.5 flex items-start gap-3">
          <div className="flex-1">
            <div className="eyebrow !text-[12px]">Reason</div>
            <h4 className="font-display text-[21px] leading-snug">{f.headline ?? f.category.replace(/_/g, " ")}</h4>
            <p className="insight-reason mt-1 !text-[17px] !font-medium">{f.reason ?? f.explanation}</p>
          </div>
          <ChevronDown size={18} className={`mt-1 shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3 }} className="overflow-hidden">
            <div className="grid gap-4 border-t border-line/70 px-5 py-4 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[14px] font-bold">Why this matters</div>
                <p className="insight-detail">{f.why_it_matters ?? f.explanation}</p>
              </div>
              <div>
                <div className="mb-1 flex items-center gap-1.5 text-[14px] font-bold"><Compass size={14} className="text-accent" />Recommended investigation</div>
                <p className="insight-detail">{f.recommendation ?? "Inspect the full variant record."}</p>
                {(f.af !== null || f.hgvsp) && <p className="meta mt-2">{f.hgvsp ? `${f.hgvsp} · ` : ""}AF {fmtAF(f.af)}</p>}
              </div>
            </div>
            <div className="flex justify-end px-5 pb-4">
              <button className="btn-ghost !py-1.5 text-[13px]" onClick={onOpen} disabled={!f.variant_id}>Full variant details <ArrowUpRight size={14} /></button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

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
  const { mode } = useProvenance();
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
  useEffect(() => setPage(1), [kind, priority, category, mode]);
  const res = useFetch(analysisId && detail?.results ? () => api.anomalies({ analysis_id: analysisId, kind, priority, category, page, page_size: 30, provenance: mode }) : null, [analysisId, kind, priority, category, page, version, detail?.results, mode]);
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
        subtitle="Three screening layers – configurable rules, robust within-class outliers and an Isolation Forest – each flag explained in plain language with a recommended next step." />
      <div className="layout-aside">
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
            <motion.div variants={stagger} className="layout-metrics">
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
                  <div className="mt-2 text-sm font-medium">{m.label}</div><p className="mt-1 text-[13px] text-muted">{m.desc}</p>
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
        <ul className="space-y-3">
          {res.data?.items.map((f, i) => <FlagCard key={f.id} f={f} index={i} onOpen={() => f.variant_id && setOpen(f.variant_id)} />)}
          {res.data && res.data.items.length === 0 && <li className="py-6 text-center text-muted">No flags for this selection{mode !== "REAL" ? " – synthetic flags exist only after a synthetic dataset is generated from this analysis" : ""}.</li>}
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
      <Guide title="How to read the anomaly engine">
        <GuideItem term="Three kinds of flag"><b>Biological interest</b>: the data look consistent, but the frequency–classification combination is unusual. <b>Data quality</b>: the record may be incomplete or inconsistent. <b>Statistical outlier</b>: unusual compared with similar variants – no interpretation implied.</GuideItem>
        <GuideItem term="Priority">Priority orders the review queue: <b>High</b> (e.g. a pathogenic variant above the 5% <Term k="BA1">BA1</Term> level), <b>Medium</b>, <b>Low</b>. It reflects how unusual the observation is, not how likely the classification is to be wrong.</GuideItem>
        <GuideItem term="Rule-based screening">Explicit, adjustable criteria – for example "a <Term k="P/LP">P/LP</Term> variant with <Term k="AF">AF</Term> ≥ 0.5%". Change the thresholds on the left and press <b>Run screening</b>.</GuideItem>
        <GuideItem term={<>Robust outliers and <Term k="Isolation Forest">Isolation Forest</Term></>}>Outliers use the median and <Term k="MAD">MAD</Term> of log-frequency within each class, which extreme values cannot distort. The Isolation Forest is a seeded machine-learning model that finds uncommon combinations of features.</GuideItem>
        <GuideItem term="What not to conclude">A flag is <b>never</b> a statement that a variant is misclassified. Example: the sickle-cell allele is pathogenic yet common in some populations because carriers are protected against malaria (balancing selection).</GuideItem>
        <GuideItem term="Where are the numbers behind a flag?">Each card states the values and thresholds that triggered it in plain language. Open <b>Full variant details</b> to see every field of the record – frequencies, counts, classification, review status and how it was matched.</GuideItem>
      </Guide>
      <Disclaimer compact />
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "../../components/Plot";
import { ClassBadge, Disclaimer, ErrorState, Explain, NeedsAnalysis, PageHeader, Panel, Stars, stagger, Tabs } from "../../components/ui";
import { VariantDrawer } from "./VariantExplorer";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, FINE_LABELS, fmtAF, fmtInt, MAIN_CLASSES, token } from "../../lib/format";
import type { CoarseClass } from "../../lib/types";

const FINE_ORDER = ["pathogenic", "pathogenic_likely_pathogenic", "likely_pathogenic", "uncertain_significance",
  "likely_benign", "benign_likely_benign", "benign", "conflicting", "other", "not_provided"];
const FINE_TO_COARSE: Record<string, CoarseClass> = {
  pathogenic: "P_LP", likely_pathogenic: "P_LP", pathogenic_likely_pathogenic: "P_LP", uncertain_significance: "VUS",
  likely_benign: "B_LB", benign: "B_LB", benign_likely_benign: "B_LB", conflicting: "CONFLICTING", other: "OTHER", not_provided: "OTHER",
};

export default function PathogenicityLab() {
  const { analysisId, detail } = useAnalysis();
  const [view, setView] = useState<"box" | "hist">("box");
  const [open, setOpen] = useState<number | null>(null);
  const stats = detail?.results?.statistics;
  const conflicting = useFetch(analysisId ? () => api.variants({ analysis_id: analysisId, coarse_class: ["CONFLICTING"], sort: "af", order: "desc", page_size: 12 }) : null, [analysisId]);
  const flags = useFetch(analysisId && detail?.results ? () => api.anomalies({ analysis_id: analysisId, kind: "biological_interest", page_size: 200 }) : null, [analysisId, detail?.results]);

  const fineBar = useMemo(() => {
    if (!stats) return [];
    const keys = FINE_ORDER.filter((k) => stats.classification_counts[k]).reverse();
    return [{ type: "bar" as const, orientation: "h" as const, y: keys.map((k) => FINE_LABELS[k]), x: keys.map((k) => stats.classification_counts[k]),
      marker: { color: keys.map((k) => token(CLASS_META[FINE_TO_COARSE[k]].color)) }, text: keys.map((k) => fmtInt(stats.classification_counts[k])),
      textposition: "outside" as const, cliponaxis: false, hovertemplate: "%{y}: %{x:,} ClinVar records<extra></extra>" }];
  }, [stats]);

  const boxes = useMemo(() => stats ? MAIN_CLASSES.filter((c) => stats.box_data[c]?.length).map((c) => ({
    type: "box" as const, name: `${CLASS_META[c].short} (n=${stats.box_data[c].length})`, y: stats.box_data[c].map((v) => Math.log10(v)),
    marker: { color: token(CLASS_META[c].color), size: 4 }, line: { width: 1.5 }, boxpoints: "suspectedoutliers" as const,
    hovertemplate: "log10 AF %{y:.2f}<extra>%{fullData.name}</extra>",
  })) : [], [stats]);

  const hist = useMemo(() => {
    if (!stats) return [];
    const e = stats.af_histogram.edges;
    const mids = e.slice(0, -1).map((x, i) => (x + e[i + 1]) / 2);
    return MAIN_CLASSES.filter((c) => stats.af_histogram.counts[c]?.some((n) => n > 0)).map((c) => ({
      type: "scatter" as const, mode: "lines" as const, name: CLASS_META[c].short, x: mids, y: stats.af_histogram.counts[c],
      line: { color: token(CLASS_META[c].color), width: 2, shape: "spline" as const }, hovertemplate: "log10 AF ≈ %{x:.2f}: %{y} variants<extra>%{fullData.name}</extra>",
    }));
  }, [stats]);

  const reviewBars = useMemo(() => {
    const r = stats?.review_stars_by_class;
    if (!r) return [];
    const stars = ["0", "1", "2", "3", "4"];
    const shades = [0.25, 0.45, 0.65, 0.85, 1];
    return stars.map((s, i) => ({
      type: "bar" as const, name: `${s}★`, x: MAIN_CLASSES.map((c) => CLASS_META[c].short),
      y: MAIN_CLASSES.map((c) => { const tot = Object.values(r[c] ?? {}).reduce((a, b) => a + b, 0); return tot ? (r[c]?.[s] ?? 0) / tot : 0; }),
      marker: { color: token("accent", shades[i]), line: { color: token("surface"), width: 2 } },
      hovertemplate: `%{x}: %{y:.1%} with ${s}★<extra></extra>`,
    }));
  }, [stats]);

  if (!analysisId) return <NeedsAnalysis />;
  if (!stats) return <Panel><p className="text-sm text-muted">Results not available yet – wait for the analysis to complete.</p></Panel>;
  const unusual = (flags.data?.items ?? []).filter((f) => ["frequent_pathogenic", "ba1_frequency_non_benign", "rare_benign"].includes(f.category));
  const presence = stats.gnomad_presence_by_class;

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="03" title="Pathogenicity Intelligence Lab"
        subtitle="How do allele frequencies differ between pathogenic, likely pathogenic, uncertain, likely benign and benign variants? Frequencies use matched variants only (exact + normalized matches with gnomAD AF > 0)." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel eyebrow="ClinVar · REAL" title="Classification distribution">
          <Plot data={fineBar} height={320} layout={{ margin: { l: 190, r: 50, t: 8, b: 36 }, showlegend: false, xaxis: { title: { text: "records" } } }} />
        </Panel>
        <Panel eyebrow="matched variants" title="Frequency by classification" actions={<Tabs value={view} onChange={setView} options={[{ value: "box", label: "Box plot" }, { value: "hist", label: "Distribution" }]} />}>
          {view === "box"
            ? <Plot data={boxes} height={320} layout={{ yaxis: { title: { text: "log10(allele frequency)" } }, showlegend: false, margin: { l: 60, r: 10, t: 8, b: 40 } }} />
            : <Plot data={hist} height={320} layout={{ xaxis: { title: { text: "log10(allele frequency)" } }, yaxis: { title: { text: "variants" } }, hovermode: "x unified" }} />}
        </Panel>
      </div>

      <Panel eyebrow="descriptive statistics" title="Allele frequency summary per class">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full min-w-[760px]">
            <thead><tr>{["Class", "n (with AF)", "In gnomAD / ClinVar", "Median AF", "Mean AF", "Q1", "Q3", "Min", "Max", "Median log10 AF"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
            <tbody>{MAIN_CLASSES.map((c) => {
              const d = stats.descriptive[c];
              return (
                <tr key={c}>
                  <td className="table-cell"><ClassBadge cls={c} /></td>
                  <td className="table-cell data">{fmtInt(d?.n)}</td>
                  <td className="table-cell data text-xs">{presence ? `${fmtInt(presence[c]?.in_gnomad)} / ${fmtInt(presence[c]?.total)}` : "—"}</td>
                  {(["median", "mean", "q1", "q3", "min", "max"] as const).map((k) => <td key={k} className="table-cell data text-xs">{fmtAF(d?.[k])}</td>)}
                  <td className="table-cell data text-xs">{d?.log10?.median?.toFixed(2) ?? "—"}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-faint">Variants absent from gnomAD are excluded from AF statistics – absence is not evidence of AF = 0. Group comparisons with p-values live in the Statistics Studio.</p>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel eyebrow="review status" title="ClinVar review stars by class">
          <Plot data={reviewBars} height={280} layout={{ barmode: "stack", bargap: 0.35, yaxis: { title: { text: "share of records" }, tickformat: ".0%" } }} />
        </Panel>
        <Panel eyebrow="conflicting interpretations" title="Submitters disagree" actions={<Link className="text-xs text-accent underline decoration-dotted" to="/workspace/variants">all in explorer</Link>}>
          {conflicting.error && <ErrorState message={conflicting.error} />}
          <ul className="divide-y divide-line/70">
            {conflicting.data?.items.map((v) => (
              <li key={v.id}><button className="flex w-full items-center gap-3 py-2 text-left text-sm hover:text-accent" onClick={() => setOpen(v.id)}>
                <span className="flex-1 truncate font-mono text-xs">{v.hgvsp ?? v.name ?? v.variant_key}</span>
                <span className="data text-xs text-muted">AF {fmtAF(v.af)}</span><Stars n={v.gold_stars} />
              </button></li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-faint">{fmtInt(conflicting.data?.total)} conflicting records in this gene.</p>
        </Panel>
      </div>

      <Panel eyebrow="explainable flags" title="Unusual frequency–classification combinations">
        {flags.error && <ErrorState message={flags.error} />}
        {unusual.length === 0 && !flags.loading && <p className="text-sm text-muted">No unusual combinations under the current thresholds (adjust them in the Anomaly Engine).</p>}
        <div className="grid gap-3 md:grid-cols-2">
          {unusual.slice(0, 10).map((f) => (
            <button key={`${f.variant_key}-${f.category}`} onClick={() => f.variant_id && setOpen(f.variant_id)} className="rounded-xl border border-line bg-raised/50 p-4 text-left transition-colors hover:border-accent/40">
              <div className="flex flex-wrap items-center gap-2 text-xs"><span className="font-mono">{f.variant_key}</span>
                <span className={`chip ${f.priority === "high" ? "border-bad/40 text-bad" : f.priority === "medium" ? "border-warn/40 text-warn" : "border-line text-muted"}`}>{f.priority}</span>
                <span className="text-muted">{f.category.replace(/_/g, " ")}</span></div>
              <p className="mt-2 text-sm text-muted">{f.explanation}</p>
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-faint">{unusual.length} flags shown from {fmtInt(flags.data?.total)} biological-interest flags. A flag is a prompt for review, never a statement that a variant is misclassified.</p>
      </Panel>
      <Explain>
        <p><b>Why log scale?</b> Allele frequencies span six orders of magnitude (one in a million to common). log10(AF) = −5 means 1 in 100,000 chromosomes.</p>
        <p><b>Box plots</b> show the median (line), the middle 50 % of variants (box) and suspected outliers (dots).</p>
        <p><b>Circularity:</b> population frequency is itself evidence used when classifying variants (ACMG/AMP BA1/BS1/PM2), so frequency differences between classes are partly expected by construction.</p>
      </Explain>
      <Disclaimer compact />
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

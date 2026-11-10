import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "../../components/Plot";
import { ClassBadge, Disclaimer, ErrorState, Guide, GuideItem, HelixLoader, Insight, NeedsAnalysis, PageHeader, Panel, PriorityBadge, ProvenanceBadge, Stars, stagger, Tabs, Term } from "../../components/ui";
import { VariantDrawer } from "./VariantExplorer";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, FINE_LABELS, fmtAF, fmtInt, MAIN_CLASSES, token } from "../../lib/format";
import { useProvenance } from "../../lib/provenance";
import type { CoarseClass, Statistics } from "../../lib/types";

const FINE_ORDER = ["pathogenic", "pathogenic_likely_pathogenic", "likely_pathogenic", "uncertain_significance",
  "likely_benign", "benign_likely_benign", "benign", "conflicting", "other", "not_provided"];
const FINE_TO_COARSE: Record<string, CoarseClass> = {
  pathogenic: "P_LP", likely_pathogenic: "P_LP", pathogenic_likely_pathogenic: "P_LP", uncertain_significance: "VUS",
  likely_benign: "B_LB", benign: "B_LB", benign_likely_benign: "B_LB", conflicting: "CONFLICTING", other: "OTHER", not_provided: "OTHER",
};
type G = "REAL" | "SYNTHETIC";
const isSyn = (g: G) => g === "SYNTHETIC";

export default function PathogenicityLab() {
  const { analysisId, detail } = useAnalysis();
  const { mode } = useProvenance();
  const [view, setView] = useState<"box" | "hist">("box");
  const [open, setOpen] = useState<number | null>(null);
  const st = useFetch(analysisId && detail?.results ? () => api.statisticsFor(analysisId, mode) : null, [analysisId, mode, detail?.results]);
  const groups = (Object.entries(st.data?.groups ?? {}).filter(([, v]) => v) as [G, Statistics][]);
  const conflicting = useFetch(analysisId ? () => api.variants({ analysis_id: analysisId, provenance: mode, coarse_class: ["CONFLICTING"], sort: "af", order: "desc", page_size: 12 }) : null, [analysisId, mode]);
  const flags = useFetch(analysisId && detail?.results ? () => api.anomalies({ analysis_id: analysisId, kind: "biological_interest", provenance: mode, page_size: 200 }) : null, [analysisId, detail?.results, mode]);

  const fineBar = useMemo(() => groups.map(([g, s]) => {
    const keys = FINE_ORDER.filter((k) => groups.some(([, x]) => x.classification_counts[k])).reverse();
    return {
      type: "bar" as const, orientation: "h" as const, name: isSyn(g) ? "Synthetic" : "Real", y: keys.map((k) => FINE_LABELS[k]),
      x: keys.map((k) => s.classification_counts[k] ?? 0),
      marker: isSyn(g) ? { color: token("pink", 0.22), line: { color: token("pink"), width: 1.5 } } : { color: keys.map((k) => token(CLASS_META[FINE_TO_COARSE[k]].color)) },
      text: keys.map((k) => fmtInt(s.classification_counts[k] ?? 0)), textposition: "outside" as const, cliponaxis: false,
      hovertemplate: `%{y}: %{x:,} records<extra>${g}</extra>`,
    };
  }), [st.data]); // eslint-disable-line

  const boxes = useMemo(() => groups.flatMap(([g, s]) => MAIN_CLASSES.filter((c) => s.box_data[c]?.length).map((c) => ({
    type: "box" as const, name: `${CLASS_META[c].short}${mode === "BOTH" ? (isSyn(g) ? " · syn" : " · real") : ""}`,
    y: s.box_data[c].map((v) => Math.log10(v)), legendgroup: g, offsetgroup: g,
    marker: { color: isSyn(g) ? token("pink") : token(CLASS_META[c].color), size: 4 },
    fillcolor: isSyn(g) ? token("pink", 0.12) : token(CLASS_META[c].color, 0.35), line: { width: 1.5, color: isSyn(g) ? token("pink") : token(CLASS_META[c].color) },
    boxpoints: "suspectedoutliers" as const, hovertemplate: `log10 AF %{y:.2f}<extra>${g} ${CLASS_META[c].short} (n=${s.box_data[c].length})</extra>`,
  }))), [st.data, mode]); // eslint-disable-line

  const hist = useMemo(() => groups.flatMap(([g, s]) => {
    const e = s.af_histogram.edges;
    const mids = e.slice(0, -1).map((x, i) => (x + e[i + 1]) / 2);
    return MAIN_CLASSES.filter((c) => s.af_histogram.counts[c]?.some((n) => n > 0)).map((c) => ({
      type: "scatter" as const, mode: "lines" as const, name: `${CLASS_META[c].short}${isSyn(g) ? " (syn)" : ""}`, x: mids, y: s.af_histogram.counts[c],
      line: { color: token(CLASS_META[c].color), width: 2, shape: "spline" as const, dash: isSyn(g) ? "dash" as const : "solid" as const },
      hovertemplate: `log10 AF ≈ %{x:.2f}: %{y} variants<extra>${g}</extra>`,
    }));
  }), [st.data]); // eslint-disable-line

  const reviewBars = useMemo(() => {
    const r = st.data?.groups.REAL?.review_stars_by_class;
    if (!r) return [];
    const shades = [0.25, 0.45, 0.65, 0.85, 1];
    return ["0", "1", "2", "3", "4"].map((s, i) => ({
      type: "bar" as const, name: `${s}★`, x: MAIN_CLASSES.map((c) => CLASS_META[c].short),
      y: MAIN_CLASSES.map((c) => { const tot = Object.values(r[c] ?? {}).reduce((a, b) => a + b, 0); return tot ? (r[c]?.[s] ?? 0) / tot : 0; }),
      marker: { color: token("accent", shades[i]), line: { color: token("surface"), width: 2 } }, hovertemplate: `%{x}: %{y:.1%} with ${s}★<extra></extra>`,
    }));
  }, [st.data]);

  if (!analysisId) return <NeedsAnalysis />;
  const primary = groups[0]?.[1];
  const d = primary?.descriptive;
  const unusual = (flags.data?.items ?? []).filter((f) => ["frequent_pathogenic", "ba1_frequency_non_benign", "rare_benign"].includes(f.category));
  const ratio = d?.P_LP?.median && d?.B_LB?.median ? d.B_LB.median / d.P_LP.median : null;

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="03" title="Pathogenicity Intelligence Lab"
        subtitle="How do allele frequencies differ between pathogenic, likely pathogenic, uncertain, likely benign and benign variants? Frequencies use matched variants only (exact + normalized matches with AF > 0)." />
      {st.loading && <HelixLoader label="Loading classification statistics" />}
      {st.error && <ErrorState message={st.error} onRetry={st.reload} />}
      {primary && d && (
        <Insight label={`Main finding · ${groups[0][0].toLowerCase()} data`}
          reason={d.P_LP?.n && d.B_LB?.n
            ? `The typical benign/likely benign variant is ${ratio && ratio >= 1 ? `${ratio.toFixed(ratio >= 10 ? 0 : 1)}× more` : "not more"} frequent than the typical pathogenic/likely pathogenic variant (median AF ${fmtAF(d.B_LB.median)} vs ${fmtAF(d.P_LP.median)}).`
            : "There are not enough matched pathogenic and benign variants with frequencies to compare their typical frequencies."}>
          <p>Each <b>median</b> is the middle frequency of variants in that class that were found in the frequency dataset ({fmtInt(d.P_LP?.n)} P/LP and {fmtInt(d.B_LB?.n)} B/LB variants). Pathogenic variants for rare diseases are usually rare, so benign variants often have higher frequencies – but because <b>frequency is itself evidence used to classify variants</b>, part of this difference is built in by design. Whether the difference is statistically meaningful is tested in the <Link to="/workspace/statistics" className="font-semibold text-accent underline">Statistics Studio</Link>.</p>
        </Insight>
      )}
      <div className="layout-halves">
        <Panel eyebrow={`ClinVar classifications · ${mode.toLowerCase()}`} title="Classification distribution">
          <Plot data={fineBar} height={340} layout={{ margin: { l: 190, r: 60, t: mode === "BOTH" ? 36 : 8, b: 36 }, showlegend: mode === "BOTH", barmode: "group", xaxis: { title: { text: "records" } } }} />
        </Panel>
        <Panel eyebrow="matched variants" title="Frequency by classification" actions={<Tabs value={view} onChange={setView} options={[{ value: "box", label: "Box plot" }, { value: "hist", label: "Distribution" }]} />}>
          {view === "box"
            ? <Plot data={boxes} height={340} layout={{ yaxis: { title: { text: "log10(allele frequency)" } }, showlegend: false, boxmode: mode === "BOTH" ? "group" : undefined, margin: { l: 60, r: 10, t: 8, b: 48 } }} />
            : <Plot data={hist} height={340} layout={{ xaxis: { title: { text: "log10(allele frequency)" } }, yaxis: { title: { text: "variants" } }, hovermode: "x unified" }} />}
          {mode === "BOTH" && <p className="meta">Synthetic data: pink outlined boxes / dashed lines. Groups are computed separately.</p>}
        </Panel>
      </div>

      {groups.map(([g, s]) => (
        <Panel key={g} eyebrow={`descriptive statistics · ${g.toLowerCase()}`} title={<span className="flex items-center gap-2">Allele frequency summary per class <ProvenanceBadge p={g} /></span>}>
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full min-w-[760px]">
              <thead><tr>{["Class", "n (with AF)", "Median AF", "Mean AF", "Q1", "Q3", "Min", "Max", "Median log10 AF"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
              <tbody>{MAIN_CLASSES.map((c) => {
                const x = s.descriptive[c];
                return (
                  <tr key={c} className="transition-colors hover:bg-raised/50">
                    <td className="table-cell"><ClassBadge cls={c} /></td>
                    <td className="table-cell data">{fmtInt(x?.n)}</td>
                    {(["median", "mean", "q1", "q3", "min", "max"] as const).map((k) => <td key={k} className="table-cell data text-[13px]">{fmtAF(x?.[k])}</td>)}
                    <td className="table-cell data text-[13px]">{x?.log10?.median?.toFixed(2) ?? "—"}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        </Panel>
      ))}

      <div className="layout-halves">
        <Panel eyebrow="review status · real data" title="ClinVar review stars by class">
          {mode === "SYNTHETIC" ? <p className="text-muted">Synthetic records carry no review stars – GeneLens never fabricates clinical evidence.</p>
            : <Plot data={reviewBars} height={290} layout={{ barmode: "stack", bargap: 0.35, yaxis: { title: { text: "share of records" }, tickformat: ".0%" } }} />}
        </Panel>
        <Panel eyebrow="conflicting interpretations" title="Submitters disagree" actions={<Link className="text-[13px] font-semibold text-accent underline decoration-dotted" to="/workspace/variants">all in explorer</Link>}>
          {conflicting.error && <ErrorState message={conflicting.error} />}
          <ul className="divide-y divide-line/70">
            {conflicting.data?.items.map((v) => (
              <li key={v.id}><button className="flex w-full items-center gap-3 py-2 text-left text-[14px] transition-colors hover:text-accent" onClick={() => setOpen(v.id)}>
                <span className="flex-1 truncate font-mono text-[13px]">{v.hgvsp ?? v.name ?? v.variant_key}</span>
                {v.provenance === "SYNTHETIC" && <ProvenanceBadge p="SYNTHETIC" />}
                <span className="data text-[12.5px] text-muted">AF {fmtAF(v.af)}</span><Stars n={v.gold_stars} />
              </button></li>
            ))}
          </ul>
          <p className="meta mt-2">{fmtInt(conflicting.data?.total)} conflicting records in this view.</p>
        </Panel>
      </div>

      <Panel eyebrow="explainable flags" title="Unusual frequency–classification combinations">
        {flags.error && <ErrorState message={flags.error} />}
        {unusual.length === 0 && !flags.loading && <p className="text-muted">No unusual combinations under the current thresholds (adjust them in the Anomaly Engine).</p>}
        <div className="grid gap-4 md:grid-cols-2">
          {unusual.slice(0, 8).map((f) => (
            <button key={`${f.variant_key}-${f.category}`} onClick={() => f.variant_id && setOpen(f.variant_id)} className="panel panel-interactive p-4 text-left">
              <div className="mb-2 flex flex-wrap items-center gap-2"><PriorityBadge p={f.priority} /><span className="font-mono text-[12.5px] text-muted">{f.variant_key}</span></div>
              <div className="font-display text-[19px] leading-snug">{f.headline}</div>
              <p className="mt-1 text-[15px] text-muted">{f.reason}</p>
            </button>
          ))}
        </div>
        <p className="meta mt-3">Showing {Math.min(8, unusual.length)} of {unusual.length} frequency-related flags. A flag is a prompt for review, never a statement that a variant is misclassified.</p>
      </Panel>

      <Guide>
        <GuideItem term={<><Term k="P/LP">P/LP</Term>, <Term k="VUS">VUS</Term>, <Term k="B/LB">B/LB</Term></>}>ClinVar's five main classifications grouped into three: <b>pathogenic / likely pathogenic</b>, <b>uncertain significance</b>, and <b>benign / likely benign</b>. <b>Conflicting</b> means submitters disagree.</GuideItem>
        <GuideItem term="Why a log scale?">Frequencies span six orders of magnitude. On the plots, <b>log10(AF) = −5</b> means 1 in 100,000 chromosomes and <b>−2</b> means 1 in 100. Each step left is ten times rarer.</GuideItem>
        <GuideItem term="Box plots">The line is the <b>median</b>; the box holds the middle 50% of variants; dots are unusually extreme values. Boxes that barely overlap suggest clearly different frequency ranges.</GuideItem>
        <GuideItem term="Missing frequencies">Variants that were not found in the frequency dataset are <b>excluded</b> from these statistics. Absence does <b>not</b> mean the frequency is zero – the site may be uncovered or filtered.</GuideItem>
        <GuideItem term={<><Term k="review stars">Review stars</Term></>}>How thoroughly the classification was reviewed. A class dominated by 0–1 star records rests on weaker evidence.</GuideItem>
        <GuideItem term="What you can and cannot conclude">You <b>can</b> describe how frequency differs between classification groups in this gene. You <b>cannot</b> conclude that any single variant is misclassified, or anything about an individual's risk.</GuideItem>
      </Guide>
      <Disclaimer compact />
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

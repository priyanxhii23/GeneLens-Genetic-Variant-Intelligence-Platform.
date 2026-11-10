import { motion } from "framer-motion";
import { CheckCircle2, CircleSlash, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ClassBadge, ErrorState, Explain, HelixLoader, NeedsAnalysis, PageHeader, Panel, stagger, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtInt, fmtNum, fmtP, MAIN_CLASSES, pct, token } from "../../lib/format";
import type { StatTest } from "../../lib/types";

function Contingency({ t }: { t: { rows: string[]; columns: string[]; counts: number[][] } }) {
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="mt-2 text-xs">
        <thead><tr><th className="px-2 py-1" />{t.columns.map((c) => <th key={c} className="px-2 py-1 text-left font-mono text-faint">{c}</th>)}</tr></thead>
        <tbody>{t.rows.map((r, i) => <tr key={r}><td className="px-2 py-1 font-mono text-faint">{r}</td>{t.counts[i].map((n, j) => <td key={j} className="data px-2 py-1">{n}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function TestCard({ t }: { t: StatTest }) {
  const sig = t["significant_fdr_0.05"];
  const n = typeof t.n === "object" ? Object.entries(t.n).map(([k, v]) => `${k} ${v}`).join(" · ") : t.n !== undefined ? `n = ${fmtInt(t.n)}` : "";
  return (
    <motion.div layout className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><div className="eyebrow">{t.test}</div><div className="font-display text-lg">{t.comparison ?? t.variables}</div><div className="text-xs text-faint">{n}</div></div>
        {!t.ran ? <span className="chip border-line text-muted"><CircleSlash size={11} />not run</span>
          : sig ? <span className="chip border-good/40 text-good"><CheckCircle2 size={11} />significant (FDR 5%)</span>
            : <span className="chip border-line text-muted"><XCircle size={11} />not significant</span>}
      </div>
      {!t.ran ? <p className="mt-3 text-sm text-muted">{t.reason}</p> : (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="eyebrow">statistic</dt><dd className="data">{fmtNum(t.statistic ?? null, 4)}{t.dof !== undefined && <span className="text-xs text-faint"> (df {t.dof})</span>}</dd></div>
            <div><dt className="eyebrow">p-value</dt><dd className="data">{fmtP(t.p_value)}</dd></div>
            <div><dt className="eyebrow">p (BH-FDR)</dt><dd className="data">{fmtP(t.p_adjusted_bh)}</dd></div>
            <div><dt className="eyebrow">p (Bonferroni)</dt><dd className="data">{fmtP(t.p_adjusted_bonferroni)}</dd></div>
          </dl>
          {t.effect_size && (
            <div className="mt-3 rounded-xl bg-raised/60 px-3 py-2 text-sm">
              <span className="text-muted">{t.effect_size.name}: </span><span className="data">{fmtNum(t.effect_size.value, 3)}</span>
              {t.effect_size.magnitude && <span className="text-xs text-faint"> ({t.effect_size.magnitude})</span>}
              {(t.effect_size.ci95_conditional || t.effect_size.ci95_fisher_z) && <span className="data text-xs text-muted"> · 95% CI [{(t.effect_size.ci95_conditional ?? t.effect_size.ci95_fisher_z)!.map((x) => fmtNum(x, 3)).join(", ")}]</span>}
              {t.median_difference_ci95 && <div className="text-xs text-muted">Median difference in log10 AF: <span className="data">{fmtNum(t.median_difference_log10, 3)}</span> (bootstrap 95% CI <span className="data">{t.median_difference_ci95.map((x) => x.toFixed(2)).join(" to ")}</span>)</div>}
            </div>
          )}
          {t.warning && <p className="mt-2 text-xs text-warn">{t.warning}</p>}
          {(t.contingency_table || t.table) && <Contingency t={(t.contingency_table ?? t.table)!} />}
          <p className="mt-3 text-sm leading-relaxed text-muted">{t.explanation}</p>
          {t.assumptions && (
            <details className="mt-2 text-xs"><summary className="cursor-pointer text-faint">assumption checks</summary>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-bg/60 p-3 font-mono text-[11px] text-muted scrollbar-thin">{JSON.stringify(t.assumptions, (_, v) => (typeof v === "number" ? Number(v.toPrecision(4)) : v), 2)}</pre></details>
          )}
        </>
      )}
    </motion.div>
  );
}

export default function StatisticsStudio() {
  const { analysisId, detail } = useAnalysis();
  const [amb, setAmb] = useState<"no" | "yes">("no");
  const stats = useFetch(analysisId && detail?.results ? () => api.statistics(analysisId, amb === "yes") : null, [analysisId, amb, detail?.results]);
  const s = stats.data;

  const ecdf = useMemo(() => s ? MAIN_CLASSES.filter((c) => s.box_data[c]?.length).map((c) => {
    const v = s.box_data[c].map((x) => Math.log10(x)).sort((a, b) => a - b);
    return { type: "scatter" as const, mode: "lines" as const, name: `${CLASS_META[c].short} (n=${v.length})`, x: v, y: v.map((_, i) => (i + 1) / v.length),
      line: { color: token(CLASS_META[c].color), width: 2, shape: "hv" as const }, hovertemplate: "log10 AF ≤ %{x:.2f}: %{y:.0%}<extra>%{fullData.name}</extra>" };
  }) : [], [s]);

  if (!analysisId) return <NeedsAnalysis />;
  const prop = s?.proportions.pathogenic_fraction_of_clinvar;

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="07" title="Statistical Analysis Studio"
        subtitle="Descriptive statistics, non-parametric group comparisons, contingency tests and correlation – with assumption checks, effect sizes, confidence intervals and multiple-testing correction, all computed by SciPy on the stored real records."
        actions={<Tabs value={amb} onChange={setAmb} options={[{ value: "no", label: "Exact + normalized" }, { value: "yes", label: "+ ambiguous" }]} />} />
      {stats.loading && <HelixLoader label="Computing statistics" />}
      {stats.error && <ErrorState message={stats.error} onRetry={stats.reload} />}
      {s && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {[["Rows considered", s.sample.total_rows], ["Matched variants used", s.sample.matched_used], ["…with gnomAD AF > 0", s.sample.matched_with_af]].map(([l, v]) => (
              <div key={l as string} className="panel p-4"><div className="eyebrow">{l}</div><div className="data mt-1 text-2xl">{fmtInt(v as number)}</div></div>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
            <Panel eyebrow="distribution" title="Cumulative distribution of log10 AF">
              <Plot data={ecdf} height={320} layout={{ xaxis: { title: { text: "log10(allele frequency)" } }, yaxis: { title: { text: "cumulative share" }, tickformat: ".0%" }, hovermode: "closest" }} />
              <p className="text-xs text-faint">Curves further right = more frequent variants. Mann–Whitney asks whether one curve sits systematically to the right of another.</p>
            </Panel>
            <Panel eyebrow="descriptive" title="Per-class summary">
              <table className="w-full text-sm">
                <thead><tr>{["Class", "n", "Median", "Mean", "SD", "IQR"].map((h) => <th key={h} className="table-head !px-2">{h}</th>)}</tr></thead>
                <tbody>{MAIN_CLASSES.map((c) => { const d = s.descriptive[c]; return (
                  <tr key={c}><td className="table-cell !px-2"><ClassBadge cls={c} /></td><td className="table-cell data !px-2 text-xs">{fmtInt(d?.n)}</td>
                    <td className="table-cell data !px-2 text-xs">{fmtAF(d?.median)}</td><td className="table-cell data !px-2 text-xs">{fmtAF(d?.mean)}</td>
                    <td className="table-cell data !px-2 text-xs">{fmtAF(d?.std)}</td><td className="table-cell data !px-2 text-xs">{fmtAF(d?.iqr)}</td></tr>); })}</tbody>
              </table>
              {prop?.estimate !== null && prop?.ci95_wilson && (
                <div className="mt-4 rounded-xl bg-raised/60 p-3 text-sm">
                  P/LP share of ClinVar records: <span className="data">{pct(prop.estimate)}</span> <span className="text-xs text-muted">(95% Wilson CI {pct(prop.ci95_wilson[0])}–{pct(prop.ci95_wilson[1])}, n = {fmtInt(prop.n)})</span>
                </div>
              )}
            </Panel>
          </div>
          <div className="rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm text-muted"><b className="text-ink">{s.multiple_testing.method}</b> across {s.multiple_testing.m} tests. {s.multiple_testing.explanation}</div>
          <motion.div variants={stagger} className="grid gap-4 lg:grid-cols-2">{s.tests.map((t, i) => <TestCard key={i} t={t} />)}</motion.div>
          <Explain title="Beginner's guide to these statistics">
            <p><b>p-value:</b> how surprising the observed difference would be if there were truly no difference. It is not the probability that the finding is true.</p>
            <p><b>Effect size:</b> how big the difference is. With thousands of variants even tiny effects become “significant”, so always read the effect size.</p>
            <p><b>Confidence interval:</b> a range of values compatible with the data at the 95% level.</p>
            <p><b>Why non-parametric tests?</b> Allele frequencies are heavily skewed (Shapiro–Wilk results are in each card's assumption checks), so rank-based tests are used.</p>
            <p><b>Independence caveat:</b> variants in one gene are not fully independent observations, and frequency is part of how classifications are assigned. Treat results as descriptive of this dataset.</p>
          </Explain>
        </>
      )}
    </motion.div>
  );
}

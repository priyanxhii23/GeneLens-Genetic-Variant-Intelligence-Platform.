import { motion } from "framer-motion";
import { CheckCircle2, CircleSlash, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ClassBadge, ErrorState, Guide, GuideItem, HelixLoader, Insight, NeedsAnalysis, PageHeader, Panel, stagger, Tabs, Term } from "../../components/ui";
import { useProvenance } from "../../lib/provenance";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtInt, fmtNum, fmtP, MAIN_CLASSES, pct, token } from "../../lib/format";
import type { StatTest, Statistics } from "../../lib/types";

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

type Normality = { test: string; applicable: boolean; reason?: string; W?: number; p_value?: number; "normal_at_0.05"?: boolean; n_tested?: number };

/** Assumption checks as readable sentences (no raw objects). */
function Assumptions({ a }: { a: Record<string, unknown> }) {
  const items: string[] = [];
  const norm = a.normality as Record<string, Normality> | undefined;
  if (norm) for (const [g, n] of Object.entries(norm)) {
    items.push(n.applicable ? `Normality, ${g}: ${n["normal_at_0.05"] ? "consistent with a normal distribution" : "not normal"} (Shapiro–Wilk p = ${fmtP(n.p_value)}, n = ${fmtInt(n.n_tested)}).`
      : `Normality, ${g}: not testable (${n.reason}).`);
  }
  if (typeof a.equal_spread_levene_p === "number") items.push(`Equal spread between groups (Levene): p = ${fmtP(a.equal_spread_levene_p as number)}${(a.equal_spread_levene_p as number) < 0.05 ? " – spreads differ, so the result compares whole distributions, not only medians" : ""}.`);
  if (typeof a.why_nonparametric === "string") items.push(a.why_nonparametric as string);
  if (typeof a.independent_observations === "string") items.push(`Independence: ${a.independent_observations}`);
  if (typeof a.expected_counts_ge_5_fraction === "number") items.push(`${Math.round((a.expected_counts_ge_5_fraction as number) * 100)}% of expected counts are ≥ 5 – ${a.assumption_met ? "the chi-square approximation is appropriate" : "too few; rely on Fisher's exact test instead"} (${a.rule}).`);
  if (typeof a.note === "string") items.push(a.note as string);
  if (!items.length) return null;
  return (
    <details className="mt-3 rounded-xl border border-line/70 bg-raised/40 p-3 text-[13.5px]">
      <summary className="cursor-pointer font-semibold text-muted">Assumption checks</summary>
      <ul className="mt-2 space-y-1.5 text-muted">{items.map((x) => <li key={x} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" /><span>{x}</span></li>)}</ul>
    </details>
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
          <p className="insight-detail mt-3">{t.explanation}</p>
          {t.assumptions && <Assumptions a={t.assumptions} />}
        </>
      )}
    </motion.div>
  );
}

/** Wilson score interval (95%) – same method as the backend; returns [estimate, lower, upper]. */
function wilson(k: number, n: number): [number, number, number] | null {
  if (!n) return null;
  const z = 1.959963984540054, p = k / n, d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d, h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [p, Math.max(0, c - h), Math.min(1, c + h)];
}

export default function StatisticsStudio() {
  const { analysisId, detail } = useAnalysis();
  const { mode } = useProvenance();
  const [amb, setAmb] = useState<"no" | "yes">("no");
  const [grp, setGrp] = useState<"REAL" | "SYNTHETIC">("REAL");
  const stats = useFetch(analysisId && detail?.results ? () => api.statisticsFor(analysisId, mode, amb === "yes") : null, [analysisId, amb, detail?.results, mode]);
  const groups = Object.entries(stats.data?.groups ?? {}).filter(([, v]) => v) as ["REAL" | "SYNTHETIC", Statistics][];
  const active = mode === "BOTH" ? grp : (mode as "REAL" | "SYNTHETIC");
  const s = stats.data?.groups[active] ?? null;

  const ecdf = useMemo(() => groups.flatMap(([g, st]) => MAIN_CLASSES.filter((c) => st.box_data[c]?.length).map((c) => {
    const v = st.box_data[c].map((x) => Math.log10(x)).sort((a, b) => a - b);
    return { type: "scatter" as const, mode: "lines" as const, name: `${CLASS_META[c].short}${g === "SYNTHETIC" ? " (syn)" : ""} n=${v.length}`, x: v, y: v.map((_, i) => (i + 1) / v.length),
      line: { color: token(CLASS_META[c].color), width: 2, shape: "hv" as const, dash: g === "SYNTHETIC" ? "dash" as const : "solid" as const },
      hovertemplate: `log10 AF ≤ %{x:.2f}: %{y:.0%}<extra>${g} ${CLASS_META[c].short}</extra>` };
  })), [stats.data]); // eslint-disable-line

  if (!analysisId) return <NeedsAnalysis />;
  const prop = s?.proportions.pathogenic_fraction_of_clinvar;
  const key = s?.tests.find((t) => t.ran && t.comparison === "P/LP vs B/LB");
  const nSig = s?.tests.filter((t) => t["significant_fdr_0.05"]).length ?? 0;
  const nRan = s?.tests.filter((t) => t.ran).length ?? 0;

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="07" title="Statistical Analysis Studio"
        subtitle="Descriptive statistics, non-parametric group comparisons, contingency tests and correlation – with assumption checks, effect sizes, confidence intervals and multiple-testing correction, computed by SciPy from the stored records."
        actions={<div className="flex flex-wrap gap-2">
          {mode === "BOTH" && <Tabs value={grp} onChange={setGrp} options={[{ value: "REAL", label: <><span className="h-2 w-2 rounded-full bg-gold" />Real tests</> }, { value: "SYNTHETIC", label: <><span className="h-2 w-2 rounded-full bg-pink" />Synthetic tests</> }]} />}
          <Tabs value={amb} onChange={setAmb} options={[{ value: "no", label: "Exact + normalized" }, { value: "yes", label: "+ ambiguous" }]} />
        </div>} />
      {stats.loading && <HelixLoader label="Computing statistics" />}
      {stats.error && <ErrorState message={stats.error} onRetry={stats.reload} />}
      {mode !== "REAL" && !stats.loading && !stats.data?.groups.SYNTHETIC && (
        <Insight tone="pink" label="No synthetic data" reason="This analysis has no linked synthetic records yet."><p>Generate a dataset in the Synthetic Lab to compute synthetic statistics. Real and synthetic statistics are always computed separately.</p></Insight>
      )}
      {s && (
        <>
          <Insight label={`Main finding · ${active.toLowerCase()} data`}
            reason={key ? `Pathogenic and benign variants ${key["significant_fdr_0.05"] ? "differ" : "do not differ"} significantly in allele frequency (Mann–Whitney p = ${fmtP(key.p_adjusted_bh)} after FDR correction; effect size ${fmtNum(key.effect_size?.value ?? null)}, ${key.effect_size?.magnitude}).`
              : "The key P/LP vs B/LB comparison could not run – each group needs at least five matched variants with a frequency."}>
            <p>{nSig} of {nRan} tests that ran were significant after <b>Benjamini–Hochberg FDR correction</b>. A significant <Term k="p-value">p-value</Term> says a difference is unlikely to be chance; the <Term k="effect size">effect size</Term> says how big it is. With thousands of variants even tiny effects become significant, so read both. Variants in a gene are not fully independent and frequency is part of how classifications are made, so treat these as <b>descriptive</b> results.</p>
          </Insight>
          <div className="grid gap-4 sm:grid-cols-3">
            {[["Rows considered", s.sample.total_rows], ["Matched variants used", s.sample.matched_used], ["…with AF > 0", s.sample.matched_with_af]].map(([l, v]) => (
              <div key={l as string} className="panel p-4"><div className="eyebrow">{l}</div><div className="data mt-1 text-[28px]">{fmtInt(v as number)}</div></div>
            ))}
          </div>
          <div className="layout-split">
            <Panel eyebrow="distribution" title="Cumulative distribution of log10 AF">
              <Plot data={ecdf} height={340} layout={{ xaxis: { title: { text: "log10(allele frequency)" } }, yaxis: { title: { text: "cumulative share" }, tickformat: ".0%" }, hovermode: "closest" }} />
              <p className="meta">Curves further right = more frequent variants. Mann–Whitney asks whether one curve sits systematically to the right of another.{mode === "BOTH" ? " Dashed = synthetic." : ""}</p>
            </Panel>
            <Panel eyebrow="descriptive" title="Per-class summary">
              <table className="w-full text-[14px]">
                <thead><tr>{["Class", "n", "Median", "Mean", "SD", "IQR"].map((h) => <th key={h} className="table-head !px-2">{h}</th>)}</tr></thead>
                <tbody>{MAIN_CLASSES.map((c) => { const d = s.descriptive[c]; return (
                  <tr key={c}><td className="table-cell !px-2"><ClassBadge cls={c} /></td><td className="table-cell data !px-2 text-[13px]">{fmtInt(d?.n)}</td>
                    <td className="table-cell data !px-2 text-[13px]">{fmtAF(d?.median)}</td><td className="table-cell data !px-2 text-[13px]">{fmtAF(d?.mean)}</td>
                    <td className="table-cell data !px-2 text-[13px]">{fmtAF(d?.std)}</td><td className="table-cell data !px-2 text-[13px]">{fmtAF(d?.iqr)}</td></tr>); })}</tbody>
              </table>
              {prop?.estimate !== null && prop?.ci95_wilson && (
                <div className="mt-4 rounded-xl bg-raised/60 p-3 text-[14px]">
                  P/LP share of ClinVar records: <span className="data">{pct(prop.estimate)}</span> <span className="text-[12.5px] text-muted">(95% Wilson CI {pct(prop.ci95_wilson[0])}–{pct(prop.ci95_wilson[1])}, n = {fmtInt(prop.n)})</span>
                </div>
              )}
            </Panel>
          </div>
          {s.gnomad_presence_by_class && (() => {
            const g = s.gnomad_presence_by_class; const n = MAIN_CLASSES.reduce((a, c) => a + (g[c]?.total ?? 0), 0);
            return n > 0 && (
              <Panel eyebrow="proportions with 95% Wilson intervals" title="Classification mix and frequency-data coverage">
                <div className="overflow-x-auto scrollbar-thin"><table className="w-full min-w-[560px] text-[13.5px]">
                  <thead><tr>{["Class", "Records", "Share of classified records", "Found in frequency dataset"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
                  <tbody>{MAIN_CLASSES.map((c) => { const t = g[c]?.total ?? 0; const share = wilson(t, n); const cov = wilson(g[c]?.in_gnomad ?? 0, t); return (
                    <tr key={c} className="border-t border-line/60"><td className="table-cell"><ClassBadge cls={c} /></td><td className="table-cell data">{fmtInt(t)}</td>
                      <td className="table-cell data">{share ? `${pct(share[0])} (${pct(share[1])}–${pct(share[2])})` : "—"}</td>
                      <td className="table-cell data">{cov ? `${pct(cov[0])} (${pct(cov[1])}–${pct(cov[2])})` : "not calculable (n = 0)"}</td></tr>); })}</tbody>
                </table></div>
              </Panel>
            );
          })()}
          <Insight label="Statistical vs biological significance" reason="A statistically significant result says a difference is unlikely to be chance in this sample; it does not say the difference matters biologically or clinically.">
            <p>With thousands of variants, tiny differences become “significant”. Read the <b>effect size</b> and its interval to judge magnitude. Tests marked <b>not run</b> did not have enough records or violated their assumptions – their results would be invalid, so GeneLens does not show a p-value for them. Sample sizes used by every test are listed on its card.</p>
          </Insight>
          <div className="rounded-xl border border-accent/30 bg-accent/5 px-4 py-3 text-[14.5px] text-muted"><b className="text-ink">{s.multiple_testing.method}</b> across {s.multiple_testing.m} tests. {s.multiple_testing.explanation}</div>
          <motion.div variants={stagger} className="grid gap-4 lg:grid-cols-2">{s.tests.map((t, i) => <TestCard key={`${active}-${i}`} t={t} />)}</motion.div>
          <Guide title="Beginner's guide to these statistics">
            <GuideItem term={<Term k="p-value">p-value</Term>}>How surprising the observed difference would be if there were truly no difference. <b>p = 0.01</b> means such a difference would appear by chance about 1 time in 100. It is <b>not</b> the probability that the finding is true.</GuideItem>
            <GuideItem term={<Term k="FDR">Adjusted p-value (BH-FDR)</Term>}>Running several tests raises the chance that one looks significant by luck. The Benjamini–Hochberg adjustment corrects for this; GeneLens calls a result significant only if the <b>adjusted</b> value is below 0.05.</GuideItem>
            <GuideItem term={<Term k="effect size">Effect size</Term>}>How big a difference is. <Term k="rank-biserial">Rank-biserial r</Term> runs from −1 to 1 (0 = no difference); Cramér's V from 0 to 1; the odds ratio is 1 when there is no association.</GuideItem>
            <GuideItem term="Confidence interval (CI)">A range of values compatible with the data at the 95% level. Example: a CI for the median difference of −0.4 to 0.2 includes 0, so "no difference" is plausible.</GuideItem>
            <GuideItem term="Why non-parametric tests?">Allele frequencies are extremely skewed (most are tiny, a few are large), which breaks t-tests. Rank-based tests like Mann–Whitney compare orderings instead of averages. Normality checks are shown under each test's <b>assumption checks</b>.</GuideItem>
            <GuideItem term="What not to conclude">These tests describe this gene's data. They do not show that frequency causes a classification, nor that any individual variant is misclassified.</GuideItem>
          </Guide>
        </>
      )}
    </motion.div>
  );
}

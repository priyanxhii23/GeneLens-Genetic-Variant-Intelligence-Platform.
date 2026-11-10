import { motion } from "framer-motion";
import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ErrorState, Explain, HelixLoader, NeedsAnalysis, PageHeader, Panel, stagger } from "../../components/ui";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { fmtNum, token } from "../../lib/format";

function Scale({ label, value, min, max, threshold, lowGood, hint }: { label: string; value: number | null | undefined; min: number; max: number; threshold: number; lowGood?: boolean; hint: string }) {
  const pos = value === null || value === undefined ? null : Math.min(1, Math.max(0, (value - min) / (max - min)));
  const tpos = (threshold - min) / (max - min);
  return (
    <div className="panel p-4">
      <div className="eyebrow">{label}</div>
      <div className="data mt-1 text-2xl">{fmtNum(value as number, 3)}</div>
      <div className="relative mt-3 h-2 rounded-full bg-raised">
        <div className={`absolute inset-y-0 rounded-full ${lowGood ? "left-0 bg-accent/30" : "right-0 bg-accent/30"}`} style={lowGood ? { width: `${tpos * 100}%` } : { left: `${tpos * 100}%` }} />
        <div className="absolute -top-1 h-4 w-px bg-ink/50" style={{ left: `${tpos * 100}%` }} title={`threshold ${threshold}`} />
        {pos !== null && <motion.div className="absolute -top-1.5 h-5 w-5 -translate-x-1/2 rounded-full border-2 border-surface bg-accent shadow-glow" initial={{ left: "0%" }} animate={{ left: `${pos * 100}%` }} transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }} />}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-faint"><span>{min}</span><span>constrained side shaded · threshold {threshold}</span><span>{max}</span></div>
      <p className="mt-2 text-xs text-muted">{hint}</p>
    </div>
  );
}

export default function ConstraintObservatory() {
  const { analysisId, detail } = useAnalysis();
  const c = detail?.results?.constraint;
  const gene = detail?.results?.gene?.symbol;
  const [input, setInput] = useState("");
  const [genes, setGenes] = useState<string[]>(["BRCA1", "CFTR", "TP53", "SCN1A", "TTN"]);
  const list = useMemo(() => Array.from(new Set([gene, ...genes].filter(Boolean) as string[])), [gene, genes]);
  const cmp = useFetch(analysisId ? () => api.constraintCompare(list) : null, [list.join(",")]);

  const oe = useMemo(() => {
    const rows = c?.observed_expected ?? [];
    return [{
      type: "scatter" as const, mode: "markers" as const, x: rows.map((r) => r.oe), y: rows.map((r) => r.class.toUpperCase()),
      error_x: { type: "data" as const, symmetric: false, array: rows.map((r) => (r.oe_upper ?? r.oe) - r.oe), arrayminus: rows.map((r) => r.oe - (r.oe_lower ?? r.oe)), color: token("accent"), thickness: 2, width: 6 },
      marker: { size: 11, color: token("accent"), line: { color: token("surface"), width: 2 } },
      hovertemplate: "%{y}: o/e %{x:.3f}<extra></extra>",
    }];
  }, [c]);
  const obsExp = useMemo(() => {
    const rows = c?.observed_expected ?? [];
    return [
      { type: "bar" as const, name: "Expected", x: rows.map((r) => r.class.toUpperCase()), y: rows.map((r) => r.expected), marker: { color: token("faint", 0.55) }, hovertemplate: "%{x} expected: %{y:.1f}<extra></extra>" },
      { type: "bar" as const, name: "Observed", x: rows.map((r) => r.class.toUpperCase()), y: rows.map((r) => r.observed), marker: { color: token("accent") }, hovertemplate: "%{x} observed: %{y}<extra></extra>" },
    ];
  }, [c]);

  const compare = useMemo(() => {
    const g = (cmp.data?.genes ?? []).filter((x) => x.available && x.metrics).sort((a, b) => (a.metrics!.oe_lof_upper ?? 9) - (b.metrics!.oe_lof_upper ?? 9));
    return [{
      type: "scatter" as const, mode: "markers" as const, y: g.map((x) => x.symbol), x: g.map((x) => x.metrics!.oe_lof),
      error_x: { type: "data" as const, symmetric: false, array: g.map((x) => (x.metrics!.oe_lof_upper ?? 0) - (x.metrics!.oe_lof ?? 0)), arrayminus: g.map((x) => (x.metrics!.oe_lof ?? 0) - (x.metrics!.oe_lof_lower ?? 0)), color: token("violet"), thickness: 2, width: 5 },
      marker: { size: 10, color: g.map((x) => (x.symbol === gene ? token("accent") : token("violet"))), line: { color: token("surface"), width: 2 } },
      customdata: g.map((x) => [x.metrics!.oe_lof_upper, x.metrics!.pli]) as unknown as number[],
      hovertemplate: "%{y}<br>LoF o/e %{x:.3f}<br>LOEUF %{customdata[0]:.3f}<br>pLI %{customdata[1]:.3g}<extra></extra>",
    }];
  }, [cmp.data, gene]);

  if (!analysisId) return <NeedsAnalysis />;
  if (!c) return <Panel><p className="text-sm text-muted">Results not available yet.</p></Panel>;
  const m = c.metrics ?? {};
  const num = (k: string) => (typeof m[k] === "number" ? (m[k] as number) : null);

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="05" title="Gene Constraint Observatory"
        subtitle={<>How depleted is <b>{gene}</b> of damaging variation in the general population, compared with a mutational model? Constraint is a gene-level population-genetics summary – <b>not</b> a prediction that any variant causes disease.</>} />
      {!c.available ? <Panel><p className="text-sm text-muted">{c.message}</p></Panel> : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Scale label="pLI" value={num("pli")} min={0} max={1} threshold={0.9} hint="Probability of LoF intolerance; ≥ 0.9 = LoF-intolerant class." />
            <Scale label="LOEUF" value={num("oe_lof_upper")} min={0} max={2} threshold={0.6} lowGood hint="Upper 90% bound of LoF o/e; lower = more constrained (v4 guidance < 0.6)." />
            <Scale label="Missense Z" value={num("mis_z")} min={-4} max={8} threshold={3.09} hint="Positive = fewer missense than expected; ≥ 3.09 often called constrained." />
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <Panel eyebrow="observed / expected with 90% CI" title="Constraint ratios">
              <Plot data={oe} height={260} layout={{ xaxis: { title: { text: "observed / expected" }, rangemode: "tozero" }, showlegend: false,
                shapes: [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: token("faint"), dash: "dot", width: 1 } }] }} />
            </Panel>
            <Panel eyebrow="variant counts" title="Observed vs expected">
              <Plot data={obsExp} height={260} layout={{ barmode: "group", bargap: 0.35, bargroupgap: 0.08, yaxis: { title: { text: "variants" } } }} />
            </Panel>
          </div>
          <Panel eyebrow="interpretation" title={`What the metrics say about ${gene}`}>
            <ul className="space-y-2 text-sm">{c.interpretation?.map((l) => <li key={l} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" />{l}</li>)}</ul>
            <p className="mt-3 text-xs text-warn">{c.disclaimer}</p>
          </Panel>
        </>
      )}

      <Panel eyebrow="gene comparison" title="LoF constraint across genes" actions={
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const g = input.trim().toUpperCase(); if (g && !genes.includes(g)) setGenes([...genes, g].slice(-11)); setInput(""); }}>
          <input className="input !w-32 !py-1 font-mono uppercase" placeholder="add gene" value={input} onChange={(e) => setInput(e.target.value)} aria-label="Add gene to comparison" />
          <button className="btn-ghost !px-2 !py-1" aria-label="Add"><Plus size={14} /></button>
        </form>}>
        {cmp.loading && <HelixLoader label="Fetching constraint from gnomAD" />}
        {cmp.error && <ErrorState message={cmp.error} onRetry={cmp.reload} />}
        {cmp.data && <Plot data={compare} height={Math.max(220, list.length * 34 + 60)} layout={{ xaxis: { title: { text: "LoF observed/expected (bar = 90% CI; right end = LOEUF)" }, rangemode: "tozero" }, showlegend: false, margin: { l: 80, r: 16, t: 8, b: 48 },
          shapes: [{ type: "line", x0: 0.6, x1: 0.6, yref: "paper", y0: 0, y1: 1, line: { color: token("warn"), dash: "dot", width: 1 } }] }} />}
        <div className="mt-3 flex flex-wrap gap-2">
          {genes.map((g) => <button key={g} className="chip border-line text-muted hover:text-bad" onClick={() => setGenes(genes.filter((x) => x !== g))} title="remove">{g} ×</button>)}
          {cmp.data?.genes.filter((g) => !g.available).map((g) => <span key={g.symbol} className="chip border-warn/40 text-warn" title={g.error}>{g.symbol}: unavailable</span>)}
        </div>
      </Panel>

      <Explain title="What each metric means">
        {Object.values(c.docs ?? {}).map((d) => <p key={d.name}><b className="text-ink">{d.name}.</b> {d.meaning} <i>Caveat: {d.caveat}</i></p>)}
      </Explain>
    </motion.div>
  );
}

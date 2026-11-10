import { AnimatePresence, motion } from "framer-motion";
import { Download, FolderOpen, Play, Plus, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import DatasetPicker from "../../components/DatasetPicker";
import GeneCombobox from "../../components/GeneCombobox";
import Plot from "../../components/Plot";
import { Counter, ErrorState, Guide, GuideItem, HelixLoader, Insight, PageHeader, Panel, Skeleton, stagger, Term } from "../../components/ui";
import { api, clearApiCache } from "../../lib/api";
import { useFetch } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtDate, fmtInt, fmtNum, MAIN_CLASSES, token } from "../../lib/format";
import type { AnalysisSummary, CompareGene, CompareParams, WhatIfResult, WhatIfThresholds } from "../../lib/types";

const POPS = ["afr", "amr", "asj", "eas", "eur", "fin", "mid", "nfe", "sas", "remaining"];
const GENE_COLORS = ["accent", "violet", "vus", "plp", "blb"];
const CAT_LABEL: Record<string, string> = { frequent_pathogenic: "Frequent P/LP", ba1_frequency_non_benign: "Non-benign ≥ BA1", rare_benign: "Rare B/LB" };

function LogSlider({ label, value, onChange, min = -6, max = -1, help }: { label: string; value: number; onChange: (v: number) => void; min?: number; max?: number; help?: string }) {
  const lv = Math.log10(value);
  return (
    <label className="block text-[13px] font-semibold text-muted" title={help}>
      <div className="flex justify-between"><span>{label}</span><span className="data text-ink">{fmtAF(value)} <span className="text-faint">({(value * 100).toPrecision(2)}%)</span></span></div>
      <input type="range" min={min} max={max} step={0.25} value={lv} onChange={(e) => onChange(Number((10 ** Number(e.target.value)).toPrecision(3)))}
        className="mt-1.5 w-full accent-[rgb(var(--accent))]" aria-label={label} />
    </label>
  );
}

function csvOf(genes: CompareGene[], w: WhatIfResult | null, p: CompareParams) {
  const head = ["gene", "status", "frequency_records", "clinvar_records", "matched", "P_LP", "VUS", "B_LB", "CONFLICTING", "below_review_threshold",
    "above_af_threshold", "median_af", "pLI", "LOEUF", "whatif_baseline", "whatif_scenario", "whatif_difference"];
  const wi = Object.fromEntries((w?.genes ?? []).map((g) => [g.gene, g]));
  const rows = genes.map((g) => [g.gene, g.status, g.frequency_records, g.clinvar_records, g.matched, g.class_counts?.P_LP, g.class_counts?.VUS,
    g.class_counts?.B_LB, g.class_counts?.CONFLICTING, g.class_counts?.BELOW_REVIEW_THRESHOLD, g.above_threshold, g.median_af, g.pli, g.loeuf,
    wi[g.gene]?.baseline?.total, wi[g.gene]?.scenario?.total, wi[g.gene]?.difference].map((x) => (x === undefined || x === null ? "" : x)).join(","));
  return `# GeneLens gene comparison – REAL records only; parameters ${JSON.stringify(p).replace(/,/g, ";")}\n${head.join(",")}\n${rows.join("\n")}\n`;
}

export default function GeneComparisonLab() {
  const [genes, setGenes] = useState<string[]>(["HBB", "CFTR"]);
  const [adding, setAdding] = useState("");
  const [dataset, setDataset] = useState("gnomad_r4");
  const [afT, setAfT] = useState(0.001);
  const [classes, setClasses] = useState<string[]>([...MAIN_CLASSES]);
  const [minStars, setMinStars] = useState(0);
  const [pops, setPops] = useState<string[]>([]);
  const [base, setBase] = useState<WhatIfThresholds>({ pathogenic_af: 0.001, pathogenic_popmax_af: 0.01, ba1_af: 0.05, rare_benign_af: 1e-5 });
  const [scen, setScen] = useState<WhatIfThresholds>({ pathogenic_af: 0.005, pathogenic_popmax_af: 0.01, ba1_af: 0.05, rare_benign_af: 1e-5 });
  const [data, setData] = useState<CompareGene[] | null>(null);
  const [whatif, setWhatif] = useState<WhatIfResult | null>(null);
  const [prevWhatif, setPrevWhatif] = useState<WhatIfResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState<Record<string, AnalysisSummary>>({});
  const [name, setName] = useState("");
  const datasets = useFetch(() => api.datasets(), []);
  const saved = useFetch(() => api.savedComparisons(), []);
  const timer = useRef<number>();

  const params: CompareParams = useMemo(() => ({ genes, dataset, af_threshold: afT, classes, min_stars: minStars, populations: pops }),
    [genes, dataset, afT, classes, minStars, pops]);

  const compute = async (p = params, b = base, s = scen) => {
    if (p.genes.length < 2) { setData(null); setWhatif(null); return; }
    setBusy(true); setErr(null);
    try {
      const [r, w] = await Promise.all([api.compareRun(p), api.compareWhatIf({ ...p, baseline: b, scenario: s })]);
      setData(r.genes); setPrevWhatif(whatif); setWhatif(w);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  // Dynamic updates: recompute shortly after any parameter changes.
  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void compute(), 350);
    return () => window.clearTimeout(timer.current);
  }, [params, base, scen]); // eslint-disable-line

  // Poll analyses started for missing genes, then recompute.
  useEffect(() => {
    const ids = Object.values(running);
    if (!ids.length) return;
    const t = window.setInterval(async () => {
      const next = await Promise.all(ids.map((a) => api.status(a.id).catch(() => a)));
      const pending = Object.fromEntries(next.filter((a) => a.status === "queued" || a.status === "running").map((a) => [a.gene_symbol, a]));
      setRunning(pending);
      if (Object.keys(pending).length < ids.length) { clearApiCache(); void compute(); }
    }, 1500);
    return () => window.clearInterval(t);
  }, [running]); // eslint-disable-line

  const runMissing = async () => {
    const missing = (data ?? []).filter((g) => g.status === "missing").map((g) => g.gene).filter((g) => !running[g]);
    const ds = datasets.data?.find((d) => d.id === dataset);
    const started = await Promise.all(missing.map((g) => api.runAnalysis({ gene: g, dataset, clinvar_source: ds?.clinvar_sources[0] ?? "eutils" }).catch(() => null)));
    setRunning((r) => ({ ...r, ...Object.fromEntries(started.filter(Boolean).map((a) => [a!.gene_symbol, a!])) }));
  };
  const addGene = (g: string) => {
    const s = g.trim().toUpperCase();
    if (s && !genes.includes(s) && genes.length < 5) setGenes([...genes, s]);
    setAdding("");
  };
  const ok = (data ?? []).filter((g) => g.status === "ok");
  const missing = (data ?? []).filter((g) => g.status === "missing");

  const classChart = MAIN_CLASSES.filter((c) => classes.includes(c)).map((c) => ({
    type: "bar" as const, name: CLASS_META[c].short, x: ok.map((g) => g.gene), y: ok.map((g) => g.class_counts?.[c] ?? 0),
    marker: { color: token(CLASS_META[c].color), line: { color: token("surface"), width: 2 } }, hovertemplate: `%{x}: %{y:,} ${CLASS_META[c].short}<extra></extra>`,
  }));
  const distChart = ok.map((g, i) => {
    const e = g.histogram!.edges; const mids = e.slice(0, -1).map((x, j) => (x + e[j + 1]) / 2);
    const tot = mids.map((_, j) => Object.values(g.histogram!.counts).reduce((a, arr) => a + (arr[j] ?? 0), 0));
    const sum = tot.reduce((a, b) => a + b, 0) || 1;
    return { type: "scatter" as const, mode: "lines" as const, name: g.gene, x: mids, y: tot.map((v) => v / sum),
      line: { color: token(GENE_COLORS[i % 5]), width: 2.5, shape: "spline" as const }, hovertemplate: `${g.gene} · log10 AF ≈ %{x:.1f}: %{y:.1%}<extra></extra>` };
  });
  const constraintChart = [{
    type: "scatter" as const, mode: "text+markers" as const, x: ok.map((g) => g.loeuf ?? null), y: ok.map((g) => g.pli ?? null), text: ok.map((g) => g.gene),
    textposition: "top center" as const, marker: { size: 14, color: ok.map((_, i) => token(GENE_COLORS[i % 5])), line: { color: token("surface"), width: 2 } },
    hovertemplate: "%{text}<br>LOEUF %{x:.3f}<br>pLI %{y:.3g}<extra></extra>",
  }];
  const wiChart = whatif ? [
    { type: "bar" as const, name: "Baseline", x: whatif.genes.filter((g) => g.status === "ok").map((g) => g.gene), y: whatif.genes.filter((g) => g.status === "ok").map((g) => g.baseline!.total), marker: { color: token("faint", 0.6) }, hovertemplate: "%{x}: %{y} flags (baseline)<extra></extra>" },
    { type: "bar" as const, name: "Scenario", x: whatif.genes.filter((g) => g.status === "ok").map((g) => g.gene), y: whatif.genes.filter((g) => g.status === "ok").map((g) => g.scenario!.total), marker: { color: token("accent") }, hovertemplate: "%{x}: %{y} flags (scenario)<extra></extra>" },
  ] : [];

  const doSave = async () => {
    if (!data) return;
    await api.saveComparison({ name: name || `${genes.join(" vs ")} · ${new Date().toLocaleDateString()}`, params, results: { genes: data }, whatif });
    setName(""); saved.reload();
  };
  const reopen = async (id: string) => {
    const s = await api.savedComparison(id);
    const p = s.parameters;
    setGenes(p.genes); setDataset(p.dataset); setAfT(p.af_threshold); setClasses(p.classes); setMinStars(p.min_stars); setPops(p.populations);
    if (s.results?.whatif) { setBase(s.results.whatif.baseline_thresholds); setScen(s.results.whatif.scenario_thresholds); }
  };
  const exportCurrent = () => {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([csvOf(data, whatif, params)], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = `GeneLens_comparison_${genes.join("_")}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  const plotCfg = (n: string) => ({ toImageButtonOptions: { filename: `GeneLens_${n}_${genes.join("_")}`, scale: 2 } });

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="09" title="Gene Comparison Lab"
        subtitle="Compare 2–5 genes side by side, explore how filters change the picture, and run what-if screening scenarios. Every number is recalculated from stored REAL records."
        actions={<><button className="btn-ghost" onClick={exportCurrent} disabled={!data}><Download size={15} />Export CSV</button></>} />

      <div className="layout-aside">
        <div className="space-y-6">
          <Panel eyebrow="1 · genes" title="Select 2–5 genes">
            <div className="mb-3 flex flex-wrap gap-2">
              <AnimatePresence>
                {genes.map((g, i) => (
                  <motion.span key={g} layout initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}
                    className={`chip border-${GENE_COLORS[i % 5]}/50 bg-${GENE_COLORS[i % 5]}/10 px-2.5 py-1 font-mono text-[13px] text-ink`}>
                    <span className={`h-2 w-2 rounded-full bg-${GENE_COLORS[i % 5]}`} />{g}
                    {running[g] && <span className="text-[11px] text-faint">running…</span>}
                    <button onClick={() => setGenes(genes.filter((x) => x !== g))} aria-label={`Remove ${g}`} className="text-faint hover:text-bad"><X size={12} /></button>
                  </motion.span>
                ))}
              </AnimatePresence>
            </div>
            {genes.length < 5 ? (
              <div className="flex gap-2">
                <div className="flex-1"><GeneCombobox value={adding} onChange={(v) => { setAdding(v); }} onSubmit={addGene} dataset={dataset} /></div>
                <button className="btn-ghost !px-3" onClick={() => addGene(adding)} disabled={!adding.trim()} aria-label="Add gene"><Plus size={15} /></button>
              </div>
            ) : <p className="meta">Maximum of five genes reached.</p>}
            {genes.length < 2 && <p className="mt-2 text-[13px] text-warn">Add at least two genes to compare.</p>}
          </Panel>
          <Panel eyebrow="2 · parameters" title="Explore">
            <div className="space-y-4">
              <div><div className="mb-1 text-[13px] font-semibold text-muted">Dataset</div><DatasetPicker datasets={datasets.data} value={dataset} onChange={setDataset} loading={datasets.loading} /></div>
              <LogSlider label="Allele frequency threshold" value={afT} onChange={setAfT} help="Variants at or above this AF are counted as 'above threshold'" />
              <div>
                <div className="mb-1.5 text-[13px] font-semibold text-muted">Clinical classifications</div>
                <div className="flex flex-wrap gap-2">{MAIN_CLASSES.map((c) => { const on = classes.includes(c); return (
                  <button key={c} aria-pressed={on} onClick={() => setClasses(on ? classes.filter((x) => x !== c) : [...classes, c])}
                    className={`chip ${on ? `border-${CLASS_META[c].color}/60 bg-${CLASS_META[c].color}/15 text-ink` : "border-line text-faint"}`}><span className={`h-1.5 w-1.5 rounded-full bg-${CLASS_META[c].color}`} />{CLASS_META[c].short}</button>); })}</div>
              </div>
              <label className="block text-[13px] font-semibold text-muted">Minimum <Term k="review stars">review status</Term>: <span className="data text-ink">{minStars}★</span>
                <input type="range" min={0} max={4} step={1} value={minStars} onChange={(e) => setMinStars(Number(e.target.value))} className="mt-1.5 w-full accent-[rgb(var(--accent))]" />
              </label>
              <div>
                <div className="mb-1.5 text-[13px] font-semibold text-muted">Populations used for AF <span className="font-normal text-faint">({pops.length ? pops.join(", ") : "all – overall AF"})</span></div>
                <div className="flex flex-wrap gap-1.5">{POPS.map((p) => { const on = pops.includes(p); return (
                  <button key={p} aria-pressed={on} onClick={() => setPops(on ? pops.filter((x) => x !== p) : [...pops, p])} className={`chip ${on ? "border-accent/50 bg-accent/10 text-ink" : "border-line text-faint"}`}>{p}</button>); })}</div>
              </div>
            </div>
          </Panel>
          <Panel eyebrow="saved" title="Saved comparisons">
            <div className="flex gap-2"><input className="input" placeholder="Name this comparison" value={name} onChange={(e) => setName(e.target.value)} />
              <button className="btn-primary !px-3" onClick={doSave} disabled={!data || genes.length < 2} aria-label="Save comparison"><Save size={15} /></button></div>
            <ul className="mt-3 divide-y divide-line/70">
              {saved.data?.map((s) => (
                <li key={s.id} className="flex items-center gap-2 py-2 text-[13.5px]">
                  <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{s.name}</span><span className="meta">{s.genes.join(", ")} · {fmtDate(s.created_at)}</span></span>
                  <button className="btn-ghost !px-2 !py-1" onClick={() => reopen(s.id)} title="Reopen"><FolderOpen size={13} /></button>
                  <a className="btn-ghost !px-2 !py-1" href={api.comparisonExportUrl(s.id)} title="Export CSV"><Download size={13} /></a>
                  <button className="btn-ghost !px-2 !py-1 hover:!text-bad" onClick={async () => { await api.deleteComparison(s.id); saved.reload(); }} title="Delete"><Trash2 size={13} /></button>
                </li>
              ))}
              {saved.data?.length === 0 && <li className="py-2 meta">Nothing saved yet.</li>}
            </ul>
          </Panel>
        </div>

        <div className="space-y-6">
          {err && <ErrorState message={err} onRetry={() => void compute()} />}
          {missing.length > 0 && (
            <Insight tone="warn" label="Data needed" reason={`${missing.map((g) => g.gene).join(", ")} ${missing.length > 1 ? "have" : "has"} no completed analysis for this dataset yet.`}>
              <p>The comparison only uses stored, real analysis results. Run the missing {missing.length > 1 ? "analyses" : "analysis"} now – the comparison updates automatically when {missing.length > 1 ? "they finish" : "it finishes"}.</p>
              <button className="btn-primary mt-1" onClick={runMissing} disabled={missing.every((g) => running[g.gene])}><Play size={14} />{missing.every((g) => running[g.gene]) ? "Running…" : `Run ${missing.length} missing ${missing.length > 1 ? "analyses" : "analysis"}`}</button>
              {Object.keys(running).length > 0 && <HelixLoader label={`Analysing ${Object.keys(running).join(", ")}`} />}
            </Insight>
          )}
          {busy && !data && <div className="grid gap-4 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-56" />)}</div>}
          {ok.length > 0 && (
            <>
              <motion.div layout className="grid gap-4" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${ok.length > 3 ? 190 : 230}px, 1fr))` }}>
                {ok.map((g, i) => (
                  <motion.div key={g.gene} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`panel p-4 ${busy ? "opacity-70" : ""} transition-opacity`}>
                    <div className={`absolute inset-x-4 top-0 h-[2px] rounded-full bg-${GENE_COLORS[i % 5]}`} />
                    <div className="flex items-baseline justify-between"><span className="font-display text-[26px]">{g.gene}</span><span className="data text-[11px] text-faint">{g.analysis_id}</span></div>
                    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2 text-[13px]">
                      <div><dt className="eyebrow !text-[10.5px]">Variants</dt><dd className="data text-[17px]"><Counter value={g.frequency_records ?? 0} /></dd></div>
                      <div><dt className="eyebrow !text-[10.5px]">Matched</dt><dd className="data text-[17px]"><Counter value={g.matched ?? 0} /></dd></div>
                      <div><dt className="eyebrow !text-[10.5px] !text-plp">P/LP</dt><dd className="data text-[17px]"><Counter value={g.class_counts?.P_LP ?? 0} /></dd></div>
                      <div><dt className="eyebrow !text-[10.5px] !text-blb">B/LB</dt><dd className="data text-[17px]"><Counter value={g.class_counts?.B_LB ?? 0} /></dd></div>
                      <div><dt className="eyebrow !text-[10.5px] !text-vus">VUS</dt><dd className="data text-[17px]"><Counter value={g.class_counts?.VUS ?? 0} /></dd></div>
                      <div><dt className="eyebrow !text-[10.5px]">≥ AF threshold</dt><dd className="data text-[17px] text-accent"><Counter value={g.above_threshold ?? 0} /></dd></div>
                      <div><dt className="eyebrow !text-[10.5px]"><Term k="pLI">pLI</Term></dt><dd className="data">{fmtNum(g.pli ?? null, 3)}</dd></div>
                      <div><dt className="eyebrow !text-[10.5px]"><Term k="LOEUF">LOEUF</Term></dt><dd className="data">{fmtNum(g.loeuf ?? null, 3)}</dd></div>
                    </dl>
                    {(g.class_counts?.BELOW_REVIEW_THRESHOLD ?? 0) > 0 && <p className="meta mt-2">{fmtInt(g.class_counts!.BELOW_REVIEW_THRESHOLD)} ClinVar records below {minStars}★ excluded from class counts</p>}
                    <p className="meta mt-2">Sources: {g.sources?.join(", ")}</p>
                  </motion.div>
                ))}
              </motion.div>
              <div className="layout-halves">
                <Panel eyebrow="classifications" title="ClinVar classes per gene"><Plot data={classChart} height={300} config={plotCfg("classes")} layout={{ barmode: "group", bargap: 0.25, yaxis: { title: { text: "records" } } }} /></Panel>
                <Panel eyebrow="frequency" title="Allele frequency distribution"><Plot data={distChart} height={300} config={plotCfg("af_distribution")} layout={{ xaxis: { title: { text: `log10(AF)${pops.length ? ` · ${pops.join("+")}` : ""}` } }, yaxis: { title: { text: "share of matched variants" }, tickformat: ".0%" },
                  shapes: [{ type: "line", x0: Math.log10(afT), x1: Math.log10(afT), yref: "paper", y0: 0, y1: 1, line: { color: token("accent"), dash: "dot", width: 1.5 } }] }} /></Panel>
                <Panel eyebrow="gene constraint" title="pLI vs LOEUF"><Plot data={constraintChart} height={300} config={plotCfg("constraint")} layout={{ showlegend: false, xaxis: { title: { text: "LOEUF (lower = more constrained)" }, rangemode: "tozero" }, yaxis: { title: { text: "pLI" }, range: [-0.05, 1.1] },
                  shapes: [{ type: "line", x0: 0.6, x1: 0.6, yref: "paper", y0: 0, y1: 1, line: { color: token("warn"), dash: "dot", width: 1 } }] }} /></Panel>
                <Panel eyebrow="what-if" title="Frequency-related review flags"><Plot data={wiChart} height={300} config={plotCfg("whatif")} layout={{ barmode: "group", bargap: 0.3, yaxis: { title: { text: "flags" } } }} /></Panel>
              </div>
            </>
          )}

          <Panel eyebrow="3 · what-if analysis" title="How would screening results change?" actions={busy ? <HelixLoader label="Recalculating…" /> : undefined}>
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-3 rounded-xl border border-line bg-raised/40 p-4">
                <div className="eyebrow">Baseline thresholds</div>
                <LogSlider label="P/LP frequency threshold" value={base.pathogenic_af} onChange={(v) => setBase({ ...base, pathogenic_af: v })} />
                <LogSlider label="Rare-benign threshold" value={base.rare_benign_af} onChange={(v) => setBase({ ...base, rare_benign_af: v })} min={-7} max={-3} />
              </div>
              <div className="space-y-3 rounded-xl border border-accent/40 bg-accent/5 p-4 shadow-glow-sm">
                <div className="eyebrow !text-accent">Scenario thresholds</div>
                <LogSlider label="P/LP frequency threshold" value={scen.pathogenic_af} onChange={(v) => setScen({ ...scen, pathogenic_af: v })} />
                <LogSlider label="Rare-benign threshold" value={scen.rare_benign_af} onChange={(v) => setScen({ ...scen, rare_benign_af: v })} min={-7} max={-3} />
              </div>
            </div>
            {whatif && (
              <div className="mt-5 space-y-4">
                <div className="grid gap-3 sm:grid-cols-4">
                  {[["Previous result", whatif.total.baseline, "text-ink"], ["Updated result", whatif.total.scenario, "text-accent"],
                    ["Difference", whatif.total.difference, whatif.total.difference > 0 ? "text-warn" : whatif.total.difference < 0 ? "text-good" : "text-ink"]].map(([l, v, c]) => (
                    <div key={l as string} className="panel p-3"><div className="eyebrow">{l}</div><div className={`data text-[26px] ${c}`}>{(v as number) > 0 && l === "Difference" ? "+" : ""}<Counter value={v as number} /></div></div>
                  ))}
                  <div className="panel p-3"><div className="eyebrow">% change</div><div className="data text-[26px]">{whatif.total.percent_change === null ? "—" : `${whatif.total.percent_change > 0 ? "+" : ""}${whatif.total.percent_change}%`}</div></div>
                </div>
                <Insight label="What changed – and what did not" reason={whatif.explanation.split(". ")[0] + "."}>
                  <p>{whatif.explanation.split(". ").slice(1).join(". ")}</p>
                  {prevWhatif && prevWhatif.total.scenario !== whatif.total.scenario && <p className="meta">Previous scenario run: {prevWhatif.total.scenario} flags.</p>}
                </Insight>
                <div className="overflow-x-auto scrollbar-thin">
                  <table className="w-full min-w-[620px] text-[13.5px]">
                    <thead><tr>{["Gene", "Baseline", "Scenario", "Difference", "% change", ...Object.values(CAT_LABEL).map((c) => `Δ ${c}`)].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
                    <tbody>{whatif.genes.map((g) => (
                      <tr key={g.gene}><td className="table-cell font-mono">{g.gene}</td>
                        {g.status !== "ok" ? <td className="table-cell text-muted" colSpan={7}>no analysis</td> : <>
                          <td className="table-cell data">{g.baseline!.total}</td><td className="table-cell data">{g.scenario!.total}</td>
                          <td className="table-cell data">{g.difference! > 0 ? "+" : ""}{g.difference}</td>
                          <td className="table-cell data">{g.percent_change === null || g.percent_change === undefined ? "—" : `${g.percent_change}%`}</td>
                          {Object.keys(CAT_LABEL).map((c) => <td key={c} className="table-cell data">{g.by_category_difference?.[c] ?? 0}</td>)}
                        </>}
                      </tr>))}</tbody>
                  </table>
                </div>
              </div>
            )}
          </Panel>

          <Guide title="How to use the Gene Comparison Lab">
            <GuideItem term="Where the numbers come from">Each gene uses its <b>most recent completed analysis</b> for the selected dataset. Parameters re-filter or re-compute those stored <b>real</b> records – they never change the data.</GuideItem>
            <GuideItem term="Allele frequency threshold">Counts how many matched variants (in the selected classes) have <Term k="AF">AF</Term> at or above the threshold. Example: at 0.001, a variant seen in 1 of every 500 chromosomes (AF = 0.002) is counted.</GuideItem>
            <GuideItem term="Minimum review status">ClinVar labels with fewer <Term k="review stars">stars</Term> than the minimum are set aside, so you can see how conclusions change when only well-reviewed classifications are used.</GuideItem>
            <GuideItem term="Population selection">When populations are selected, AF is recalculated as <b>ΣAC ÷ ΣAN</b> over those groups only. With none selected, the overall AF is used. Missing population data is excluded, never treated as zero.</GuideItem>
            <GuideItem term="What-if analysis">Re-runs the anomaly engine's <b>frequency rules</b> under two sets of thresholds. Raising the P/LP threshold flags fewer variants; lowering it flags more. This is a change in <b>screening parameters</b>, not in biological truth.</GuideItem>
            <GuideItem term="Saving and exporting">Save a comparison to reopen it later with the same settings, export results as CSV, and download any chart as PNG with the camera icon in its top-right toolbar.</GuideItem>
          </Guide>
        </div>
      </div>
    </motion.div>
  );
}

import { motion } from "framer-motion";
import { Download, FlaskConical, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ClassBadge, ErrorState, Explain, HelixLoader, PageHeader, Panel, ProvenanceBadge, stagger, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtDate, fmtInt, fmtNum, MAIN_CLASSES, pct, POP_LABELS, token } from "../../lib/format";
import type { SyntheticJob } from "../../lib/types";

const ALL_POPS = ["afr", "amr", "asj", "eas", "fin", "mid", "nfe", "sas", "remaining"];

export default function SyntheticLab() {
  const { analysisId, detail } = useAnalysis();
  const [source, setSource] = useState<"real" | "default">(analysisId ? "real" : "default");
  const [n, setN] = useState(2000);
  const [seed, setSeed] = useState(42);
  const [mode, setMode] = useState<"mirror" | "custom">("mirror");
  const [weights, setWeights] = useState<Record<string, number>>({ P_LP: 25, VUS: 35, B_LB: 35, CONFLICTING: 5 });
  const [missing, setMissing] = useState(0.02);
  const [conflict, setConflict] = useState(0.03);
  const [unusual, setUnusual] = useState(0.03);
  const [pops, setPops] = useState<string[]>(ALL_POPS);
  const [job, setJob] = useState<SyntheticJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [cls, setCls] = useState<string>("P_LP");
  const jobs = useFetch(() => api.syntheticJobs(), [job?.id]);
  const preview = useFetch(job ? () => api.variants({ synthetic_job_id: job.id, provenance: "SYNTHETIC", page_size: 12, sort: "af", order: "desc" }) : null, [job?.id]);
  const useReal = source === "real" && !!analysisId && !!detail?.results;

  const generate = async () => {
    setBusy(true); setErr(null);
    try {
      setJob(await api.generateSynthetic({
        source_analysis_id: useReal ? analysisId : null, n_records: n, seed, populations: pops,
        class_distribution: mode === "custom" ? weights : null, missing_rate: missing, conflicting_rate: conflict, unusual_rate: unusual,
      }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const dist = job?.comparison?.distribution;
  const overlay = useMemo(() => {
    if (!job) return [];
    const d = job.comparison?.distribution;
    if (!d) return [];
    const e = d.edges; const mids = e.slice(0, -1).map((x, i) => (x + e[i + 1]) / 2);
    const c = d.classes[cls];
    const norm = (h: number[]) => { const s = h.reduce((a, b) => a + b, 0) || 1; return h.map((x) => x / s); };
    return [
      { type: "scatter" as const, mode: "lines" as const, name: `REAL (n=${c.n_real})`, x: mids, y: norm(c.real_hist), line: { color: token(CLASS_META[cls as "P_LP"].color), width: 2.5, shape: "spline" as const }, hovertemplate: "REAL · log10 AF %{x:.2f}: %{y:.1%}<extra></extra>" },
      { type: "scatter" as const, mode: "lines" as const, name: `SYNTHETIC (n=${c.n_synthetic})`, x: mids, y: norm(c.synthetic_hist), line: { color: token("violet"), width: 2.5, dash: "dash" as const, shape: "spline" as const }, fill: "tozeroy" as const, fillpattern: { shape: "/" as const, fgcolor: token("violet", 0.35), bgcolor: "rgba(0,0,0,0)" }, hovertemplate: "SYNTHETIC · log10 AF %{x:.2f}: %{y:.1%}<extra></extra>" },
    ];
  }, [job, cls]);

  const propChart = useMemo(() => {
    if (!dist) return [];
    return [
      { type: "bar" as const, name: "REAL", x: MAIN_CLASSES.map((c) => CLASS_META[c].short), y: MAIN_CLASSES.map((c) => dist.class_proportions[c]?.real ?? 0), marker: { color: token("accent") }, hovertemplate: "REAL %{x}: %{y:.1%}<extra></extra>" },
      { type: "bar" as const, name: "SYNTHETIC", x: MAIN_CLASSES.map((c) => CLASS_META[c].short), y: MAIN_CLASSES.map((c) => dist.class_proportions[c]?.synthetic ?? 0), marker: { color: token("violet", 0.55), pattern: { shape: "/" as const, fgcolor: token("violet") } }, hovertemplate: "SYNTHETIC %{x}: %{y:.1%}<extra></extra>" },
    ];
  }, [dist]);

  const rate = (label: string, v: number, set: (x: number) => void, help: string) => (
    <label className="block text-xs text-muted" title={help}>
      <div className="flex justify-between"><span>{label}</span><span className="data text-ink">{pct(v)}</span></div>
      <input type="range" min={0} max={0.5} step={0.01} value={v} onChange={(e) => set(Number(e.target.value))} className="mt-1 w-full accent-[rgb(var(--violet))]" />
    </label>
  );

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="08" title="Synthetic Genome Data Lab"
        subtitle="A reproducible, seeded generator that samples from distributions estimated from real data – class mix, a Gaussian mixture over log10 AF, allele-number and population structure – without copying any real variant. Every record is permanently labelled SYNTHETIC." />
      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <Panel eyebrow="generator" title="Configure simulation" className="border-violet/40">
          <div className="space-y-4">
            <div className="synthetic-hatch -mt-1 h-2 rounded-full" aria-hidden />
            <div>
              <div className="eyebrow mb-2">distribution source</div>
              <Tabs value={source} onChange={setSource} options={[{ value: "real", label: "Fit to active analysis" }, { value: "default", label: "Parametric defaults" }]} />
              {source === "real" && !useReal && <p className="mt-2 text-xs text-warn">No completed analysis selected – parametric defaults will be used.</p>}
              {useReal && <p className="mt-2 text-xs text-muted">Fitting to {detail?.analysis.gene_symbol} ({detail?.analysis.id}). Only summary parameters are estimated.</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-muted">Records<input type="number" min={1} max={100000} className="input mt-1 font-mono" value={n} onChange={(e) => setN(Number(e.target.value))} /></label>
              <label className="text-xs text-muted">Random seed<input type="number" className="input mt-1 font-mono" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label>
            </div>
            <div>
              <div className="eyebrow mb-2">classification mix</div>
              <Tabs value={mode} onChange={setMode} options={[{ value: "mirror", label: "Mirror fitted" }, { value: "custom", label: "Custom" }]} />
              {mode === "custom" && (
                <div className="mt-3 space-y-2">{MAIN_CLASSES.map((c) => (
                  <label key={c} className="flex items-center gap-3 text-xs"><span className="w-20"><ClassBadge cls={c} /></span>
                    <input type="range" min={0} max={100} value={weights[c]} onChange={(e) => setWeights({ ...weights, [c]: Number(e.target.value) })} className="flex-1 accent-[rgb(var(--violet))]" />
                    <span className="data w-10 text-right">{Math.round((weights[c] / Math.max(1, Object.values(weights).reduce((a, b) => a + b, 0))) * 100)}%</span></label>
                ))}</div>
              )}
            </div>
            {rate("Missing values", missing, setMissing, "Fraction of records with missing frequency, population or classification fields")}
            {rate("Simulated conflicting classifications", conflict, setConflict, "Fraction assigned a conflicting label")}
            {rate("Unusual frequency patterns", unusual, setUnusual, "Half frequent-pathogenic (AF 1–10%), half very rare benign")}
            <div>
              <div className="eyebrow mb-2">population groups</div>
              <div className="flex flex-wrap gap-1.5">{ALL_POPS.map((p) => { const on = pops.includes(p); return (
                <button key={p} title={POP_LABELS[p]} aria-pressed={on} onClick={() => setPops(on ? pops.filter((x) => x !== p) : [...pops, p])} className={`chip ${on ? "border-violet/50 text-ink" : "border-line text-faint"}`}>{p}</button>); })}</div>
            </div>
            <button className="btn w-full bg-violet text-white hover:-translate-y-px hover:shadow-glow" disabled={busy || pops.length === 0} onClick={generate}><Sparkles size={15} />{busy ? "Generating…" : "Generate synthetic dataset"}</button>
            {busy && <HelixLoader label="Sampling & evaluating" />}
            {err && <ErrorState message={err} />}
          </div>
        </Panel>

        <div className="space-y-6">
          {!job && <Panel title="No synthetic dataset generated in this session" eyebrow="output"><p className="text-sm text-muted">Configure the generator and press generate. Results include a real-vs-synthetic comparison and a check of whether the anomaly engine recovers the injected scenarios.</p></Panel>}
          {job && (
            <>
              <Panel eyebrow={`job ${job.id} · seed ${job.seed}`} title={<span className="flex items-center gap-2"><FlaskConical size={18} className="text-violet" />{fmtInt(job.stored_records)} synthetic records</span>}
                actions={<a className="btn-ghost" href={api.variantExportUrl({ synthetic_job_id: job.id, provenance: "SYNTHETIC" })} download><Download size={14} />Export CSV</a>}>
                <div className="grid gap-4 md:grid-cols-3">
                  <div><div className="eyebrow">model</div><div className="text-sm">{job.fitted_model.source.replace(/_/g, " ")}</div>{job.fitted_model.note && <div className="text-xs text-warn">{job.fitted_model.note}</div>}</div>
                  <div><div className="eyebrow">class counts</div><div className="mt-1 flex flex-wrap gap-1.5">{Object.entries(job.class_counts).map(([c, v]) => <span key={c} className="chip border-line text-muted">{CLASS_META[c as "P_LP"]?.short ?? c} {fmtInt(v)}</span>)}</div></div>
                  {job.comparison?.anomaly_engine_evaluation && (() => { const ev = job.comparison!.anomaly_engine_evaluation; return (
                    <div><div className="eyebrow">anomaly engine recovery</div>
                      <div className="text-sm">unusual: <span className="data">{ev.injected_unusual_flagged}/{ev.injected_unusual}</span> · conflicts: <span className="data">{ev.injected_conflicts_flagged}/{ev.injected_conflicts}</span></div>
                      <div className="text-xs text-faint" title={ev.note}>injected ground truth, default thresholds</div></div>); })()}
                </div>
              </Panel>
              {dist ? (
                <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
                  <Panel eyebrow="real vs synthetic" title="log10 AF distribution" actions={<select className="input !w-auto !py-1 text-xs" value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Class">{MAIN_CLASSES.map((c) => <option key={c} value={c}>{CLASS_META[c].short}</option>)}</select>}>
                    <Plot data={overlay} height={300} layout={{ xaxis: { title: { text: "log10(allele frequency)" } }, yaxis: { title: { text: "share of class" }, tickformat: ".0%" } }} />
                    <p className="text-xs text-faint">KS statistic: <span className="data">{fmtNum(dist.classes[cls]?.ks?.statistic ?? null)}</span> (0 = identical distributions). {dist.explanation}</p>
                  </Panel>
                  <Panel eyebrow="class mix" title="Proportions">
                    <Plot data={propChart} height={300} layout={{ barmode: "group", bargap: 0.3, bargroupgap: 0.1, yaxis: { tickformat: ".0%" } }} />
                    <p className="text-xs text-faint">Total variation distance: <span className="data">{fmtNum(dist.class_total_variation_distance)}</span></p>
                  </Panel>
                </div>
              ) : <Panel><p className="text-sm text-muted">Generated from parametric defaults – no real dataset to compare against.</p></Panel>}
              <Panel eyebrow="preview · highest AF" title="Synthetic records" bodyClass="p-0">
                <div className="overflow-x-auto scrollbar-thin">
                  <table className="w-full min-w-[720px]">
                    <thead><tr>{["ID", "Source", "Class", "AF", "AC / AN", "Top population", "QC / scenario"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
                    <tbody>{preview.data?.items.map((v) => (
                      <tr key={v.id} className="synthetic-hatch">
                        <td className="table-cell font-mono text-xs">{v.variant_key}</td><td className="table-cell"><ProvenanceBadge p={v.provenance} /></td>
                        <td className="table-cell"><ClassBadge cls={v.coarse_class} label={v.clinical_significance} /></td>
                        <td className="table-cell data text-xs">{fmtAF(v.af)}</td><td className="table-cell data text-xs">{fmtInt(v.ac)} / {fmtInt(v.an)}</td>
                        <td className="table-cell text-xs text-muted">{v.popmax_population ?? "—"}</td>
                        <td className="table-cell text-[11px] text-faint">{(v.qc_flags ?? []).filter((f) => f !== "simulated_record").join(", ") || "—"}</td>
                      </tr>))}</tbody>
                  </table>
                </div>
              </Panel>
            </>
          )}
          <Panel eyebrow="history" title="Previous synthetic jobs">
            <ul className="divide-y divide-line/70 text-sm">{jobs.data?.slice(0, 8).map((j) => (
              <li key={j.id} className="flex flex-wrap items-center gap-3 py-2"><span className="font-mono text-xs">{j.id}</span><span className="text-muted">{fmtInt(j.n_records)} records · seed {j.seed}</span>
                <span className="text-xs text-faint">{j.model_source?.replace(/_/g, " ")}</span><span className="flex-1 text-right text-xs text-faint">{fmtDate(j.created_at)}</span>
                <button className="btn-ghost !py-1 text-xs" onClick={() => api.syntheticJob(j.id).then(setJob)}>open</button></li>))}
              {jobs.data?.length === 0 && <li className="py-2 text-muted">None yet.</li>}</ul>
          </Panel>
        </div>
      </div>
      <Explain title="How the generator works">
        <p>1. <b>Fit:</b> class proportions; a 1–3 component Gaussian mixture of log10 AF per class; a normal model of log10 AN; mean population AN shares; spread of population AF around the global AF.</p>
        <p>2. <b>Sample:</b> for each record draw a class, a target AF and a total AN; split AN across populations (Dirichlet); draw population AC ~ Binomial(AN, AF·noise). Global AC/AN are sums, so AF = AC/AN always holds.</p>
        <p>3. <b>Inject scenarios</b> (optional): missing fields, conflicting labels, unusual frequency patterns – recorded as QC flags so the anomaly engine can be evaluated against known ground truth.</p>
        <p>Synthetic records have no conditions, submitters or review stars: GeneLens never fabricates clinical evidence.</p>
      </Explain>
    </motion.div>
  );
}

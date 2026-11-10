import { motion } from "framer-motion";
import { ArrowRight, CircleDot, Database, FlaskConical, MapPin, Play, ShieldAlert, Sigma, Split, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DatasetPicker from "../../components/DatasetPicker";
import GeneCombobox, { rememberGene } from "../../components/GeneCombobox";
import Plot from "../../components/Plot";
import { Disclaimer, ErrorState, HelixLoader, Insight, Metric, PageHeader, Panel, Skeleton, stagger, Term } from "../../components/ui";
import { api, clearApiCache } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, fmtDate, fmtInt, MATCH_LABELS, pct, token } from "../../lib/format";
import { useProvenance } from "../../lib/provenance";
import type { AnalysisSummary, CoarseClass } from "../../lib/types";

const STARTERS = ["HBB", "CFTR", "BRCA1", "BRCA2", "TP53", "LDLR", "G6PD", "PAH"];

function GeneLauncher({ onStarted }: { onStarted: (a: AnalysisSummary) => void }) {
  const [gene, setGene] = useState("");
  const [dataset, setDataset] = useState(() => { try { return localStorage.getItem("genelens-dataset") || "gnomad_r4"; } catch { return "gnomad_r4"; } });
  const [source, setSource] = useState("eutils");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const datasets = useFetch(() => api.datasets(), []);
  const ds = datasets.data?.find((d) => d.id === dataset);
  useEffect(() => { try { localStorage.setItem("genelens-dataset", dataset); } catch { /* */ } }, [dataset]);
  useEffect(() => { if (ds && !ds.clinvar_sources.includes(source)) setSource(ds.clinvar_sources[0]); }, [ds, source]);

  const run = async (symbol = gene) => {
    if (!symbol.trim()) return;
    setBusy(true); setErr(null);
    rememberGene(symbol.trim().toUpperCase());
    try { onStarted(await api.runAnalysis({ gene: symbol.trim().toUpperCase(), dataset, clinvar_source: source })); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <Panel eyebrow="new analysis" title="Investigate a gene" className="relative z-10">
      <form onSubmit={(e) => { e.preventDefault(); void run(); }} className="space-y-4">
        <GeneCombobox value={gene} onChange={setGene} onSubmit={(g) => void run(g)} dataset={dataset} />
        <div>
          <div className="mb-1 text-[13px] font-semibold text-muted">Dataset</div>
          <DatasetPicker datasets={datasets.data} value={dataset} onChange={setDataset} loading={datasets.loading} />
          {datasets.error && <p className="mt-1 text-xs text-bad">{datasets.error}</p>}
        </div>
        <label className="block text-[13px] font-semibold text-muted">ClinVar source
          <select className="input mt-1" value={source} onChange={(e) => setSource(e.target.value)}>
            {(ds?.clinvar_sources ?? ["eutils", "tsv"]).map((s) => <option key={s} value={s}>{s === "eutils" ? "NCBI E-utilities (live)" : "variant_summary TSV (local download)"}</option>)}
          </select>
        </label>
        <button className="btn-primary w-full !py-2.5" disabled={busy || !gene.trim() || ds?.status === "unavailable"}><Play size={15} />{busy ? "Starting…" : "Run research pipeline"}</button>
        {err && <ErrorState message={err} />}
        <div>
          <div className="eyebrow mb-2">suggested starting genes</div>
          <div className="flex flex-wrap gap-2">
            {STARTERS.map((g) => (
              <button type="button" key={g} onClick={() => { setGene(g); void run(g); }}
                className="chip border-line px-2.5 py-1 font-mono text-[12.5px] text-muted transition-all hover:-translate-y-px hover:border-accent/50 hover:text-accent hover:shadow-glow-sm">{g}</button>
            ))}
          </div>
        </div>
      </form>
    </Panel>
  );
}

function RunProgress({ run, onDone }: { run: AnalysisSummary; onDone: (a: AnalysisSummary) => void }) {
  const [s, setS] = useState(run);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await api.status(run.id);
        if (!alive) return;
        setS(next);
        if (next.status === "completed" || next.status === "failed") { onDone(next); return; }
      } catch { /* transient */ }
      if (alive) window.setTimeout(tick, 900);
    };
    void tick();
    return () => { alive = false; };
  }, [run.id, onDone]);
  return (
    <Panel eyebrow={`analysis ${s.id}`} title={`Processing ${s.gene_symbol}`} className="shadow-glow-sm">
      <div className="space-y-3">
        <HelixLoader label={s.stage ?? "Queued"} />
        <div className="h-2 overflow-hidden rounded-full bg-raised">
          <motion.div className="h-full rounded-full bg-gradient-to-r from-accent to-violet" animate={{ width: `${Math.max(4, s.progress * 100)}%` }} transition={{ duration: 0.6 }} />
        </div>
        <p className="text-[13px] text-muted">Data is retrieved live from public APIs and cached; large genes can take a few minutes (rate-limited NCBI requests).</p>
        {s.status === "failed" && <ErrorState message={s.error ?? "Analysis failed"} />}
      </div>
    </Panel>
  );
}

export default function CommandCenter() {
  const { analysisId, detail, select, refresh } = useAnalysis();
  const { mode } = useProvenance();
  const [running, setRunning] = useState<AnalysisSummary | null>(null);
  const dash = useFetch(() => api.dashboard(analysisId, mode), [analysisId, mode]);
  const sources = useFetch(() => api.sourceList(), []);
  const m = dash.data?.metrics;
  const g = dash.data?.groups ?? {};
  const real = g.REAL;
  const syn = g.SYNTHETIC;
  const primary = mode === "SYNTHETIC" ? syn : real;
  const freqLabel = detail?.results?.dataset?.frequency_source ?? "gnomAD";
  const annot = detail?.results?.gene_annotation;

  const classData = useMemo(() => {
    const order: CoarseClass[] = ["P_LP", "VUS", "B_LB", "CONFLICTING", "OTHER", "NOT_IN_CLINVAR"];
    const traces = [];
    for (const [name, grp] of Object.entries(g)) {
      if (!grp) continue;
      const present = order.filter((c) => (grp.by_class[c] ?? 0) > 0).reverse();
      traces.push({
        type: "bar" as const, orientation: "h" as const, name: name === "REAL" ? "Real" : "Synthetic",
        y: present.map((c) => CLASS_META[c].short), x: present.map((c) => grp.by_class[c]),
        marker: name === "REAL" ? { color: present.map((c) => token(CLASS_META[c].color)) }
          : { color: token("pink", 0.25), line: { color: token("pink"), width: 1.5 } },
        text: present.map((c) => fmtInt(grp.by_class[c])), textposition: "outside" as const, cliponaxis: false,
        hovertemplate: `%{y}: %{x:,} records<extra>${name === "REAL" ? "REAL" : "SYNTHETIC"}</extra>`,
      });
    }
    return traces;
  }, [g]);

  const onDone = (a: AnalysisSummary) => {
    clearApiCache();  // a finished analysis changes dashboards, history and dataset badges
    setRunning(null);
    if (a.status === "completed") { select(a.id); void refresh(); }
    dash.reload();
  };
  const remove = async (id: string) => {
    if (!window.confirm(`Delete analysis ${id} and all its stored records, flags and export history? This cannot be undone.`)) return;
    await api.deleteAnalysis(id);
    if (id === analysisId) select(null);
    dash.reload();
  };

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="01" title="Genomic Command Center"
        subtitle="Launch analyses, choose among ten datasets and seven integrated sources, and monitor the loaded data. Every number here is computed from records stored in the GeneLens database." />

      <div className="layout-aside">
        <div className="space-y-6">
          {running ? <RunProgress run={running} onDone={onDone} /> : <GeneLauncher onStarted={setRunning} />}
          <Panel eyebrow="integrated sources" title="Source status" actions={<Link to="/workspace/sources" className="text-[13px] font-semibold text-accent hover:underline">Manage <ArrowRight size={12} className="inline" /></Link>}>
            {sources.loading && <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>}
            {sources.error && <ErrorState message={sources.error} onRetry={sources.reload} />}
            <ul className="space-y-2">
              {sources.data?.map((s) => (
                <li key={s.id} className="flex items-center gap-2.5 text-[14px]">
                  <CircleDot size={13} className={s.available ? "text-good" : s.available === false ? "text-bad" : "text-faint"} />
                  <span className="flex-1 truncate">{s.name}</span>
                  <span className={`text-[12px] ${s.available ? "text-good" : "text-bad"}`}>{s.available ? "available" : s.available === false ? "unavailable" : "unchecked"}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <div className="space-y-6">
          {dash.error && <ErrorState message={dash.error} onRetry={dash.reload} />}
          {!analysisId && !dash.loading && (
            <Insight label="Getting started" reason="Pick a gene and a dataset, then run the research pipeline.">
              <p>The pipeline retrieves <b>population frequencies</b> (or a variant catalogue) and <b>ClinVar classifications</b>, matches them allele by allele, runs statistics and anomaly screening, and stores everything for the other modules. <b>HBB</b> with gnomAD v4 completes in under a minute.</p>
            </Insight>
          )}
          {dash.loading && !m && <div className="layout-metrics">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)}</div>}
          {m && primary !== undefined && dash.data?.analysis && (
            <>
              {mode !== "REAL" && !syn?.total_records && (
                <Insight label="No synthetic data yet" tone="pink" reason="This analysis has no linked synthetic records.">
                  <p>Generate a dataset in the <Link to="/workspace/synthetic" className="font-semibold text-pink underline">Synthetic Lab</Link> to populate the synthetic view. Real records are unaffected.</p>
                </Insight>
              )}
              <motion.div variants={stagger} className="layout-metrics">
                <Metric label={`${mode === "SYNTHETIC" ? "Synthetic" : freqLabel} records`} value={primary?.gnomad_variants ?? 0} value2={mode === "BOTH" ? syn?.gnomad_variants : undefined} icon={<Database size={14} />} hint={detail?.results?.dataset?.name ?? dash.data.analysis.dataset} />
                <Metric label="ClinVar records" value={primary?.clinvar_records ?? 0} value2={mode === "BOTH" ? syn?.clinvar_records : undefined} icon={<Database size={14} />} tone="accent2" hint="germline classifications" />
                <Metric label="Matched alleles" value={primary?.matched ?? 0} value2={mode === "BOTH" ? syn?.matched : undefined} icon={<Split size={14} />} tone="violet" glow hint={mode === "SYNTHETIC" ? "generated as matched pairs" : `${pct(dash.data.matching?.clinvar_match_rate)} of ClinVar with coordinates`} />
                <Metric label="Flagged variants" value={primary?.flagged ?? 0} value2={mode === "BOTH" ? syn?.flagged : undefined} icon={<ShieldAlert size={14} />} tone="warn" hint={<Link className="underline decoration-dotted" to="/workspace/anomalies">review flags</Link>} />
                <Metric label="Pathogenic / LP" value={primary?.pathogenic ?? 0} value2={mode === "BOTH" ? syn?.pathogenic : undefined} tone="plp" hint="ClinVar P + LP + P/LP" />
                <Metric label="Benign / LB" value={primary?.benign ?? 0} value2={mode === "BOTH" ? syn?.benign : undefined} tone="blb" hint="ClinVar B + LB + B/LB" />
                <Metric label="VUS" value={primary?.vus ?? 0} value2={mode === "BOTH" ? syn?.vus : undefined} tone="vus" hint="uncertain significance" />
                <Metric label="Conflicting" value={primary?.conflicting ?? 0} value2={mode === "BOTH" ? syn?.conflicting : undefined} tone="conf" hint="submitters disagree" />
              </motion.div>

              <div className="layout-halves">
                <Panel eyebrow={`${dash.data.analysis.gene_symbol} · ${mode === "BOTH" ? "REAL vs SYNTHETIC" : mode}`} title="Classification mix">
                  <Plot data={classData} height={280} layout={{ margin: { l: 90, r: 60, t: mode === "BOTH" ? 36 : 8, b: 36 }, xaxis: { title: { text: "records" } }, showlegend: mode === "BOTH", barmode: "group" }} />
                </Panel>
                <Panel eyebrow={`${freqLabel} ↔ ClinVar`} title="Matching outcome">
                  {mode === "SYNTHETIC" ? <p className="text-[14px] text-muted">Synthetic records are generated as matched frequency + classification pairs, so database matching does not apply to them.</p> : (
                    <ul className="space-y-2.5">
                      {Object.entries(real?.by_match_status ?? {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
                        const frac = v / Math.max(1, real?.total_records ?? 1);
                        return (
                          <li key={k} className="text-[14px]">
                            <div className="flex justify-between"><span>{MATCH_LABELS[k] ?? k}</span><span className="data text-muted">{fmtInt(v)}</span></div>
                            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised">
                              <motion.div className={`h-full rounded-full ${["exact", "normalized"].includes(k) ? "bg-accent" : k === "ambiguous" ? "bg-warn" : "bg-faint/60"}`}
                                initial={{ width: 0 }} animate={{ width: `${frac * 100}%` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  <p className="mt-3 text-[12.5px] text-faint">Unmatched records stay visible in the Variant Explorer. Records are never joined by gene name alone.</p>
                </Panel>
              </div>

              {annot && Object.keys(annot.sources ?? {}).length > 0 && (
                <Panel eyebrow="gene annotation cross-check" title={<span className="flex items-center gap-2"><MapPin size={18} className="text-accent" />{dash.data.analysis.gene_symbol}{annot.name ? <span className="text-[16px] text-muted">· {annot.name}</span> : null}{annot.cytoband ? <span className="chip border-line font-mono text-muted">{annot.cytoband}</span> : null}</span>}>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {Object.entries(annot.sources).map(([src, c]) => (
                      <div key={src} className="rounded-xl border border-line bg-raised/50 p-3">
                        <div className="eyebrow">{src}</div>
                        <div className="data mt-1 text-[13.5px]">chr{c.chrom}:{fmtInt(c.start)}–{fmtInt(c.end)}</div>
                        {c.ensembl_id && <div className="data text-[12px] text-faint">{c.ensembl_id} · {c.canonical_transcript}</div>}
                        {c.transcripts && <div className="data text-[12px] text-faint">{c.transcripts.map((t) => t.name).join(", ")}</div>}
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[13px] text-muted">{annot.genome} coordinates from {Object.keys(annot.sources).join(", ")}. {annot.note}</p>
                </Panel>
              )}

              <div className="layout-split">
                <Panel eyebrow="provenance" title="Loaded datasets">
                  <div className="overflow-x-auto scrollbar-thin">
                    <table className="w-full min-w-[560px]">
                      <thead><tr>{["Source", "Release", "Access", "Records", "Retrieved"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
                      <tbody>
                        {dash.data.datasets?.map((d, i) => (
                          <tr key={i} className="transition-colors hover:bg-raised/50">
                            <td className="table-cell font-semibold">{d.source === "Synthetic" ? <span className="chip border-pink/50 bg-pink/10 text-pink"><FlaskConical size={11} />Synthetic</span> : d.source}</td>
                            <td className="table-cell text-[12.5px] text-muted">{d.release}</td>
                            <td className="table-cell"><span className={`chip ${d.access_mode === "live_api" ? "border-good/40 text-good" : d.access_mode === "offline_snapshot" ? "border-warn/40 text-warn" : "border-line text-muted"}`}>{d.access_mode.replace("_", " ")}</span></td>
                            <td className="table-cell data">{fmtInt(d.record_count)}</td>
                            <td className="table-cell text-[12.5px] text-muted">{fmtDate(d.retrieved_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
                <Panel eyebrow="real vs synthetic" title="Record provenance">
                  <div className="space-y-3 text-[14px]">
                    <div className="flex justify-between"><span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-gold" />Real records</span><span className="data">{fmtInt(m.real)}</span></div>
                    <div className="flex justify-between"><span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-pink" />Linked synthetic records</span><span className="data">{fmtInt(m.synthetic_linked)}</span></div>
                    <div className="flex h-2.5 overflow-hidden rounded-full bg-raised" aria-label="Real versus synthetic records">
                      <div className="bg-gold" style={{ width: `${(m.real / Math.max(1, m.real + m.synthetic_linked)) * 100}%` }} />
                      <div className="bg-pink/70" style={{ flex: 1 }} />
                    </div>
                    <p className="text-[12.5px] text-faint">Synthetic records are stored separately and never enter real-data statistics. Use the <b className="text-ink">Real · Synthetic · Both</b> switch at the top to change what every module displays.</p>
                  </div>
                </Panel>
              </div>
            </>
          )}

          <Panel eyebrow="research history" title="Recent analyses">
            {dash.data?.recent.length ? (
              <ul className="divide-y divide-line/70">
                {dash.data.recent.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-3 py-2.5 text-[14px]">
                    <span className={`h-2 w-2 rounded-full ${r.status === "completed" ? "bg-good" : r.status === "failed" ? "bg-bad" : "bg-warn animate-pulse"}`} />
                    <span className="font-display text-[18px]">{r.gene_symbol}</span>
                    <span className="data text-[12px] text-faint">{r.id} · {r.dataset}</span>
                    <span className="flex-1 text-[12.5px] text-muted">{fmtDate(r.created_at)}</span>
                    {r.status === "completed" && r.id !== analysisId && <button className="btn-ghost !py-1 text-xs" onClick={() => select(r.id)}><Sigma size={12} />Open</button>}
                    {r.id === analysisId && <span className="chip border-accent/40 text-accent shadow-glow-sm">active</span>}
                    {r.status === "failed" && <span className="max-w-xs truncate text-xs text-bad" title={r.error ?? ""}>{r.error}</span>}
                    <button className="btn-ghost !px-2 !py-1 hover:!text-bad" onClick={() => remove(r.id)} aria-label={`Delete analysis ${r.id}`}><Trash2 size={13} /></button>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No analyses yet.</p>}
            <p className="mt-2 text-[12.5px] text-faint">Full provenance (parameters, dataset releases, exports) is in the <Link className="underline" to="/workspace/reports">Report Generator</Link>.</p>
          </Panel>
          <p className="text-[12.5px] text-faint"><Term k="ClinVar">ClinVar</Term> classifications are submitted assertions; <Term k="gnomAD">gnomAD</Term> and other datasets are reference samples.</p>
          <Disclaimer compact />
        </div>
      </div>
    </motion.div>
  );
}

import { motion } from "framer-motion";
import { CircleDot, Database, FlaskConical, Play, RefreshCw, Search, ShieldAlert, Sigma, Split } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Plot from "../../components/Plot";
import { Disclaimer, ErrorState, HelixLoader, Metric, PageHeader, Panel, stagger } from "../../components/ui";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, fmtDate, fmtInt, MATCH_LABELS, pct, token } from "../../lib/format";
import type { AnalysisSummary, CoarseClass } from "../../lib/types";

const SUGGESTED = [
  { g: "HBB", why: "small, fast; sickle-cell allele shows population structure" },
  { g: "CFTR", why: "recessive disease; frequent pathogenic carrier alleles" },
  { g: "BRCA1", why: "large; many VUS and conflicting classifications" },
];

function GeneLauncher({ onStarted }: { onStarted: (a: AnalysisSummary) => void }) {
  const [gene, setGene] = useState("");
  const [hits, setHits] = useState<{ symbol: string; ensembl_id: string }[]>([]);
  const [dataset, setDataset] = useState("gnomad_r4");
  const [source, setSource] = useState("eutils");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const datasets = useFetch(() => api.datasets(), []);
  const timer = useRef<number>();

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (gene.length < 2) { setHits([]); return; }
    timer.current = window.setTimeout(() => {
      api.searchGenes(gene).then((r) => setHits(r.results.slice(0, 6))).catch(() => setHits([]));
    }, 300);
  }, [gene]);

  const ds = datasets.data?.find((d) => d.id === dataset);
  useEffect(() => { if (ds && !ds.clinvar_sources.includes(source)) setSource(ds.clinvar_sources[0]); }, [ds, source]);

  const run = async (symbol = gene) => {
    if (!symbol.trim()) return;
    setBusy(true); setErr(null); setHits([]);
    try { onStarted(await api.runAnalysis({ gene: symbol.trim().toUpperCase(), dataset, clinvar_source: source })); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <Panel eyebrow="new analysis" title="Investigate a gene" className="relative z-10">
      <form onSubmit={(e) => { e.preventDefault(); void run(); }} className="space-y-3">
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <input className="input !pl-9 font-mono uppercase" placeholder="Gene symbol, e.g. HBB" value={gene}
            onChange={(e) => setGene(e.target.value)} aria-label="Gene symbol" autoComplete="off" />
          {hits.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-line bg-surface shadow-soft">
              {hits.map((h) => (
                <li key={h.ensembl_id}>
                  <button type="button" onClick={() => { setGene(h.symbol); setHits([]); }} className="flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-raised">
                    <span className="font-mono">{h.symbol}</span><span className="data text-xs text-faint">{h.ensembl_id}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs text-muted">gnomAD dataset
            <select className="input mt-1" value={dataset} onChange={(e) => setDataset(e.target.value)}>
              {(datasets.data ?? [{ id: "gnomad_r4", label: "gnomAD v4", reference_genome: "GRCh38", clinvar_sources: ["eutils"] }]).map((d) =>
                <option key={d.id} value={d.id}>{d.label} · {d.reference_genome}</option>)}
            </select>
          </label>
          <label className="text-xs text-muted">ClinVar source
            <select className="input mt-1" value={source} onChange={(e) => setSource(e.target.value)}>
              {(ds?.clinvar_sources ?? ["eutils", "tsv"]).map((s) => <option key={s} value={s}>{s === "eutils" ? "NCBI E-utilities (live)" : "variant_summary TSV (local)"}</option>)}
            </select>
          </label>
        </div>
        <button className="btn-primary w-full" disabled={busy || !gene.trim()}><Play size={15} />{busy ? "Starting…" : "Run research pipeline"}</button>
        {err && <ErrorState message={err} />}
        <div className="pt-1">
          <div className="eyebrow mb-2">suggested starting genes</div>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED.map((s) => (
              <button type="button" key={s.g} title={s.why} onClick={() => { setGene(s.g); void run(s.g); }} className="chip border-line text-muted hover:border-accent/50 hover:text-accent">{s.g}</button>
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
    <Panel eyebrow={`analysis ${s.id}`} title={`Processing ${s.gene_symbol}`}>
      <div className="space-y-3">
        <HelixLoader label={s.stage ?? "Queued"} />
        <div className="h-2 overflow-hidden rounded-full bg-raised">
          <motion.div className="h-full rounded-full bg-gradient-to-r from-accent to-violet" animate={{ width: `${Math.max(4, s.progress * 100)}%` }} transition={{ duration: 0.6 }} />
        </div>
        {s.status === "failed" && <ErrorState message={s.error ?? "Analysis failed"} />}
      </div>
    </Panel>
  );
}

export default function CommandCenter() {
  const { analysisId, select, refresh } = useAnalysis();
  const [running, setRunning] = useState<AnalysisSummary | null>(null);
  const dash = useFetch(() => api.dashboard(analysisId), [analysisId]);
  const sources = useFetch(() => api.sources(), []);
  const m = dash.data?.metrics;

  const classData = useMemo(() => {
    if (!m) return [];
    const order: CoarseClass[] = ["P_LP", "VUS", "B_LB", "CONFLICTING", "OTHER", "NOT_IN_CLINVAR"];
    const present = order.filter((c) => (m.by_class[c] ?? 0) > 0).reverse();
    return [{
      type: "bar" as const, orientation: "h" as const, y: present.map((c) => CLASS_META[c].short), x: present.map((c) => m.by_class[c]),
      marker: { color: present.map((c) => token(CLASS_META[c].color)) }, text: present.map((c) => fmtInt(m.by_class[c])),
      textposition: "outside" as const, cliponaxis: false, hovertemplate: "%{y}: %{x:,} records<extra></extra>",
    }];
  }, [m]);

  const onDone = (a: AnalysisSummary) => {
    setRunning(null);
    if (a.status === "completed") { select(a.id); void refresh(); }
    dash.reload();
  };

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="01" title="Genomic Command Center"
        subtitle="Launch analyses and monitor the loaded dataset. Every number on this page is computed from records stored in the GeneLens database." />

      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <div className="space-y-6">
          {running ? <RunProgress run={running} onDone={onDone} /> : <GeneLauncher onStarted={setRunning} />}
          <Panel eyebrow="data sources" title="Source status" actions={<button className="btn-ghost !px-2 !py-1" onClick={() => api.sources(true).then(sources.setData)} aria-label="Refresh source status"><RefreshCw size={13} /></button>}>
            {sources.loading && <HelixLoader label="Checking sources" />}
            {sources.error && <ErrorState message={sources.error} onRetry={sources.reload} />}
            {sources.data && (
              <ul className="space-y-2.5 text-sm">
                {([["gnomad", "gnomAD GraphQL API"], ["clinvar", "NCBI E-utilities (ClinVar)"], ["clinvar_tsv", "ClinVar bulk TSV"]] as const).map(([k, label]) => {
                  const st = sources.data![k];
                  return (
                    <li key={k} className="flex items-start gap-2.5">
                      <CircleDot size={14} className={`mt-0.5 ${st.available ? "text-good" : k === "clinvar_tsv" ? "text-faint" : "text-bad"}`} />
                      <div className="min-w-0"><div>{label} <span className="text-xs text-muted">{st.available ? "available" : "unavailable"}</span></div>
                        <div className="truncate text-xs text-faint" title={st.detail}>{st.detail}</div></div>
                    </li>
                  );
                })}
              </ul>
            )}
            {sources.data && (!sources.data.gnomad.available || !sources.data.clinvar.available) && (
              <p className="mt-3 text-xs text-warn">A live source is unreachable. Analyses fall back to cached responses or a labelled offline snapshot (HBB ships with one); otherwise they fail with an explicit error.</p>
            )}
          </Panel>
        </div>

        <div className="space-y-6">
          {dash.error && <ErrorState message={dash.error} onRetry={dash.reload} />}
          {!analysisId && !dash.loading && (
            <Panel title="No analysis selected yet" eyebrow="getting started">
              <p className="text-sm text-muted">Pick a gene on the left. <b>HBB</b> runs in seconds and is a good first analysis. The pipeline retrieves gnomAD and ClinVar records, matches them allele by allele, runs statistics and screening, and stores everything for the other modules.</p>
            </Panel>
          )}
          {m && dash.data?.analysis && (
            <>
              <motion.div variants={stagger} className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Metric label="gnomAD variants" value={m.gnomad_variants} icon={<Database size={14} />} hint={dash.data.analysis.dataset} />
                <Metric label="ClinVar records" value={m.clinvar_records} icon={<Database size={14} />} tone="accent2" hint="germline classifications" />
                <Metric label="Matched alleles" value={m.matched} icon={<Split size={14} />} tone="violet" hint={`${pct(dash.data.matching?.clinvar_match_rate)} of ClinVar with coordinates`} />
                <Metric label="Flagged variants" value={m.flagged} icon={<ShieldAlert size={14} />} tone="warn" hint={<Link className="underline decoration-dotted" to="/workspace/anomalies">review flags</Link>} />
                <Metric label="Pathogenic / LP" value={m.pathogenic} tone="plp" hint="ClinVar P + LP + P/LP" />
                <Metric label="Benign / LB" value={m.benign} tone="blb" hint="ClinVar B + LB + B/LB" />
                <Metric label="VUS" value={m.vus} tone="vus" hint="uncertain significance" />
                <Metric label="Conflicting" value={m.conflicting} tone="conf" hint="submitters disagree" />
              </motion.div>

              <div className="grid gap-6 lg:grid-cols-2">
                <Panel eyebrow={`${dash.data.analysis.gene_symbol} · REAL records`} title="Classification mix">
                  <Plot data={classData} height={260} layout={{ margin: { l: 90, r: 50, t: 8, b: 30 }, xaxis: { title: { text: "records" } }, showlegend: false }} />
                </Panel>
                <Panel eyebrow="gnomAD ↔ ClinVar" title="Matching outcome">
                  <ul className="space-y-2">
                    {Object.entries(m.by_match_status).sort((a, b) => b[1] - a[1]).map(([k, v]) => {
                      const frac = v / m.total_records;
                      return (
                        <li key={k} className="text-sm">
                          <div className="flex justify-between"><span>{MATCH_LABELS[k] ?? k}</span><span className="data text-muted">{fmtInt(v)}</span></div>
                          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised">
                            <motion.div className={`h-full rounded-full ${["exact", "normalized"].includes(k) ? "bg-accent" : k === "ambiguous" ? "bg-warn" : "bg-faint/60"}`}
                              initial={{ width: 0 }} animate={{ width: `${frac * 100}%` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                  <p className="mt-3 text-xs text-faint">Unmatched records stay visible in the Variant Explorer. Records are never joined by gene name alone.</p>
                </Panel>
              </div>

              <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
                <Panel eyebrow="provenance" title="Loaded datasets">
                  <div className="overflow-x-auto scrollbar-thin">
                    <table className="w-full min-w-[520px]">
                      <thead><tr>{["Source", "Release", "Access", "Records", "Retrieved"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
                      <tbody>
                        {dash.data.datasets?.map((d, i) => (
                          <tr key={i}>
                            <td className="table-cell">{d.source === "Synthetic" ? <span className="chip synthetic-hatch border-violet/50 text-violet"><FlaskConical size={11} />Synthetic</span> : d.source}</td>
                            <td className="table-cell text-xs text-muted">{d.release}</td>
                            <td className="table-cell"><span className={`chip ${d.access_mode === "live_api" ? "border-good/40 text-good" : d.access_mode === "offline_snapshot" ? "border-warn/40 text-warn" : "border-line text-muted"}`}>{d.access_mode.replace("_", " ")}</span></td>
                            <td className="table-cell data">{fmtInt(d.record_count)}</td>
                            <td className="table-cell text-xs text-muted">{fmtDate(d.retrieved_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
                <Panel eyebrow="real vs synthetic" title="Record provenance">
                  <div className="space-y-4">
                    <div>
                      <div className="flex justify-between text-sm"><span>This analysis – REAL</span><span className="data">{fmtInt(m.real)}</span></div>
                      <div className="flex justify-between text-sm"><span className="text-violet">Linked SYNTHETIC jobs</span><span className="data">{fmtInt(m.synthetic_linked)}</span></div>
                    </div>
                    <div className="flex h-3 overflow-hidden rounded-full bg-raised" aria-label="Real versus synthetic records in the database">
                      <div className="bg-accent" style={{ width: `${(dash.data.database.real_records / Math.max(1, dash.data.database.real_records + dash.data.database.synthetic_records)) * 100}%` }} />
                      <div className="synthetic-hatch bg-violet/40" style={{ flex: 1 }} />
                    </div>
                    <div className="flex justify-between text-xs text-muted">
                      <span>Database: {fmtInt(dash.data.database.real_records)} real</span>
                      <span className="text-violet">{fmtInt(dash.data.database.synthetic_records)} synthetic</span>
                    </div>
                    <p className="text-xs text-faint">Synthetic records are stored separately and never enter real-data statistics.</p>
                  </div>
                </Panel>
              </div>
            </>
          )}

          <Panel eyebrow="activity" title="Recent analyses">
            {dash.data?.recent.length ? (
              <ul className="divide-y divide-line/70">
                {dash.data.recent.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                    <span className={`h-2 w-2 rounded-full ${r.status === "completed" ? "bg-good" : r.status === "failed" ? "bg-bad" : "bg-warn animate-pulse"}`} />
                    <span className="font-display text-base">{r.gene_symbol}</span>
                    <span className="data text-xs text-faint">{r.id} · {r.dataset}</span>
                    <span className="flex-1 text-xs text-muted">{fmtDate(r.created_at)}</span>
                    {r.status === "completed" && r.id !== analysisId && <button className="btn-ghost !py-1 text-xs" onClick={() => select(r.id)}><Sigma size={12} />Open</button>}
                    {r.id === analysisId && <span className="chip border-accent/40 text-accent">active</span>}
                    {r.status === "failed" && <span className="max-w-xs truncate text-xs text-bad" title={r.error ?? ""}>{r.error}</span>}
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No analyses yet.</p>}
          </Panel>
          <Disclaimer compact />
        </div>
      </div>
    </motion.div>
  );
}

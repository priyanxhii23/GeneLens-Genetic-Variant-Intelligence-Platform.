/** Analysis history & provenance (formerly the standalone History page) – embedded in the Report Generator. */
import { AnimatePresence, motion } from "framer-motion";
import { FolderOpen, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ErrorState, HelixLoader, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { fmtDate, fmtInt } from "../../lib/format";

export default function ProvenanceHistory() {
  const { analysisId, select } = useAnalysis();
  const nav = useNavigate();
  const hist = useFetch(() => api.history(), []);
  const [expanded, setExpanded] = useState<string | null>(null);
  const det = useFetch(expanded ? () => api.historyDetail(expanded) : null, [expanded]);

  const remove = async (id: string) => {
    if (!window.confirm(`Delete analysis ${id} and all its stored records, flags and export history? This cannot be undone.`)) return;
    await api.deleteAnalysis(id);
    if (id === analysisId) select(null);
    hist.reload();
  };

  return (
    <Panel eyebrow="research history" title="Analysis history & provenance">
      <p className="mb-4 text-[14.5px] text-muted">Every analysis is stored with its gene, dataset release, retrieval dates, parameters, record counts and exports. Reopen one to restore it across all modules.</p>
      {hist.loading && <HelixLoader label="Loading history" />}
      {hist.error && <ErrorState message={hist.error} onRetry={hist.reload} />}
      <ul className="relative space-y-3 before:absolute before:bottom-2 before:left-[9px] before:top-2 before:w-px before:bg-line">
        {hist.data?.map((h) => (
          <motion.li key={h.id} layout className="relative pl-8">
            <span className={`absolute left-[4px] top-4 h-3 w-3 rounded-full ring-4 ring-surface ${h.status === "completed" ? "bg-accent" : h.status === "failed" ? "bg-bad" : "bg-warn"}`} />
            <div className="rounded-xl border border-line bg-raised/40 p-3.5 transition-colors hover:border-accent/30">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="font-display text-[19px]">{h.gene_symbol}</span>
                <span className="data text-[11.5px] text-faint">{h.id}</span>
                <span className="chip border-line text-muted">{h.dataset} · {h.reference_genome}</span>
                {h.id === analysisId && <span className="chip border-accent/40 text-accent">active</span>}
                <span className="flex-1" />
                <span className="text-[12.5px] text-muted">{fmtDate(h.created_at)}</span>
                {h.status === "completed" && <button className="btn-ghost !py-1 text-xs" onClick={() => { select(h.id); nav("/workspace"); }}><FolderOpen size={13} />Reopen</button>}
                <button className="btn-ghost !py-1 text-xs" onClick={() => setExpanded(expanded === h.id ? null : h.id)}>{expanded === h.id ? "Hide" : "Provenance"}</button>
                <button className="btn-ghost !px-2 !py-1 hover:!text-bad" onClick={() => remove(h.id)} aria-label={`Delete analysis ${h.id}`}><Trash2 size={13} /></button>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-4 text-[12.5px] text-muted">
                <span>status: <b className={h.status === "failed" ? "text-bad" : "text-ink"}>{h.status}</b></span>
                <span>real records: <span className="data text-ink">{fmtInt(h.real_count)}</span></span>
                <span>linked synthetic: <span className="data text-pink">{fmtInt(h.synthetic_count)}</span></span>
                <span>matched: <span className="data text-ink">{fmtInt(h.matched)}</span></span>
                <span>flags: <span className="data text-ink">{fmtInt(h.flags)}</span></span>
              </div>
              {h.error && <p className="mt-2 text-[12.5px] text-bad">{h.error}</p>}
              <AnimatePresence>
                {expanded === h.id && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                    {det.loading && <div className="pt-3"><HelixLoader label="Loading provenance" /></div>}
                    {det.data && (
                      <div className="mt-3 grid gap-4 lg:grid-cols-2">
                        <div>
                          <div className="eyebrow mb-2">datasets & sources</div>
                          <ul className="space-y-2 text-[12.5px]">{det.data.datasets.map((d, i) => (
                            <li key={i} className="rounded-lg bg-surface/70 p-2"><b>{d.source}</b> · {d.release} · {d.access_mode} · {fmtInt(d.record_count)} records<br />
                              <span className="text-faint">retrieved {fmtDate(d.retrieved_at)} · {d.query}</span></li>))}</ul>
                          <div className="eyebrow mb-2 mt-4">parameters</div>
                          <pre className="overflow-x-auto rounded-lg bg-bg/60 p-3 font-mono text-[11.5px] text-muted scrollbar-thin">{JSON.stringify(det.data.analysis.parameters, null, 2)}</pre>
                        </div>
                        <div>
                          <div className="eyebrow mb-2">exports</div>
                          {det.data.exports.length ? <ul className="space-y-1 text-[12.5px]">{det.data.exports.map((e) => (
                            <li key={e.id} className="flex gap-2"><span className="text-muted">{e.kind}</span><a className="truncate font-mono text-accent underline decoration-dotted" href={api.downloadUrl(e.id)}>{e.filename}</a></li>))}</ul>
                            : <p className="text-[12.5px] text-muted">None.</p>}
                          <div className="eyebrow mb-2 mt-4">synthetic jobs</div>
                          {det.data.synthetic_jobs.length ? <ul className="space-y-1 text-[12.5px] text-pink">{det.data.synthetic_jobs.map((j) => <li key={j.id}>{j.id} · {fmtInt(j.n_records)} records · seed {j.seed} · {fmtDate(j.created_at)}</li>)}</ul>
                            : <p className="text-[12.5px] text-muted">None.</p>}
                          {det.data.results && <p className="mt-4 text-[12.5px] text-faint">Pipeline runtime: {det.data.results.runtime_seconds}s</p>}
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.li>
        ))}
        {hist.data?.length === 0 && <li className="pl-8 text-muted">No analyses yet. Run one from the Command Center.</li>}
      </ul>
    </Panel>
  );
}

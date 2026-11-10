import { motion } from "framer-motion";
import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { Disclaimer, ErrorState, HelixLoader, NeedsAnalysis, PageHeader, Panel, stagger } from "../../components/ui";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { fmtDate } from "../../lib/format";

const SECTIONS = ["Project title & selected gene", "Dataset information & retrieval dates", "Methodology", "Dataset statistics & matching",
  "Variant classification analysis (charts)", "Population frequency analysis (chart)", "Gene constraint findings (chart)",
  "Statistical results with FDR correction", "Flagged variants (top 25)", "Research interpretation (computed only)", "Limitations",
  "Data source citations", "Medical & research disclaimer"];

export default function Reports() {
  const { analysisId, detail } = useAnalysis();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const list = useFetch(analysisId ? () => api.reports(analysisId) : null, [analysisId]);
  if (!analysisId) return <NeedsAnalysis />;

  const gen = async (format: "pdf" | "csv") => {
    setBusy(format); setErr(null);
    try {
      const rec = await api.generateReport(analysisId, format);
      list.reload();
      window.location.href = api.downloadUrl(rec.id);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(null); }
  };
  const findings = detail?.results?.interpretation.findings ?? [];

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="09" title="Research Report Generator" subtitle={`Generate downloadable reports for ${detail?.analysis.gene_symbol ?? "the active analysis"}. Every sentence in the interpretation is derived from a computed value – no invented conclusions.`} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div className="space-y-4">
          {[{ f: "pdf" as const, icon: FileText, t: "PDF research report", d: "Full report with Matplotlib/Seaborn charts, tables, methodology, limitations, citations and disclaimer." },
            { f: "csv" as const, icon: FileSpreadsheet, t: "CSV statistics report", d: "Flat table of dataset provenance, matching counts, descriptive statistics, test results, anomaly counts and constraint metrics." }].map(({ f, icon: Icon, t, d }) => (
            <motion.button key={f} whileHover={{ y: -3 }} onClick={() => gen(f)} disabled={!!busy || detail?.analysis.status !== "completed"} className="panel group flex w-full items-start gap-4 p-5 text-left disabled:opacity-50">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent"><Icon size={22} /></span>
              <span className="flex-1"><span className="block font-display text-lg">{t}</span><span className="mt-1 block text-sm text-muted">{d}</span></span>
              <Download size={16} className="mt-1 text-faint group-hover:text-accent" />
            </motion.button>
          ))}
          {busy && <HelixLoader label={`Rendering ${busy.toUpperCase()} report`} />}
          {err && <ErrorState message={err} />}
          <Panel eyebrow="pdf contents" title="Report sections">
            <ol className="grid gap-1.5 text-sm text-muted sm:grid-cols-2">{SECTIONS.map((s, i) => <li key={s}><span className="data mr-2 text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>{s}</li>)}</ol>
          </Panel>
        </div>
        <div className="space-y-6">
          <Panel eyebrow="preview" title="Research interpretation">
            <ul className="space-y-2 text-sm">{findings.map((f) => <li key={f} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-accent" /><span className="text-muted">{f}</span></li>)}</ul>
          </Panel>
          <Panel eyebrow="exports" title="Generated files">
            {list.data?.length ? (
              <ul className="divide-y divide-line/70 text-sm">{list.data.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-3 py-2"><span className="chip border-line text-muted">{r.kind.replace(/_/g, " ")}</span>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs" title={r.filename}>{r.filename}</span>
                  <span className="text-xs text-faint">{(r.size_bytes / 1024).toFixed(0)} KB · {fmtDate(r.created_at)}</span>
                  <a className="btn-ghost !px-2 !py-1" href={api.downloadUrl(r.id)} aria-label={`Download ${r.filename}`}><Download size={13} /></a></li>))}</ul>
            ) : <p className="text-sm text-muted">No exports yet for this analysis.</p>}
          </Panel>
          <Disclaimer compact />
        </div>
      </div>
    </motion.div>
  );
}

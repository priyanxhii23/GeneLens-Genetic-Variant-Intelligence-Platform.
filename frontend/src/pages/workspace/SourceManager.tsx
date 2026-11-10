import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, ExternalLink, RefreshCw, XCircle } from "lucide-react";
import { useState } from "react";
import { ErrorState, Guide, GuideItem, Insight, PageHeader, Panel, Skeleton, stagger, Term } from "../../components/ui";
import { api } from "../../lib/api";
import { useFetch } from "../../lib/analysis";
import { fmtDate, fmtInt } from "../../lib/format";
import type { DatasetEntry, SourceEntry } from "../../lib/types";

const CATEGORY: Record<string, string> = {
  population_frequency: "Population frequency", clinical: "Clinical classification", annotation: "Gene & variant annotation",
  variant_catalogue: "Variant catalogue", reference: "Reference genome & tracks",
};

function SourceCard({ s, onRefreshed }: { s: SourceEntry; onRefreshed: (s: SourceEntry) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const refresh = async () => {
    setBusy(true); setErr(null);
    try { onRefreshed(await api.refreshSource(s.id)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const ok = s.available;
  return (
    <motion.article layout variants={{ hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0 } }}
      className={`panel panel-interactive flex flex-col p-5 ${ok ? "" : ok === false ? "border-bad/40" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="eyebrow">{CATEGORY[s.category] ?? s.category} · {s.provider}</div>
          <h3 className="card-title mt-1">{s.name}</h3>
        </div>
        <span className={`chip shrink-0 ${ok ? "border-good/50 bg-good/10 text-good shadow-glow-sm" : ok === false ? "border-bad/50 bg-bad/10 text-bad" : "border-line text-faint"}`}>
          {ok ? <CheckCircle2 size={12} /> : ok === false ? <XCircle size={12} /> : null}
          {ok ? "available" : ok === false ? "unavailable" : "not checked"}
        </span>
      </div>
      <p className="mt-2 text-[14px] text-muted">{s.used_for}</p>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-[13.5px]">
        <div className="col-span-2"><dt className="eyebrow">Integration method</dt><dd>{s.method}</dd></div>
        <div className="col-span-2"><dt className="eyebrow">Release / version</dt><dd className="break-words">{s.release ?? "—"}</dd></div>
        <div><dt className="eyebrow">Last successful connection</dt><dd>{fmtDate(s.last_success_at)}</dd></div>
        <div><dt className="eyebrow">Last retrieval</dt><dd>{fmtDate(s.last_retrieval_at)}</dd></div>
        <div><dt className="eyebrow">Records retrieved</dt><dd className="data">{fmtInt(s.records_retrieved)}</dd></div>
        <div><dt className="eyebrow">Latency</dt><dd className="data">{s.latency_ms !== null ? `${s.latency_ms} ms` : "—"}</dd></div>
      </dl>
      <div className="mt-3 flex flex-wrap gap-1.5">{s.provides.map((p) => <span key={p} className="chip border-line text-[11.5px] font-medium text-muted">{p}</span>)}</div>
      {s.detail && <p className="mt-3 text-[13px] text-faint">{s.detail}</p>}
      {s.last_error && (
        <div className="mt-3 flex gap-2 rounded-xl border border-warn/30 bg-warn/5 p-3 text-[12.5px] text-warn">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <span><b>Last error</b> ({fmtDate(s.last_error_at)}): {s.last_error.slice(0, 220)}</span>
        </div>
      )}
      {err && <div className="mt-3"><ErrorState message={err} /></div>}
      <div className="mt-auto flex items-center justify-between gap-2 pt-4">
        <a href={s.homepage} target="_blank" rel="noreferrer" className="flex min-w-0 items-center gap-1 text-[13px] text-accent hover:underline" title={s.endpoint}><span className="truncate">{s.endpoint.replace("https://", "")}</span><ExternalLink size={12} className="shrink-0" /></a>
        <button className="btn-ghost shrink-0 !py-1.5 text-[13px]" onClick={refresh} disabled={busy} aria-label={`Refresh ${s.name}`}>
          <RefreshCw size={13} className={busy ? "animate-spin" : ""} />{busy ? "Checking…" : "Refresh"}
        </button>
      </div>
    </motion.article>
  );
}

function DatasetTable({ data }: { data: DatasetEntry[] }) {
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[860px]">
        <thead><tr>{["Dataset", "Provider", "Assembly", "Release", "Data type", "Status"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.id} className="transition-colors hover:bg-raised/50">
              <td className="table-cell"><div className="font-semibold">{d.name}</div><div className="data text-[11.5px] text-faint">{d.id}</div></td>
              <td className="table-cell text-[13px]">{d.provider}</td>
              <td className="table-cell"><span className="chip border-line font-mono text-muted">{d.assembly}</span></td>
              <td className="table-cell max-w-[240px] text-[12.5px] text-muted">{d.release}</td>
              <td className="table-cell text-[13px]">{d.data_type.replace("_", " ")}</td>
              <td className="table-cell"><span title={d.status_detail} className={`chip ${d.status === "available" ? "border-good/40 text-good" : "border-bad/40 text-bad"}`}>{d.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function SourceManager() {
  const src = useFetch(() => api.sourceList(), []);
  const ds = useFetch(() => api.datasets(), []);
  const [refreshing, setRefreshing] = useState(false);
  const refreshAll = async () => {
    setRefreshing(true);
    try { src.setData(await api.sourceList(true)); ds.setData(await api.datasets(true)); } finally { setRefreshing(false); }
  };
  const up = src.data?.filter((s) => s.available).length ?? 0;
  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="11" title="Source Manager"
        subtitle="Seven integrated data providers behind the ten datasets. Each status comes from a real request made by the backend – nothing on this page is simulated."
        actions={<button className="btn-primary" onClick={refreshAll} disabled={refreshing}><RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />{refreshing ? "Checking all sources…" : "Refresh all"}</button>} />
      {src.data && (
        <Insight label="Connection summary" tone={up === src.data.length ? "good" : "warn"}
          reason={`${up} of ${src.data.length} sources are currently reachable from the GeneLens backend.`}>
          <p>Each check performs a small live request (for example an <b>einfo</b> call to NCBI, a schema query to gnomAD, or a <b>HEAD</b> request for the 1000 Genomes index). If a source is unreachable, analyses that need it fail with an explicit error, or – for gnomAD and ClinVar – fall back to cached responses or a <b>clearly labelled offline snapshot</b>. Unavailable sources are never shown as available.</p>
        </Insight>
      )}
      {src.error && <ErrorState message={src.error} onRetry={src.reload} />}
      {!src.data && src.loading && <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-72" />)}</div>}
      <motion.div variants={stagger} className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        <AnimatePresence>
          {src.data?.map((s) => <SourceCard key={s.id} s={s} onRefreshed={(n) => src.setData(src.data!.map((x) => (x.id === n.id ? n : x)))} />)}
        </AnimatePresence>
      </motion.div>
      <Panel eyebrow="dataset registry" title="Ten analysable datasets">
        {ds.data ? <DatasetTable data={ds.data} /> : <Skeleton className="h-64" />}
        <p className="mt-3 text-[13px] text-muted">Population-frequency datasets provide <Term k="AC">AC</Term>/<Term k="AN">AN</Term>/<Term k="AF">AF</Term>; the ClinVar dataset provides classifications only; dbSNP provides RefSNP alleles with per-study frequencies. Datasets on different <Term k="GRCh38">assemblies</Term> are never mixed without coordinate conversion.</p>
      </Panel>
      <Guide title="How the data ecosystem fits together">
        <GuideItem term="Datasets vs sources">A <b>dataset</b> is what you analyse (e.g. gnomAD v4). A <b>source</b> is the service that delivers it (e.g. the gnomAD GraphQL API). Some datasets use several sources – 1000 Genomes needs <b>IGSR</b> for the data and <b>Ensembl</b> for the gene's GRCh37 coordinates.</GuideItem>
        <GuideItem term="Records retrieved">A running total of records fetched live from each source by this GeneLens installation. Cached re-use is not counted, so the number reflects real downloads.</GuideItem>
        <GuideItem term="Assemblies">Each dataset is tied to a reference genome (<b>GRCh38</b> or <b>GRCh37</b>). ClinVar records are converted using ClinVar's own coordinates on both assemblies before matching. Records without coordinates on the needed assembly are kept as <b>unmatchable</b>, never guessed.</GuideItem>
        <GuideItem term="If something is unavailable">Public APIs sometimes rate-limit or go down. Press <b>Refresh</b> to re-check. An NCBI API key in <span className="data">backend/.env</span> raises NCBI's rate limit from 3 to 10 requests per second.</GuideItem>
      </Guide>
    </motion.div>
  );
}

/**
 * Custom Dataset Lab – upload a researcher's own variant file, inspect it, confirm the column
 * mapping and genome assembly, then run it through the GeneLens pipeline. Everything here is
 * labelled CUSTOM DATA and stored separately from the official REAL datasets.
 */
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, CheckCircle2, ChevronDown, Compass, Download, FileUp, Pencil, Play, Plus, RefreshCw, Trash2, Upload, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import Plot from "../../components/Plot";
import {
  ClassBadge, ErrorState, Guide, GuideItem, HelixLoader, Insight, Metric, PageHeader, Panel, PriorityBadge, ProvenanceBadge,
  Skeleton, stagger, Term,
} from "../../components/ui";
import VariantDrawer from "../../components/VariantDrawer";
import { api, uploadCustomDataset } from "../../lib/api";
import { useFetch } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtDate, fmtInt, fmtP, token } from "../../lib/format";
import type { Assembly, CoarseClass, CustomDataset, CustomFlag, VariantRow } from "../../lib/types";

const ACCEPT = ".csv,.tsv,.txt,.vcf,.gz,.json";
const STAGES = ["Validating and normalising records", "Matching with ClinVar", "Storing records", "Running statistics",
  "Population summary", "Screening for anomalies", "Writing cleaned dataset"];
const fmtBytes = (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const STATUS_TONE: Record<string, string> = { inspected: "accent", queued: "warn", processing: "warn", completed: "good", failed: "bad" };
const STATUS_LABEL: Record<string, string> = { inspected: "awaiting confirmation", queued: "queued", processing: "processing", completed: "analysed", failed: "failed" };

function CustomChip() {
  return <span className="chip border-violet/50 bg-violet/10 font-semibold text-violet"><Upload size={11} />CUSTOM DATA</span>;
}

// ---------------------------------------------------------------------------------------- upload
function UploadPanel({ onUploaded, onCancel }: { onUploaded: (d: CustomDataset) => void; onCancel?: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [drag, setDrag] = useState(false);
  const [sent, setSent] = useState<{ loaded: number; total: number } | null>(null);
  const [phase, setPhase] = useState<"idle" | "uploading" | "inspecting">("idle");
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const pick = (f: File | undefined) => {
    if (!f) return;
    setErr(null); setFile(f); setName(f.name.replace(/\.(vcf\.gz|[a-z]+)$/i, ""));
    if (!/\.(csv|tsv|txt|vcf|vcf\.gz|vcf\.bgz|json)$/i.test(f.name)) setErr("Unsupported file type. Upload CSV, TSV, TXT, VCF, VCF.GZ or JSON.");
  };
  const fmt = file ? (file.name.toLowerCase().match(/\.(vcf\.gz|vcf\.bgz|[a-z0-9]+)$/)?.[1] ?? "?").toUpperCase() : "";
  const start = async () => {
    if (!file) return;
    setErr(null); setPhase("uploading"); setSent({ loaded: 0, total: file.size });
    try {
      const d = await uploadCustomDataset(file, name.trim() || undefined, (loaded, total) => {
        setSent({ loaded, total });
        if (loaded >= total) setPhase("inspecting");
      });
      onUploaded(d);
    } catch (e) { setErr((e as Error).message); setPhase("idle"); }
  };
  const busy = phase !== "idle";
  return (
    <Panel eyebrow="custom dataset lab" title="Add a custom dataset" actions={<>{<CustomChip />}{onCancel && <button className="btn-ghost !px-2" onClick={onCancel} aria-label="Close upload"><X size={15} /></button>}</>}>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); if (!busy) pick(e.dataTransfer.files?.[0]); }}
        className={`flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${drag ? "border-violet bg-violet/10" : "border-line hover:border-violet/60"}`}
        data-testid="dropzone">
        <FileUp size={34} className="text-violet" />
        <div className="text-[16px] font-semibold">Drag & drop a variant file here</div>
        <div className="text-[13.5px] text-muted">CSV · TSV · TXT · VCF · VCF.GZ · JSON — up to 200 MB</div>
        <button className="btn-ghost" onClick={() => input.current?.click()} disabled={busy}>Browse files</button>
        <input ref={input} type="file" accept={ACCEPT} className="hidden" data-testid="file-input" onChange={(e) => pick(e.target.files?.[0])} />
      </div>
      {file && (
        <div className="mt-4 grid gap-3 rounded-xl border border-line p-4 md:grid-cols-[1fr_auto] md:items-end">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="sm:col-span-3"><label className="eyebrow" htmlFor="ds-name">Dataset name</label>
              <input id="ds-name" className="input mt-1 w-full" value={name} maxLength={160} onChange={(e) => setName(e.target.value)} disabled={busy} /></div>
            <div><div className="eyebrow">File</div><div className="truncate text-[14px]" title={file.name}>{file.name}</div></div>
            <div><div className="eyebrow">Size</div><div className="data text-[14px]">{fmtBytes(file.size)}</div></div>
            <div><div className="eyebrow">Format</div><div className="data text-[14px]">{fmt}</div></div>
          </div>
          <button className="btn-primary" onClick={start} disabled={busy || !!err}><Upload size={15} />{busy ? "Working…" : "Upload & inspect"}</button>
        </div>
      )}
      {busy && sent && (
        <div className="mt-4" aria-live="polite">
          <div className="flex justify-between text-[13px] text-muted">
            <span>{phase === "uploading" ? "Uploading" : "Validating format and inspecting columns…"}</span>
            <span className="data">{fmtBytes(sent.loaded)} / {fmtBytes(sent.total)}</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-raised">
            <div className={`h-full rounded-full bg-violet transition-[width] ${phase === "inspecting" ? "animate-pulse" : ""}`} style={{ width: `${sent.total ? (100 * sent.loaded) / sent.total : 0}%` }} />
          </div>
        </div>
      )}
      {err && <div className="mt-4"><ErrorState message={err} /></div>}
      <p className="mt-4 text-[13px] text-muted">Your file is stored only on this GeneLens installation (backend <span className="data">data/uploads</span>). Nothing is sent to external services except gene symbols, when you choose ClinVar matching.</p>
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------- inspection & mapping
function InspectionPanel({ ds, onChanged }: { ds: CustomDataset; onChanged: (d: CustomDataset) => void }) {
  const ins = ds.inspection!;
  const [mapping, setMapping] = useState<Record<string, string | null>>(ds.mapping ?? ins.suggested_mapping);
  const [assembly, setAssembly] = useState<Assembly>(ds.assembly);
  const [clinvar, setClinvar] = useState(ds.options?.clinvar ?? true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setMapping(ds.mapping ?? ins.suggested_mapping); setAssembly(ds.assembly); setClinvar(ds.options?.clinvar ?? true); }, [ds.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const used = Object.values(mapping).filter(Boolean) as string[];
  const dupCol = used.find((c, i) => used.indexOf(c) !== i);
  const hasCoords = (mapping.chrom && mapping.pos && mapping.ref && mapping.alt) || mapping.variant_id;
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      await api.updateCustomDataset(ds.id, { mapping, assembly, clinvar });
      onChanged(await api.processCustomDataset(ds.id));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const genomic = ["chrom", "pos", "ref", "alt", "variant_id"].filter((f) => mapping[f]);
  const clinical = ["clinical_significance", "review_status"].filter((f) => mapping[f]);
  const counts = ["af", "ac", "an"].filter((f) => mapping[f]);
  return (
    <div className="stack">
      <div className="layout-metrics">
        <Metric label="Records" value={ins.row_count} hint="ALT alleles counted separately" />
        <Metric label="Columns" value={ins.columns.length} />
        <Metric label="Population columns" value={Object.keys(ins.population_columns).length} tone="violet" />
        <Metric label="Columns with gaps" value={Object.values(ins.missing_by_column).filter((n) => n > 0).length} tone="warn" />
      </div>
      <Panel eyebrow="automatic inspection" title="What GeneLens found in the file" actions={<CustomChip />}>
        <ul className="grid gap-2 text-[14px] md:grid-cols-2">
          <Found ok={genomic.length > 0} label="Genomic fields">{genomic.length ? genomic.map((f) => ins.field_labels[f]).join(", ") : "none recognised – map them below"}</Found>
          <Found ok={counts.length > 0} label="Frequency fields (AC / AN / AF)">{counts.length ? counts.map((f) => f.toUpperCase()).join(", ") : "not present – frequency analyses will be unavailable"}</Found>
          <Found ok={clinical.length > 0} label="Clinical classification">{clinical.length ? clinical.map((f) => ins.field_labels[f]).join(", ") : "not present – can be retrieved from ClinVar when the assembly is known"}</Found>
          <Found ok={Object.keys(ins.population_columns).length > 0} label="Population fields">{Object.keys(ins.population_columns).join(", ").toUpperCase() || "none"}</Found>
          <Found ok={ins.assembly.value !== "unknown"} label="Genome assembly">{ins.assembly.value === "unknown" ? "not stated in the file" : `${ins.assembly.value} (from file header)`}</Found>
          <Found ok={ins.issues.length === 0} label="Schema">{ins.issues.length ? ins.issues.join(" ") : "a complete set of variant coordinates is available"}</Found>
        </ul>
      </Panel>

      <Panel eyebrow={`preview · first ${ins.preview.length} of ${fmtInt(ins.row_count)} records`} title="Check the data before processing">
        <div className="max-h-[420px] overflow-auto scrollbar-thin rounded-xl border border-line">
          <table className="w-full text-[12.5px]" data-testid="preview-table">
            <thead className="sticky top-0 z-[1] bg-panel"><tr>{ins.columns.map((c) => (
              <th key={c} className="table-head whitespace-nowrap">{c}{ins.missing_by_column[c] > 0 && <span className="ml-1 text-warn" title={`${ins.missing_by_column[c]} missing values`}>· {fmtInt(ins.missing_by_column[c])} missing</span>}</th>
            ))}</tr></thead>
            <tbody>{ins.preview.map((r, i) => (
              <tr key={i} className="border-t border-line/60">{ins.columns.map((c) => (
                <td key={c} className="whitespace-nowrap px-3 py-1.5 font-mono">{r[c] === null || r[c] === "" ? <span className="text-faint">—</span> : String(r[c]).slice(0, 60)}</td>
              ))}</tr>
            ))}</tbody>
          </table>
        </div>
        <p className="mt-2 text-[12.5px] text-muted">"—" marks an empty cell. Empty values stay missing during analysis; they are never treated as zero.</p>
      </Panel>

      <Panel eyebrow="column mapping" title="Confirm which column holds which field">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Object.keys(ins.field_labels).map((f) => (
            <label key={f} className="block">
              <span className="eyebrow">{ins.field_labels[f]}{["chrom", "pos", "ref", "alt"].includes(f) && <span className="text-violet"> *</span>}</span>
              <select className="input mt-1 w-full" value={mapping[f] ?? ""} data-field={f}
                onChange={(e) => setMapping({ ...mapping, [f]: e.target.value || null })}>
                <option value="">— not in file —</option>
                {ins.columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          ))}
        </div>
        {dupCol && <p className="mt-3 text-[13px] text-bad">Column “{dupCol}” is mapped to more than one field.</p>}
        {!hasCoords && <p className="mt-3 text-[13px] text-warn">Map chromosome, position, reference and alternate (*) – or a variant identifier like 1-12345-A-G.</p>}
      </Panel>

      <Panel eyebrow="genome assembly" title="Which reference genome are the coordinates on?">
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Genome assembly">
          {(["GRCh38", "GRCh37", "unknown"] as Assembly[]).map((a) => (
            <button key={a} role="radio" aria-checked={assembly === a} onClick={() => setAssembly(a)}
              className={`chip !px-4 !py-2 text-[14px] ${assembly === a ? "border-violet bg-violet/15 text-ink" : "border-line text-muted hover:border-violet/50"}`}>
              {a === "unknown" ? "Unknown" : a}
            </button>
          ))}
        </div>
        <p className="mt-3 text-[13.5px] text-muted">
          {ins.assembly.value !== "unknown" ? <>Detected <b>{ins.assembly.value}</b> from the file header{ins.assembly.evidence[0] ? <> (<span className="data">{ins.assembly.evidence[0].slice(0, 80)}</span>)</> : null}.</> : ins.assembly.note}
          {" "}GeneLens never guesses an assembly from coordinates and never merges data across assemblies. With “Unknown”, ClinVar matching is disabled.
        </p>
        <label className="mt-4 flex items-start gap-2 text-[14px]">
          <input type="checkbox" className="mt-1" checked={clinvar} onChange={(e) => setClinvar(e.target.checked)} />
          <span><b>Match against ClinVar</b> (exact allele matches, using the mapped gene symbols). {mapping.clinical_significance ? "Your own classifications are kept; ClinVar is used only for a concordance comparison." : "ClinVar classifications are added as retrieved annotations."}</span>
        </label>
      </Panel>
      {err && <ErrorState message={err} />}
      <div className="flex flex-wrap items-center justify-end gap-3">
        <span className="text-[13px] text-muted">The preview above looks right? Run the full pipeline on all {fmtInt(ins.row_count)} records.</span>
        <button className="btn-primary" onClick={run} disabled={busy || !hasCoords || !!dupCol} data-testid="run-analysis"><Play size={15} />{busy ? "Starting…" : "Run GeneLens Analysis"}</button>
      </div>
    </div>
  );
}

function Found({ ok, label, children }: { ok: boolean; label: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-2.5 rounded-xl border border-line/70 p-3">
      {ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-good" /> : <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" />}
      <span><b>{label}</b><br /><span className="text-muted">{children}</span></span>
    </li>
  );
}

// ---------------------------------------------------------------------------------------- processing
function Processing({ ds }: { ds: CustomDataset }) {
  const current = STAGES.findIndex((s) => ds.stage?.startsWith(s.split(" ")[0]) && ds.stage?.includes(s.split(" ").slice(-1)[0]));
  const idx = ds.stage?.startsWith("Retrieving ClinVar") ? 1 : current;
  return (
    <Panel eyebrow="processing" title={`Analysing “${ds.name}”`} actions={<CustomChip />}>
      <HelixLoader label={ds.stage ?? "Queued"} />
      <ol className="mt-4 grid gap-1.5 text-[14px]">
        {STAGES.map((s, i) => (
          <li key={s} className={`flex items-center gap-2 ${i < idx ? "text-good" : i === idx ? "font-semibold text-ink" : "text-faint"}`}>
            {i < idx ? <CheckCircle2 size={14} /> : <span className={`h-2 w-2 rounded-full ${i === idx ? "animate-pulse bg-violet" : "bg-line"}`} />}{s}
            {i === idx && ds.stage && ds.stage !== s && <span className="text-[12.5px] font-normal text-muted">– {ds.stage}</span>}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[12.5px] text-muted">Stages are reported by the backend as they happen. ClinVar retrieval depends on NCBI's response time.</p>
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------- dashboard
const FIELD_STATUS_LABEL: Record<string, string> = { allele_frequency: "Allele frequency", classification: "Clinical classification", populations: "Population frequencies", assembly: "Genome assembly", review_status: "Review status" };

function statusTone(v: string) { return v.startsWith("unavailable") || v === "unknown" ? "faint" : v.startsWith("retrieved") ? "accent" : v.startsWith("calculated") || v.startsWith("mixed") ? "good" : "violet"; }

function Dashboard({ ds }: { ds: CustomDataset }) {
  const s = ds.summary!;
  const [drawer, setDrawer] = useState<number | null>(null);
  const [shown, setShown] = useState(10);
  const classes = Object.entries(s.classification_distribution).sort((a, b) => b[1] - a[1]);
  const edges = s.af_distribution.edges;
  const plp = s.statistics.tests.find((t) => t.comparison === "P/LP vs B/LB");
  return (
    <div className="stack">
      <div className="layout-metrics">
        <Metric label="Total records" value={s.totals.rows} tone="violet" />
        <Metric label="Valid" value={s.totals.valid} tone="good" hint={`${fmtInt(s.totals.unique_valid)} distinct alleles analysed`} />
        <Metric label="Invalid" value={s.totals.invalid} tone="bad" hint="coordinates or alleles unusable" />
        <Metric label="Duplicates" value={s.totals.duplicates} tone="warn" hint="same chrom-pos-ref-alt" />
        <Metric label="With missing values" value={s.totals.records_with_missing_fields} tone="warn" hint="no AF or invalid coordinates" />
      </div>
      <Insight label="Where each result comes from" tone="accent" reason="GeneLens separates values read from your file, values it calculated, values retrieved from external sources, and values that are unavailable.">
        <ul className="grid gap-2 sm:grid-cols-2">
          {Object.entries(s.field_status).map(([k, v]) => (
            <li key={k} className="flex flex-wrap items-center gap-2"><b>{FIELD_STATUS_LABEL[k] ?? k}</b><span className={`chip border-${statusTone(v)}/40 text-${statusTone(v)}`}>{v}</span></li>
          ))}
        </ul>
      </Insight>
      <div className="layout-halves">
        <Panel eyebrow="classification" title="Classification distribution">
          {classes.length ? <Plot height={300} data={[{ type: "bar", orientation: "h", y: classes.map(([c]) => CLASS_META[c as CoarseClass]?.label ?? c), x: classes.map(([, n]) => n),
            marker: { color: classes.map(([c]) => token(CLASS_META[c as CoarseClass]?.color ?? "other")) }, hovertemplate: "%{y}: %{x}<extra></extra>" }]}
            layout={{ margin: { l: 210, r: 16, t: 16, b: 40 }, xaxis: { title: { text: "records" } } }} /> : <p className="text-muted">No records.</p>}
          <p className="mt-2 text-[13px] text-muted">“Not in ClinVar” here means the record has no classification – neither in your file nor retrieved.</p>
        </Panel>
        <Panel eyebrow="allele frequency" title="Allele-frequency distribution">
          {s.af_distribution.with_af ? <Plot height={300} data={[{ type: "bar", x: edges.slice(0, -1).map((e, i) => `1e${e}…1e${edges[i + 1]}`), y: s.af_distribution.counts, marker: { color: token("violet") }, hovertemplate: "%{x}: %{y}<extra></extra>" }]}
            layout={{ xaxis: { title: { text: "allele frequency (log10 bins)" }, tickangle: -35 }, yaxis: { title: { text: "records" } } }} />
            : <p className="py-10 text-center text-muted">No allele frequencies are available in this dataset.</p>}
          <p className="mt-2 text-[13px] text-muted">{fmtInt(s.af_distribution.with_af)} with AF &gt; 0 · {fmtInt(s.af_distribution.af_zero)} with AF = 0 (AC = 0) · {fmtInt(s.af_distribution.af_missing)} without AF (shown as missing, not zero).</p>
        </Panel>
      </div>
      <div className="layout-halves">
        <Panel eyebrow="statistics" title="Pathogenic vs benign frequency comparison">
          {plp?.ran ? (
            <div className="space-y-2 text-[14px]">
              <p><b>{plp.test}</b> on log10 AF: p = <span className="data">{fmtP(plp.p_value)}</span>{plp.p_adjusted_bh !== undefined && <> (FDR-adjusted <span className="data">{fmtP(plp.p_adjusted_bh)}</span>)</>}; effect size {plp.effect_size?.name} <span className="data">{plp.effect_size?.value?.toFixed(3) ?? "—"}</span> ({plp.effect_size?.magnitude ?? "n/a"}).</p>
              <p className="text-muted">A small p-value means the two groups' frequencies differ statistically in <i>this</i> dataset; the effect size says how large that difference is. Neither proves that any individual classification is right or wrong.</p>
            </div>
          ) : <p className="text-[14px] text-muted">Not calculated: {plp?.reason ?? "the dataset needs pathogenic and benign records with allele frequencies"}.</p>}
          <ul className="mt-3 divide-y divide-line/60 text-[13.5px]">
            {s.statistics.tests.filter((t) => t !== plp).map((t, i) => (
              <li key={i} className="flex flex-wrap justify-between gap-2 py-1.5"><span>{t.test}{t.comparison ? ` · ${t.comparison}` : ""}</span>
                <span className={t.ran ? "data" : "text-faint"}>{t.ran ? `p = ${fmtP(t.p_value)}` : `not run – ${t.reason ?? "insufficient data"}`}</span></li>
            ))}
          </ul>
        </Panel>
        <Panel eyebrow="clinvar" title="ClinVar matching">
          {s.clinvar.status === "unavailable" || s.clinvar.status === "skipped" ? (
            <p className="text-[14px] text-muted"><b className="text-ink">{s.clinvar.status === "skipped" ? "Skipped." : "Unavailable."}</b> {s.clinvar.reason}</p>
          ) : (
            <div className="space-y-3 text-[14px]">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[["Exact", s.clinvar.matched_exact], ["Normalised", s.clinvar.matched_normalized], ["Ambiguous", s.clinvar.ambiguous], ["No record", s.clinvar.no_clinvar_record]].map(([l, v]) => (
                  <div key={l as string}><div className="eyebrow">{l}</div><div className="data text-[20px]">{fmtInt(v as number)}</div></div>
                ))}
              </div>
              <p className="text-muted">Genes queried: {s.clinvar.genes_queried?.join(", ")} · {fmtInt(s.clinvar.clinvar_records_retrieved)} ClinVar records retrieved. {s.clinvar.note}</p>
              {s.clinvar.concordance && (
                <p>Concordance with your classifications: <b>{s.clinvar.concordance.agreement_rate === null ? "no overlapping records" : `${(s.clinvar.concordance.agreement_rate * 100).toFixed(1)}% agree`}</b> ({fmtInt(s.clinvar.concordance.agree)} agree, {fmtInt(s.clinvar.concordance.disagree)} differ).</p>
              )}
              {s.clinvar.errors?.map((e) => <p key={e.gene} className="text-warn">{e.gene}: {e.message}</p>)}
            </div>
          )}
        </Panel>
      </div>
      {s.populations && s.populations.groups.length > 0 && (
        <Panel eyebrow="populations" title="Population frequencies reported in the file">
          <div className="overflow-x-auto scrollbar-thin"><table className="w-full min-w-[620px] text-[13.5px]">
            <thead><tr>{["Population", "Variants observed", "Missing", "Median AN"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
            <tbody>{s.populations.groups.map((g) => (
              <tr key={g.id} className="border-t border-line/60"><td className="table-cell">{g.label}</td><td className="table-cell data">{fmtInt(g.variants_observed)}</td>
                <td className="table-cell data">{fmtInt(g.missing)}</td><td className="table-cell data">{g.median_an === null ? "not reported" : fmtInt(Math.round(g.median_an))}</td></tr>
            ))}</tbody>
          </table></div>
          <p className="mt-2 text-[13px] text-muted">Population frequencies describe groups in your dataset; they cannot be used to infer an individual's ancestry or disease risk.</p>
        </Panel>
      )}
      <div className="layout-halves">
        <Panel eyebrow="data quality" title="Quality checks">
          <ul className="divide-y divide-line/60 text-[14px]">
            {Object.entries(s.quality.qc_flag_counts).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
              <li key={k} className="flex justify-between py-1.5"><span>{QC_TEXT[k] ?? k.replace(/_/g, " ")}</span><span className="data">{fmtInt(n)}</span></li>
            ))}
            {Object.entries(s.missing_by_field).map(([k, n]) => (
              <li key={`m-${k}`} className="flex justify-between py-1.5"><span>Missing {k.toUpperCase()}</span><span className="data">{fmtInt(n)}</span></li>
            ))}
            {!Object.keys(s.quality.qc_flag_counts).length && !Object.keys(s.missing_by_field).length && <li className="py-2 text-good">No quality problems found.</li>}
          </ul>
        </Panel>
        <Panel eyebrow="composition" title="Genes and variant types">
          <div className="flex flex-wrap gap-1.5">{Object.entries(s.genes).map(([g, n]) => <span key={g} className="chip border-line"><b>{g}</b><span className="data text-muted">{fmtInt(n)}</span></span>)}</div>
          <div className="mt-3 flex flex-wrap gap-1.5">{Object.entries(s.variant_types).map(([g, n]) => <span key={g} className="chip border-line text-muted">{g} · {fmtInt(n)}</span>)}</div>
        </Panel>
      </div>
      <Panel eyebrow="anomaly screening" title={`Flagged records (${fmtInt(s.anomaly_summary.total)})`}>
        {s.anomalies.length ? <ul className="space-y-3">{s.anomalies.slice(0, shown).map((f, i) => <FlagCard key={i} f={f} onOpen={() => f.variant_id && setDrawer(f.variant_id)} />)}</ul>
          : <p className="text-[14px] text-muted">No records met the screening rules.</p>}
        {s.anomalies.length > shown && <div className="mt-3 flex items-center justify-between gap-2 text-[13px] text-muted"><span>Showing {shown} of {s.anomalies.length} flags (highest priority first); all are in the JSON export.</span><button className="btn-ghost !py-1" onClick={() => setShown(shown + 20)}>Show more</button></div>}
      </Panel>
      <RecordTable ds={ds} onOpen={setDrawer} />
      <VariantDrawer id={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}

const QC_TEXT: Record<string, string> = {
  duplicate_record: "Duplicate records (same allele repeated)", invalid_coordinates: "Invalid coordinates or alleles",
  af_reported_without_counts: "AF reported without AC/AN", af_inconsistent: "AF disagrees with AC/AN", ac_exceeds_an: "AC larger than AN",
  zero_an: "AN equal to zero", af_out_of_range: "AF outside 0–1", invalid_ac: "Non-numeric AC", invalid_an: "Non-numeric AN", invalid_af: "Non-numeric AF",
  ambiguous_match: "Ambiguous ClinVar match",
};

function FlagCard({ f, onOpen }: { f: CustomFlag; onOpen: () => void }) {
  const [open, setOpen] = useState(f.priority === "high");
  return (
    <li className={`panel overflow-hidden ${f.priority === "high" ? "border-bad/40" : f.priority === "medium" ? "border-warn/30" : ""}`}>
      <button className="w-full px-4 py-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <div className="flex flex-wrap items-center gap-2"><PriorityBadge p={f.priority} /><ProvenanceBadge p="CUSTOM" /><span className="ml-auto font-mono text-[12.5px] text-muted">{f.variant_key}</span></div>
        <div className="mt-2 flex gap-2"><div className="flex-1"><div className="eyebrow">Why was this variant flagged?</div><h4 className="font-display text-[19px]">{f.headline}</h4><p className="mt-1 text-[14.5px]">{f.reason}</p></div>
          <ChevronDown size={17} className={`mt-1 shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`} /></div>
      </button>
      <AnimatePresence initial={false}>{open && (
        <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
          <div className="grid gap-4 border-t border-line/70 px-4 py-3 md:grid-cols-2 text-[14px]">
            <div><div className="mb-1 font-bold">What this means</div><p className="text-muted">{f.why_it_matters}</p></div>
            <div><div className="mb-1 flex items-center gap-1.5 font-bold"><Compass size={14} className="text-accent" />Recommended next step</div><p className="text-muted">{f.recommendation}</p></div>
          </div>
          {f.variant_id && <div className="flex justify-end px-4 pb-3"><button className="btn-ghost !py-1.5 text-[13px]" onClick={onOpen}>Open record</button></div>}
        </motion.div>
      )}</AnimatePresence>
    </li>
  );
}

function RecordTable({ ds, onOpen }: { ds: CustomDataset; onOpen: (id: number) => void }) {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  useEffect(() => { const t = setTimeout(() => { setQuery(q); setPage(1); }, 250); return () => clearTimeout(t); }, [q]);
  const res = useFetch(() => api.variants({ custom_dataset_id: ds.id, page, page_size: 25, search: query || undefined }), [ds.id, page, query, ds.updated_at]);
  const d = res.data;
  return (
    <Panel eyebrow="records" title="Processed records" actions={<input className="input !min-h-0 w-56 !py-1.5" placeholder="Search key, gene, rsID…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search records" />}>
      {res.error && <ErrorState message={res.error} onRetry={res.reload} />}
      {!d ? <Skeleton className="h-64" /> : (
        <>
          <div className={`overflow-x-auto scrollbar-thin transition-opacity ${res.loading ? "opacity-60" : ""}`}><table className="w-full min-w-[760px] text-[13.5px]">
            <thead><tr>{["Variant", "Gene", "AF", "AC / AN", "Classification", "Quality"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
            <tbody>{d.items.map((v: VariantRow) => (
              <tr key={v.id} className="cursor-pointer border-t border-line/60 hover:bg-raised/50" onClick={() => onOpen(v.id)}>
                <td className="table-cell font-mono text-[12.5px]">{v.variant_key}</td><td className="table-cell">{v.gene_symbol ?? <span className="text-faint">—</span>}</td>
                <td className="table-cell data">{fmtAF(v.af)}</td><td className="table-cell data">{v.ac ?? "—"} / {v.an ?? "—"}</td>
                <td className="table-cell"><ClassBadge cls={v.coarse_class} label={v.clinical_significance} /></td>
                <td className="table-cell text-[12px] text-muted">{(v.qc_flags ?? []).map((f) => QC_TEXT[f] ?? f).join("; ") || "ok"}</td>
              </tr>
            ))}</tbody>
          </table></div>
          <div className="mt-3 flex items-center justify-between text-[13px] text-muted">
            <span>{fmtInt(d.total)} records</span>
            <span className="flex items-center gap-2"><button className="btn-ghost !py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>Page {d.page} / {Math.max(d.pages ?? 1, 1)}<button className="btn-ghost !py-1" disabled={page >= (d.pages ?? 1)} onClick={() => setPage(page + 1)}>Next</button></span>
          </div>
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------- management
function DatasetHeader({ ds, onChanged, onDeleted }: { ds: CustomDataset; onChanged: (d: CustomDataset) => void; onDeleted: () => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(ds.name);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setName(ds.name), [ds.name]);
  const act = async (fn: () => Promise<void>) => { setBusy(true); setErr(null); try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); } };
  const working = ds.status === "queued" || ds.status === "processing";
  return (
    <Panel bodyClass="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><CustomChip /><span className={`chip border-${STATUS_TONE[ds.status]}/40 text-${STATUS_TONE[ds.status]}`}>{STATUS_LABEL[ds.status]}</span><span className="chip border-line font-mono text-muted">{ds.assembly === "unknown" ? "assembly unknown" : ds.assembly}</span></div>
          {editing ? (
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); act(async () => { onChanged(await api.updateCustomDataset(ds.id, { name })); setEditing(false); }); }}>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={160} autoFocus aria-label="Dataset name" />
              <button className="btn-primary" disabled={busy || !name.trim()}>Save</button><button type="button" className="btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            </form>
          ) : <h2 className="mt-2 font-display text-[28px] leading-tight">{ds.name}</h2>}
          <div className="meta mt-1">{ds.filename} · {ds.file_format.toUpperCase()} · {fmtBytes(ds.size_bytes)} · uploaded {fmtDate(ds.created_at)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={() => setEditing(true)} disabled={busy || working}><Pencil size={14} />Rename</button>
          {(ds.status === "completed" || ds.status === "failed") && <button className="btn-ghost" disabled={busy} onClick={() => act(async () => onChanged(await api.processCustomDataset(ds.id)))}><RefreshCw size={14} />Reprocess</button>}
          {ds.status === "completed" && <>
            <a className="btn-ghost" href={api.customExportUrl(ds.id, "json")}><Download size={14} />Analysis JSON</a>
            <a className="btn-ghost" href={api.customExportUrl(ds.id, "csv")}><Download size={14} />Analysis CSV</a>
            <a className="btn-ghost" href={api.customCleanedUrl(ds.id)}><Download size={14} />Cleaned data</a>
          </>}
          <button className="btn-ghost text-bad" disabled={busy || working} onClick={() => { if (window.confirm(`Delete “${ds.name}” and all of its processed records? This cannot be undone.`)) act(async () => { await api.deleteCustomDataset(ds.id); onDeleted(); }); }}><Trash2 size={14} />Delete</button>
        </div>
      </div>
      {err && <div className="mt-3"><ErrorState message={err} /></div>}
    </Panel>
  );
}

function History({ ds }: { ds: CustomDataset }) {
  if (!ds.history?.length) return null;
  return (
    <Panel eyebrow="processing history" title="What happened to this dataset">
      <ol className="space-y-1.5 text-[13.5px]">{[...ds.history].reverse().map((h, i) => (
        <li key={i} className="flex flex-wrap gap-x-3"><span className="data text-faint">{fmtDate(h.at)}</span><b className="capitalize">{h.action}</b><span className="text-muted">{h.detail}</span></li>
      ))}</ol>
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------- page
export default function CustomDatasetLab() {
  const list = useFetch(() => api.customDatasets(), []);
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("id"));
  const [adding, setAdding] = useState(false);
  const [ds, setDs] = useState<CustomDataset | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const items = list.data ?? [];
  useEffect(() => { if (!selected && !adding && items.length) setSelected(items[0].id); }, [items, selected, adding]);
  const load = useCallback(async (id: string) => {
    try { setDs(await api.customDataset(id)); setErr(null); } catch (e) { setErr((e as Error).message); }
  }, []);
  useEffect(() => { if (selected) load(selected); else setDs(null); }, [selected, load]);
  // poll while processing; the stage names come from the backend
  useEffect(() => {
    if (!ds || (ds.status !== "queued" && ds.status !== "processing")) return;
    const t = setTimeout(() => load(ds.id), 1000);
    return () => clearTimeout(t);
  }, [ds, load]);
  const lastStatus = useRef<string | null>(null);
  useEffect(() => { if (ds && lastStatus.current && lastStatus.current !== ds.status) list.reload(); lastStatus.current = ds?.status ?? null; }, [ds?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const update = (d: CustomDataset) => { setDs((prev) => ({ ...(prev ?? {}), ...d } as CustomDataset)); list.reload(); if (d.status === "queued") load(d.id); };
  const view = useMemo(() => {
    if (adding || (!items.length && list.data)) return <UploadPanel onUploaded={(d) => { setAdding(false); setSelected(d.id); setDs(d); list.reload(); }} onCancel={items.length ? () => setAdding(false) : undefined} />;
    if (err) return <ErrorState message={err} onRetry={() => selected && load(selected)} />;
    if (!ds) return <Skeleton className="h-96" />;
    return (
      <div className="stack">
        <DatasetHeader ds={ds} onChanged={update} onDeleted={() => { setSelected(null); setDs(null); list.reload(); }} />
        {ds.status === "failed" && <ErrorState message={`Processing failed: ${ds.error ?? "unknown reason"}. Adjust the mapping or assembly below and run again.`} />}
        {(ds.status === "queued" || ds.status === "processing") && <Processing ds={ds} />}
        {ds.status === "completed" && ds.summary && <Dashboard ds={ds} />}
        {(ds.status === "inspected" || ds.status === "failed") && ds.inspection && <InspectionPanel ds={ds} onChanged={update} />}
        {ds.status === "completed" && ds.inspection && (
          <details className="panel p-5"><summary className="cursor-pointer font-semibold">Change mapping or assembly and reprocess</summary><div className="mt-4"><InspectionPanel ds={ds} onChanged={update} /></div></details>
        )}
        <History ds={ds} />
      </div>
    );
  }, [adding, items, list.data, err, ds, selected]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="stack">
      <PageHeader index="12" title="Custom Dataset Lab"
        subtitle={<>Upload your own variant dataset and run it through the same GeneLens pipeline – validation, normalisation, statistics, population summaries, ClinVar matching and anomaly screening. Uploaded data is labelled <b className="text-violet">CUSTOM DATA</b> everywhere and never mixed with the official datasets.</>}
        actions={<button className="btn-primary" onClick={() => { setAdding(true); setSelected(null); }} data-testid="add-dataset"><Plus size={15} />Add Custom Dataset</button>} />
      <div className="layout-aside">
        <aside className="stack">
          <Panel eyebrow="your datasets" title={`Custom datasets (${items.length})`} bodyClass="p-3">
            {!list.data && list.loading && <Skeleton className="h-40" />}
            {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
            {list.data && !items.length && <p className="p-2 text-[13.5px] text-muted">No custom datasets yet. Add one to get started.</p>}
            <ul className="space-y-1.5">{items.map((d) => (
              <li key={d.id}><button onClick={() => { setAdding(false); setSelected(d.id); }}
                className={`w-full rounded-xl border px-3 py-2.5 text-left transition-colors ${selected === d.id && !adding ? "border-violet/60 bg-violet/10" : "border-transparent hover:bg-raised/60"}`}>
                <div className="truncate font-semibold">{d.name}</div>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
                  <span className={`text-${STATUS_TONE[d.status]}`}>{STATUS_LABEL[d.status]}</span>·<span>{d.file_format.toUpperCase()}</span>·<span>{d.row_count === null ? "—" : `${fmtInt(d.row_count)} records`}</span>
                </div>
              </button></li>
            ))}</ul>
          </Panel>
          <Guide title="Supported files" defaultOpen={false}>
            <GuideItem term="Tables (CSV / TSV / TXT)">One row per variant. Columns such as <span className="data">chrom, pos, ref, alt</span>, <Term k="AC">AC</Term>, <Term k="AN">AN</Term>, <Term k="AF">AF</Term>, gene and clinical significance are detected automatically; population columns like <span className="data">AF_nfe</span> or <span className="data">afr_AC</span> are recognised too.</GuideItem>
            <GuideItem term="VCF / VCF.GZ">Multi-allelic sites are split into one record per ALT allele; INFO fields AC/AN/AF/CLNSIG/GENEINFO are read. The assembly is taken from <span className="data">##reference</span> or <span className="data">##contig</span> lines when present.</GuideItem>
            <GuideItem term="JSON">A list of variant objects, or an object containing such a list (e.g. <span className="data">{"{\"variants\": [...]}"}</span>).</GuideItem>
          </Guide>
        </aside>
        <section className="min-w-0">{view}</section>
      </div>
    </motion.div>
  );
}

import { motion } from "framer-motion";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ClassBadge, ErrorState, Guide, GuideItem, MatchBadge, NeedsAnalysis, PageHeader, Panel, ProvenanceBadge, Stars, stagger, Term } from "../../components/ui";
import { useProvenance } from "../../lib/provenance";
import { api } from "../../lib/api";
import { useAnalysis, useFetch } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtInt, MATCH_LABELS, POP_LABELS } from "../../lib/format";
import type { CoarseClass, VariantRow } from "../../lib/types";

const CLASSES: CoarseClass[] = ["P_LP", "VUS", "B_LB", "CONFLICTING", "OTHER", "NOT_IN_CLINVAR"];
export { default as VariantDrawer } from "../../components/VariantDrawer";
import VariantDrawer from "../../components/VariantDrawer";

const ROW_H = 58;      // fixed row height enables windowed rendering
const VIEW_PX = 620;   // ≈ 62vh scroll viewport
const OVERSCAN = 8;

/** Renders only the rows visible in the scroll container (+ overscan). */
export function useWindowedRows<T>(rows: T[], viewportPx: number) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  useEffect(() => { ref.current?.scrollTo({ top: 0 }); setScrollTop(0); }, [rows]);
  const start = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
  const end = Math.min(rows.length, Math.ceil((scrollTop + viewportPx) / ROW_H) + OVERSCAN);
  return { ref, onScroll: (e: React.UIEvent<HTMLDivElement>) => setScrollTop(e.currentTarget.scrollTop),
           slice: rows.slice(start, end), start, padTop: start * ROW_H, padBottom: (rows.length - end) * ROW_H };
}

type SortKey = "pos" | "af" | "ac" | "an" | "coarse_class" | "gold_stars" | "match_status";

export default function VariantExplorer() {
  const { analysisId, detail } = useAnalysis();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [classes, setClasses] = useState<CoarseClass[]>([]);
  const [match, setMatch] = useState("");
  const { mode: prov } = useProvenance();
  const [minAf, setMinAf] = useState("");
  const [maxAf, setMaxAf] = useState("");
  const [flagged, setFlagged] = useState(false);
  const [topPop, setTopPop] = useState("");
  const [sort, setSort] = useState<SortKey>("pos");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => { const t = setTimeout(() => setQ(search), 200); return () => clearTimeout(t); }, [search]);
  useEffect(() => setPage(1), [q, classes, match, prov, minAf, maxAf, flagged, pageSize, topPop]);

  const params = useMemo(() => ({
    analysis_id: analysisId ?? undefined, provenance: prov, search: q, coarse_class: classes, match_status: match ? [match] : undefined,
    min_af: minAf || undefined, max_af: maxAf || undefined, flagged_only: flagged || undefined, top_population: topPop || undefined,
  }), [analysisId, prov, q, classes, match, minAf, maxAf, flagged, topPop]);
  const res = useFetch(analysisId ? () => api.variants({ ...params, page, page_size: pageSize, sort, order }) : null, [params, page, pageSize, sort, order]);
  const items: VariantRow[] = useMemo(() => res.data?.items ?? [], [res.data]);
  const win = useWindowedRows(items, VIEW_PX);

  if (!analysisId) return <NeedsAnalysis />;
  const freq = detail?.results?.dataset?.frequency_source ?? "gnomAD";
  const toggleSort = (k: SortKey) => { if (sort === k) setOrder(order === "asc" ? "desc" : "asc"); else { setSort(k); setOrder(k === "af" ? "desc" : "asc"); } };
  const Th = ({ k, children }: { k?: SortKey; children: string }) => (
    <th className="table-head whitespace-nowrap">
      {k ? <button className="inline-flex items-center gap-1 hover:text-accent" onClick={() => toggleSort(k)} aria-label={`Sort by ${children}`}>{children}
        {sort === k && (order === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}</button> : children}
    </th>
  );

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-5">
      <PageHeader index="02" title="Variant Explorer"
        subtitle="Every gnomAD and ClinVar record for the active analysis – matched, unmatched and unmatchable – with server-side search, filtering, sorting and pagination."
        actions={<a className="btn-ghost" href={api.variantExportUrl(params)} download><Download size={15} />Export CSV</a>} />

      <Panel bodyClass="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[240px] flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
            <input className="input !pl-9" placeholder="Search key, rsID, HGVS, condition, ClinVar ID…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search variants" />
          </div>
          <span className={`chip px-2.5 py-1 ${prov === "REAL" ? "border-gold/50 text-gold" : prov === "SYNTHETIC" ? "border-pink/50 text-pink" : "border-accent/50 text-accent"}`} title="Change with the Real · Synthetic · Both switch at the top">showing: {prov === "BOTH" ? "real + synthetic" : prov.toLowerCase()}</span>
          <select className="input !w-auto" value={match} onChange={(e) => setMatch(e.target.value)} aria-label="Match status">
            <option value="">All match statuses</option>
            {Object.entries(MATCH_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input className="input !w-28" placeholder="min AF" value={minAf} onChange={(e) => setMinAf(e.target.value)} aria-label="Minimum allele frequency" />
          <input className="input !w-28" placeholder="max AF" value={maxAf} onChange={(e) => setMaxAf(e.target.value)} aria-label="Maximum allele frequency" />
          <select className="input !w-auto" value={topPop} onChange={(e) => setTopPop(e.target.value)} aria-label="Population with highest frequency">
            <option value="">Any top population</option>
            {Object.entries(POP_LABELS).filter(([k]) => k !== "oth").map(([k, l]) => <option key={k} value={k}>Top AF in {l}</option>)}
          </select>
          <label className="flex items-center gap-2 text-[13px] text-muted"><input type="checkbox" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} className="accent-[rgb(var(--accent))]" />flagged only</label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {CLASSES.map((c) => {
            const on = classes.includes(c);
            return (
              <button key={c} onClick={() => setClasses(on ? classes.filter((x) => x !== c) : [...classes, c])} aria-pressed={on}
                className={`chip transition-colors ${on ? `border-${CLASS_META[c].color}/60 bg-${CLASS_META[c].color}/15 text-ink` : "border-line text-muted hover:text-ink"}`}>
                <span className={`h-1.5 w-1.5 rounded-full bg-${CLASS_META[c].color}`} />{CLASS_META[c].short}
              </button>
            );
          })}
          {classes.length > 0 && <button className="text-xs text-faint underline" onClick={() => setClasses([])}>clear</button>}
        </div>
      </Panel>

      <Panel bodyClass="p-0">
        {res.error && <div className="p-4"><ErrorState message={res.error} onRetry={res.reload} /></div>}
        <div ref={win.ref} onScroll={win.onScroll} className="max-h-[62vh] overflow-auto scrollbar-thin" style={{ height: Math.min(VIEW_PX, (items.length + 1) * ROW_H + 12) }}>
          <table className={`w-full min-w-[1100px] ${prov === "BOTH" ? "prov-both" : ""}`}>
            <thead><tr>
              <Th>Variant</Th><Th k="pos">Position</Th><Th>REF › ALT</Th><Th k="af">AF</Th><Th k="ac">AC</Th><Th k="an">AN</Th>
              <Th k="coarse_class">Classification</Th><Th k="gold_stars">Review</Th><Th>Top population</Th><Th k="match_status">Match</Th><Th>Source</Th>
            </tr></thead>
            <tbody className={res.loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
              {win.padTop > 0 && <tr aria-hidden style={{ height: win.padTop }}><td colSpan={11} /></tr>}
              {win.slice.map((v) => (
                <tr key={v.id} onClick={() => setOpen(v.id)} onKeyDown={(e) => e.key === "Enter" && setOpen(v.id)} tabIndex={0} style={{ height: ROW_H }}
                  className={`cursor-pointer transition-colors hover:bg-raised/70 focus:bg-raised/70 focus:outline-none ${open === v.id ? "bg-accent/[0.07]" : ""} ${prov === "BOTH" ? (v.provenance === "SYNTHETIC" ? "prov-synthetic" : "prov-real") : ""}`}>
                  <td className="table-cell max-w-[240px]"><div className={`truncate font-mono text-[13px] ${v.provenance === "SYNTHETIC" && prov !== "BOTH" ? "syn-id inline-block max-w-full" : ""}`}>{v.variant_key}</div><div className="truncate text-[12px] text-faint">{v.hgvsp ?? v.hgvsc ?? v.name ?? v.rsid ?? ""}</div></td>
                  <td className="table-cell data text-xs">{v.chrom ? `${v.chrom}:${fmtInt(v.pos)}` : "—"}</td>
                  <td className="table-cell max-w-[120px] truncate font-mono text-xs" title={`${v.ref} > ${v.alt}`}>{v.ref || "–"} › {v.alt || "–"}</td>
                  <td className="table-cell data text-xs">{fmtAF(v.af)}</td>
                  <td className="table-cell data text-xs">{fmtInt(v.ac)}</td>
                  <td className="table-cell data text-xs">{fmtInt(v.an)}</td>
                  <td className="table-cell"><ClassBadge cls={v.coarse_class} label={v.clinical_significance} /></td>
                  <td className="table-cell"><Stars n={v.gold_stars} /></td>
                  <td className="table-cell text-xs text-muted">{v.popmax_population ? `${v.popmax_population} · ${fmtAF(v.popmax_af)}` : "—"}</td>
                  <td className="table-cell"><MatchBadge s={v.match_status} /></td>
                  <td className="table-cell"><ProvenanceBadge p={v.provenance} source={v.provenance === "REAL" ? freq : null} /></td>
                </tr>
              ))}
              {win.padBottom > 0 && <tr aria-hidden style={{ height: win.padBottom }}><td colSpan={11} /></tr>}
              {res.data && items.length === 0 && <tr><td colSpan={11} className="p-10 text-center text-sm text-muted">No records match these filters.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm">
          <span className="text-muted">{res.data ? `${fmtInt(res.data.total)} records · page ${res.data.page} of ${Math.max(1, res.data.pages ?? 1)}` : "…"}</span>
          <div className="flex items-center gap-2">
            <select className="input !w-auto !py-1 text-xs" value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} aria-label="Rows per page">
              {[25, 50, 100, 250, 500].map((n) => <option key={n} value={n}>{n} / page</option>)}
            </select>
            <button className="btn-ghost !px-2 !py-1" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={15} /></button>
            <button className="btn-ghost !px-2 !py-1" disabled={!res.data || page >= (res.data.pages ?? 1)} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={15} /></button>
          </div>
        </div>
      </Panel>
      <Guide title="How to read this table">
        <GuideItem term={<><Term k="AF">Allele frequency (AF)</Term></>}>How often the alternate allele occurs among sampled chromosomes. It is calculated as <b>AF = AC ÷ AN</b>. A value of <b>1.0e-5</b> means about <b>1 in 100,000</b> chromosomes.</GuideItem>
        <GuideItem term={<><Term k="AC">AC</Term> and <Term k="AN">AN</Term></>}><b>AC</b> (allele count) is how many sampled chromosomes carry the allele; <b>AN</b> (allele number) is how many chromosomes were confidently genotyped. Example: AC = 3, AN = 300,000 → AF = 0.00001.</GuideItem>
        <GuideItem term="Missing values (—)">A dash means the value is <b>not reported</b>. A missing AN or AF is <b>not</b> the same as zero – the site may be uncovered, filtered, or absent from the selected dataset.</GuideItem>
        <GuideItem term="Match status">How a frequency record was linked to ClinVar: <b>Exact</b> (identical chromosome-position-alleles), <b>Normalized</b> (same allele written differently, e.g. indel anchors), <b>Ambiguous</b>, or unmatched (<b>gnomAD/ClinVar only</b>, <b>Unmatchable</b>). Records are never joined by gene name.</GuideItem>
        <GuideItem term={<>Review stars (<Term k="review stars">★</Term>)</>}>How thoroughly a ClinVar classification was reviewed: 0 = no assertion criteria … 4 = practice guideline. More stars = more confidence in the label, not in the biology.</GuideItem>
        <GuideItem term="Real, synthetic and both">Use the <b>Real · Synthetic · Both</b> switch at the top. In <b>Both</b> mode, real records are outlined in <b className="text-gold">gold</b> and synthetic ones in <b className="text-pink">pink</b>. Synthetic records are simulated and are never real observations.</GuideItem>
      </Guide>
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

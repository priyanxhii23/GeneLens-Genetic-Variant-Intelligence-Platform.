import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ClassBadge, Explain, NeedsAnalysis, PageHeader, Panel, stagger } from "../../components/ui";
import { VariantDrawer } from "./VariantExplorer";
import { useAnalysis } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtInt, MAIN_CLASSES, pct, POP_LABELS, token } from "../../lib/format";

export default function PopulationObservatory() {
  const { analysisId, detail } = useAnalysis();
  const pops = detail?.results?.populations;
  const [selected, setSelected] = useState<string[] | null>(null);
  const [classFilter, setClassFilter] = useState<string>("ALL");
  const [open, setOpen] = useState<number | null>(null);
  const active = selected ?? pops?.populations ?? [];

  const rows = useMemo(() => (pops?.matrix ?? []).filter((r) => classFilter === "ALL" || r.coarse_class === classFilter), [pops, classFilter]);

  const heat = useMemo(() => {
    if (!rows.length) return [];
    const z = rows.map((r) => active.map((p) => { const c = r.populations[p]; return c && c.af !== null && c.af > 0 ? Math.log10(c.af) : null; }));
    const text = rows.map((r) => active.map((p) => { const c = r.populations[p]; return c ? `AF ${fmtAF(c.af)}<br>AC ${fmtInt(c.ac)} / AN ${fmtInt(c.an)}` : "no data (AN not reported)"; }));
    const labels = rows.map((r) => (r.hgvsp ?? r.hgvsc ?? r.variant_key).slice(0, 28));
    return [
      { type: "heatmap" as const, z, x: active, y: labels, text: text as unknown as string[], hovertemplate: "%{y} · %{x}<br>%{text}<extra></extra>",
        colorscale: [[0, token("accent", 0.06)], [0.5, token("accent", 0.5)], [1, token("accent", 1)]] as [number, string][],
        zmin: -6, zmax: 0, xgap: 2, ygap: 2, hoverongaps: true,
        colorbar: { title: { text: "log10 AF", side: "right" as const }, thickness: 10, outlinewidth: 0, tickfont: { color: token("muted") } } },
    ];
  }, [rows, active]);

  const groupsBar = useMemo(() => {
    if (!pops) return [];
    const g = pops.groups.filter((x) => active.includes(x.id));
    return MAIN_CLASSES.map((c) => ({
      type: "bar" as const, name: CLASS_META[c].short, x: g.map((x) => x.id), y: g.map((x) => x.by_class[c]?.observed ?? 0),
      marker: { color: token(CLASS_META[c].color), line: { color: token("surface"), width: 2 } },
      hovertemplate: "%{x}: %{y} variants with AC>0<extra>%{fullData.name}</extra>",
    }));
  }, [pops, active]);

  if (!analysisId) return <NeedsAnalysis />;
  if (!pops) return <Panel><p className="text-sm text-muted">Results not available yet.</p></Panel>;
  const popmax = Object.entries(pops.pathogenic_popmax_distribution).sort((a, b) => b[1] - a[1]);

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="04" title="Population Frequency Observatory"
        subtitle={`Allele frequencies across gnomAD genetic-ancestry groups for ${fmtInt(pops.n_variants)} gnomAD variants. These are aggregate reference-sample frequencies – they cannot be used to infer anyone's ancestry or disease risk.`} />

      <Panel bodyClass="p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="eyebrow mr-2">populations</span>
          {pops.populations.map((p) => {
            const on = active.includes(p);
            return <button key={p} aria-pressed={on} title={POP_LABELS[p]} onClick={() => setSelected(on ? active.filter((x) => x !== p) : [...active, p])}
              className={`chip ${on ? "border-accent/50 bg-accent/10 text-ink" : "border-line text-faint"}`}>{p}</button>;
          })}
          <button className="text-xs text-faint underline" onClick={() => setSelected(null)}>all</button>
          <span className="eyebrow ml-auto mr-2">class</span>
          <select className="input !w-auto !py-1 text-xs" value={classFilter} onChange={(e) => setClassFilter(e.target.value)} aria-label="Classification filter">
            <option value="ALL">All classes</option>
            {[...MAIN_CLASSES, "NOT_IN_CLINVAR"].map((c) => <option key={c} value={c}>{CLASS_META[c as keyof typeof CLASS_META].short}</option>)}
          </select>
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Panel eyebrow={`top ${rows.length} variants by overall AF`} title="Population frequency matrix">
          <Plot data={heat} height={Math.max(320, rows.length * 18 + 80)} layout={{ margin: { l: 190, r: 20, t: 8, b: 40 }, yaxis: { autorange: "reversed", tickfont: { size: 10, family: "JetBrains Mono" } }, xaxis: { side: "top" } }} />
          <p className="mt-2 text-xs text-faint">Empty (background) cells = population had no allele number at this site or AC = 0. Hover a cell for AC/AN.</p>
        </Panel>
        <div className="space-y-6">
          <Panel eyebrow="by class" title="Variants observed per group">
            <Plot data={groupsBar} height={280} layout={{ barmode: "stack", bargap: 0.3, yaxis: { title: { text: "variants (AC>0)" } } }} />
          </Panel>
          <Panel eyebrow="P/LP variants" title="Population with highest AF">
            {popmax.length === 0 ? <p className="text-sm text-muted">No P/LP variants observed in gnomAD.</p> : (
              <ul className="space-y-2">{popmax.map(([p, n]) => (
                <li key={p} className="text-sm"><div className="flex justify-between"><span>{POP_LABELS[p] ?? p}</span><span className="data text-muted">{n}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-raised"><div className="h-full rounded-full bg-plp" style={{ width: `${(n / popmax[0][1]) * 100}%` }} /></div></li>))}</ul>)}
            <p className="mt-3 text-xs text-faint">grpmax excludes bottlenecked/small groups (ami, asj, fin, mid, remaining), as in gnomAD. Larger samples (e.g. nfe) detect more rare variants simply because more chromosomes were sequenced.</p>
          </Panel>
        </div>
      </div>

      <Panel eyebrow="interactive comparison" title="Group summary">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full min-w-[720px]">
            <thead><tr>{["Group", "Label", "Variants AC>0", "Total AC", "Median AN", "Missing AN", "grpmax eligible"].map((h) => <th key={h} className="table-head">{h}</th>)}</tr></thead>
            <tbody>{pops.groups.filter((g) => active.includes(g.id)).map((g) => (
              <tr key={g.id}><td className="table-cell font-mono text-xs">{g.id}</td><td className="table-cell text-sm">{g.label}</td>
                <td className="table-cell data">{fmtInt(g.variants_observed)}</td><td className="table-cell data">{fmtInt(g.total_ac)}</td>
                <td className="table-cell data">{fmtInt(Math.round(g.median_an))}</td>
                <td className="table-cell"><span className={`chip ${g.missing ? "border-warn/40 text-warn" : "border-line text-muted"}`}>{fmtInt(g.missing)} · {pct(g.missing_fraction)}</span></td>
                <td className="table-cell text-xs text-muted">{g.grpmax_eligible ? "yes" : "no"}</td></tr>))}</tbody>
          </table>
        </div>
      </Panel>

      <Panel eyebrow="drill-down" title="Most frequent variants">
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full min-w-[820px]">
            <thead><tr><th className="table-head">Variant</th><th className="table-head">Class</th><th className="table-head">AF</th>{active.map((p) => <th key={p} className="table-head">{p}</th>)}</tr></thead>
            <tbody>{rows.slice(0, 20).map((r) => (
              <tr key={r.variant_key} className="cursor-pointer hover:bg-raised/60" onClick={() => setOpen(r.id)}>
                <td className="table-cell max-w-[200px] truncate font-mono text-xs">{r.hgvsp ?? r.variant_key}</td>
                <td className="table-cell"><ClassBadge cls={r.coarse_class} /></td>
                <td className="table-cell data text-xs">{fmtAF(r.af)}</td>
                {active.map((p) => <td key={p} className="table-cell data text-xs">{r.populations[p] ? fmtAF(r.populations[p]!.af) : <span className="text-warn" title="no allele number reported">n/a</span>}</td>)}
              </tr>))}</tbody>
          </table>
        </div>
      </Panel>
      <Explain>{pops.notes.map((n) => <p key={n}>{n}</p>)}</Explain>
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

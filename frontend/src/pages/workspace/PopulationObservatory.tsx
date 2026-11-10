import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import Plot from "../../components/Plot";
import { ClassBadge, ErrorState, Guide, GuideItem, HelixLoader, Insight, NeedsAnalysis, PageHeader, Panel, ProvenanceBadge, stagger, Tabs, Term } from "../../components/ui";
import { api } from "../../lib/api";
import { useFetch } from "../../lib/analysis";
import { useProvenance } from "../../lib/provenance";
import { VariantDrawer } from "./VariantExplorer";
import { useAnalysis } from "../../lib/analysis";
import { CLASS_META, fmtAF, fmtInt, MAIN_CLASSES, pct, POP_LABELS, token } from "../../lib/format";

export default function PopulationObservatory() {
  const { analysisId, detail } = useAnalysis();
  const { mode } = useProvenance();
  const [grp, setGrp] = useState<"REAL" | "SYNTHETIC">("REAL");
  const res = useFetch(analysisId && detail?.results ? () => api.populationsFor(analysisId, mode) : null, [analysisId, mode, detail?.results]);
  const which = mode === "BOTH" ? grp : (mode as "REAL" | "SYNTHETIC");
  const pops = res.data?.groups[which] ?? undefined;
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
  if (res.loading && !res.data) return <HelixLoader label="Loading population data" />;
  if (res.error) return <ErrorState message={res.error} onRetry={res.reload} />;
  if (!pops) return <Insight tone="pink" label="Nothing to show" reason={which === "SYNTHETIC" ? "This analysis has no linked synthetic records yet." : "Population data is not available for this analysis."}><p>{which === "SYNTHETIC" ? "Generate a synthetic dataset in the Synthetic Lab first." : "The selected dataset may not report population-level counts (for example dbSNP or the ClinVar-only dataset)."}</p></Insight>;
  const top = [...pops.groups].sort((a, b) => b.variants_observed - a.variants_observed)[0];
  const popmax = Object.entries(pops.pathogenic_popmax_distribution).sort((a, b) => b[1] - a[1]);

  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
      <PageHeader index="04" title="Population Frequency Observatory"
        subtitle={`Allele frequencies across genetic-ancestry groups for ${fmtInt(pops.n_variants)} ${which === "SYNTHETIC" ? "synthetic" : (detail?.results?.dataset?.frequency_source ?? "gnomAD")} records. These are aggregate reference-sample frequencies – they cannot be used to infer anyone's ancestry or disease risk.`}
        actions={mode === "BOTH" ? <Tabs value={grp} onChange={setGrp} options={[{ value: "REAL", label: <><span className="h-2 w-2 rounded-full bg-gold" />Real</> }, { value: "SYNTHETIC", label: <><span className="h-2 w-2 rounded-full bg-pink" />Synthetic</> }]} /> : <ProvenanceBadge p={which} />} />
      {pops.n_variants === 0 ? (
        <Insight label="No population data" reason="The selected dataset does not report population-level allele counts.">
          <p>Population breakdowns are available for <b>gnomAD</b> and <b>1000 Genomes</b> datasets. dbSNP and ClinVar-only analyses have no per-population counts.</p>
        </Insight>
      ) : top && (
        <Insight label="Main observation" reason={`The ${top.label} group contributes the most observed variants (${fmtInt(top.variants_observed)}), which mainly reflects how many people from that group were sequenced.`}>
          <p>Larger groups detect more rare variants simply because more chromosomes were examined (median <Term k="AN">allele number</Term> {top.median_an === null ? "not reported" : fmtInt(Math.round(top.median_an))} here). Compare frequencies, not variant counts, when asking whether an allele is more common in one group. Missing values are shown explicitly and are <b>not</b> zero.</p>
        </Insight>
      )}

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

      <div className="layout-split">
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
                <td className="table-cell data">{g.median_an === null ? "—" : fmtInt(Math.round(g.median_an))}</td>
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
      <Guide>
        <GuideItem term="Population groups">These represent <b>genetic ancestry groups</b> used in the reference dataset (for example <b>afr</b> = African / African American, <b>nfe</b> = non-Finnish European). They describe groups of sampled individuals, <b>not</b> an individual's identity.</GuideItem>
        <GuideItem term={<Term k="AF">Allele frequency (AF)</Term>}>How frequently an alternate allele occurs in a sampled group. It is calculated as <b>AF = AC ÷ AN</b> – the number of chromosomes carrying the allele divided by the number examined. Example: AC = 5 out of AN = 50,000 gives AF = 0.0001 (1 in 10,000).</GuideItem>
        <GuideItem term={<><Term k="AC">AC</Term> and <Term k="AN">AN</Term></>}><b>AC</b> (allele count) counts carriers' chromosomes; <b>AN</b> (allele number) counts all chromosomes successfully genotyped – about two per person. An extremely small AF such as <b>1e-6</b> usually means the allele was seen once or twice among a million chromosomes.</GuideItem>
        <GuideItem term="Missing (n/a)">If a population has no reported allele number for a variant, its frequency is <b>unavailable</b>. This does <b>NOT</b> mean the allele frequency is zero – the site may not have been covered in that group.</GuideItem>
        <GuideItem term={<Term k="grpmax">grpmax</Term>}>The highest frequency among large, non-bottlenecked groups. Small or founder groups (Amish, Ashkenazi Jewish, Finnish, Middle Eastern, "remaining") are excluded because chance and population history can inflate their frequencies.</GuideItem>
        <GuideItem term="Important">Population-level genetic frequencies <b>cannot</b> be used to determine an individual's ancestry or predict their disease risk. They describe reference samples only.</GuideItem>
      </Guide>
      <VariantDrawer id={open} onClose={() => setOpen(null)} />
    </motion.div>
  );
}

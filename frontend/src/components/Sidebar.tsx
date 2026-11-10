/**
 * Navigation styled as a chromosome ideogram: each module is a band on the
 * rail and the active band carries an animated "locus marker". Collapsible
 * to an icon rail on desktop; off-canvas on small screens.
 */
import { motion } from "framer-motion";
import {
  Activity, BarChart3, ChevronsLeft, ChevronsRight, Database, FileText, FlaskConical, Gauge, GitCompareArrows, Globe2,
  Layers, Radar, ShieldAlert, X,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useAnalysis } from "../lib/analysis";
import { LogoMark } from "./ui";

export const NAV = [
  { to: "/workspace", label: "Command Center", band: "p13", icon: Gauge, end: true },
  { to: "/workspace/variants", label: "Variant Explorer", band: "p12", icon: Layers },
  { to: "/workspace/pathogenicity", label: "Pathogenicity Lab", band: "p11", icon: ShieldAlert },
  { to: "/workspace/populations", label: "Population Observatory", band: "q11", icon: Globe2 },
  { to: "/workspace/constraint", label: "Constraint Observatory", band: "q12", icon: Activity },
  { to: "/workspace/anomalies", label: "Anomaly Engine", band: "q13", icon: Radar },
  { to: "/workspace/statistics", label: "Statistics Studio", band: "q21", icon: BarChart3 },
  { to: "/workspace/synthetic", label: "Synthetic Lab", band: "q22", icon: FlaskConical },
  { to: "/workspace/compare", label: "Gene Comparison Lab", band: "q23", icon: GitCompareArrows },
  { to: "/workspace/reports", label: "Report Generator", band: "q24", icon: FileText },
  { to: "/workspace/sources", label: "Source Manager", band: "q25", icon: Database },
];

export default function Sidebar({ open, onClose, collapsed, onToggle }: {
  open: boolean; onClose: () => void; collapsed: boolean; onToggle: () => void;
}) {
  const { pathname } = useLocation();
  const { detail } = useAnalysis();
  const a = detail?.analysis;
  const w = collapsed ? "lg:w-[84px]" : "lg:w-[284px]";
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-bg/70 backdrop-blur-sm lg:hidden" onClick={onClose} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-[284px] flex-col border-r border-line bg-surface/95 backdrop-blur-xl transition-[transform,width] duration-300 ${w} lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className={`flex items-center justify-between pb-4 pt-5 ${collapsed ? "lg:justify-center lg:px-2" : "px-5"} px-5`}>
          <NavLink to="/" className="group flex items-center gap-3.5" title="GeneLens home">
            <LogoMark size={48} />
            <span className={collapsed ? "lg:hidden" : ""}>
              <span className="block font-display text-[27px] leading-none tracking-tight transition-colors group-hover:text-accent">GeneLens</span>
              <span className="eyebrow mt-1 block !text-[9.5px] !tracking-[0.22em]">variant intelligence</span>
            </span>
          </NavLink>
          <button className="text-muted lg:hidden" onClick={onClose} aria-label="Close navigation"><X size={18} /></button>
        </div>

        <div className={`mx-4 mb-4 rounded-xl border border-line bg-raised/60 p-3 ${collapsed ? "lg:hidden" : ""}`}>
          <div className="eyebrow mb-1">Active analysis</div>
          {a ? (
            <div>
              <div className="flex items-baseline justify-between"><span className="font-display text-[22px]">{a.gene_symbol}</span><span className="data text-[10.5px] text-faint">{a.id}</span></div>
              <div className="data truncate text-[11.5px] text-muted">{detail?.results?.dataset?.name ?? a.dataset} · {a.reference_genome}</div>
            </div>
          ) : <div className="text-xs text-muted">None selected</div>}
        </div>

        <nav className="relative flex-1 overflow-y-auto px-3 scrollbar-thin" aria-label="Research modules">
          <div className={`absolute bottom-3 left-[27px] top-1 w-[6px] rounded-full bg-gradient-to-b from-line via-line/60 to-line ${collapsed ? "lg:hidden" : ""}`} aria-hidden />
          <ul className="relative space-y-0.5">
            {NAV.map((n) => {
              const active = n.end ? pathname === n.to : pathname.startsWith(n.to);
              const Icon = n.icon;
              return (
                <li key={n.to}>
                  <NavLink to={n.to} end={n.end} onClick={onClose} title={n.label}
                    className={`group relative flex items-center gap-3 rounded-xl py-2.5 text-[14.5px] font-medium transition-colors ${collapsed ? "pl-9 pr-3 lg:justify-center lg:px-0" : "pl-9 pr-3"} ${active ? "text-ink" : "text-muted hover:text-ink"}`}>
                    {active && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl border border-accent/30 bg-accent/[0.08] shadow-glow-sm" transition={{ type: "spring", bounce: 0.18, duration: 0.5 }} />}
                    <span className={`absolute left-[11px] h-[3px] w-[14px] rounded-full transition-all ${collapsed ? "lg:hidden" : ""} ${active ? "bg-accent shadow-glow" : "bg-faint/40 group-hover:bg-accent/60"}`} aria-hidden />
                    <Icon size={17} className={`relative transition-transform group-hover:scale-110 ${active ? "text-accent" : ""}`} />
                    <span className={`relative flex-1 ${collapsed ? "lg:hidden" : ""}`}>{n.label}</span>
                    <span className={`data relative text-[9.5px] text-faint ${collapsed ? "lg:hidden" : ""}`}>{n.band}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
        <button onClick={onToggle} className="mx-3 mb-2 hidden items-center justify-center gap-2 rounded-xl py-2 text-[12.5px] text-faint transition-colors hover:bg-raised hover:text-ink lg:flex" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <ChevronsRight size={16} /> : <><ChevronsLeft size={16} />Collapse</>}
        </button>
        <div className={`border-t border-line px-5 py-3 text-[11px] leading-snug text-faint ${collapsed ? "lg:hidden" : ""}`}>
          Data: gnomAD · ClinVar · Ensembl · dbSNP · IGSR · UCSC. Research use only – not for clinical decisions.
        </div>
      </aside>
    </>
  );
}

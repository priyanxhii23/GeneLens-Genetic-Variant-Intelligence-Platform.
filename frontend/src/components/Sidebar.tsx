/**
 * Navigation styled as a chromosome ideogram: each module is a band on the
 * rail and the active band carries an animated "locus marker".
 */
import { motion } from "framer-motion";
import {
  Activity, BarChart3, Dna, FileText, FlaskConical, Gauge, Globe2, History, Layers, Radar, ShieldAlert, X,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { useAnalysis } from "../lib/analysis";

export const NAV = [
  { to: "/workspace", label: "Command Center", band: "p13", icon: Gauge, end: true },
  { to: "/workspace/variants", label: "Variant Explorer", band: "p12", icon: Layers },
  { to: "/workspace/pathogenicity", label: "Pathogenicity Lab", band: "p11", icon: ShieldAlert },
  { to: "/workspace/populations", label: "Population Observatory", band: "q11", icon: Globe2 },
  { to: "/workspace/constraint", label: "Constraint Observatory", band: "q12", icon: Activity },
  { to: "/workspace/anomalies", label: "Anomaly Engine", band: "q13", icon: Radar },
  { to: "/workspace/statistics", label: "Statistics Studio", band: "q21", icon: BarChart3 },
  { to: "/workspace/synthetic", label: "Synthetic Lab", band: "q22", icon: FlaskConical },
  { to: "/workspace/reports", label: "Report Generator", band: "q23", icon: FileText },
  { to: "/workspace/history", label: "History & Provenance", band: "q24", icon: History },
];

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { pathname } = useLocation();
  const { detail } = useAnalysis();
  const a = detail?.analysis;
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-bg/70 backdrop-blur-sm lg:hidden" onClick={onClose} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col border-r border-line bg-surface/95 backdrop-blur-xl transition-transform duration-300 lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between px-5 pb-4 pt-5">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl border border-accent/30 bg-accent/10 text-accent shadow-glow"><Dna size={18} /></span>
            <span>
              <span className="block font-display text-lg leading-none">GeneLens</span>
              <span className="eyebrow !text-[9px]">variant intelligence</span>
            </span>
          </NavLink>
          <button className="text-muted lg:hidden" onClick={onClose} aria-label="Close navigation"><X size={18} /></button>
        </div>

        <div className="mx-5 mb-4 rounded-xl border border-line bg-raised/60 p-3">
          <div className="eyebrow mb-1">Active analysis</div>
          {a ? (
            <div>
              <div className="flex items-baseline justify-between"><span className="font-display text-xl">{a.gene_symbol}</span><span className="data text-[10px] text-faint">{a.id}</span></div>
              <div className="data text-[11px] text-muted">{a.dataset} · {a.reference_genome}</div>
            </div>
          ) : <div className="text-xs text-muted">None selected</div>}
        </div>

        <nav className="relative flex-1 overflow-y-auto px-3 scrollbar-thin" aria-label="Research modules">
          {/* the chromosome rail */}
          <div className="absolute bottom-3 left-[27px] top-1 w-[6px] rounded-full bg-gradient-to-b from-line via-line/60 to-line" aria-hidden />
          <div className="absolute left-[25px] top-[calc(30%)] h-3 w-[10px] rounded-full bg-raised ring-1 ring-line" aria-hidden title="centromere" />
          <ul className="relative space-y-0.5">
            {NAV.map((n) => {
              const active = n.end ? pathname === n.to : pathname.startsWith(n.to);
              const Icon = n.icon;
              return (
                <li key={n.to}>
                  <NavLink to={n.to} end={n.end} onClick={onClose}
                    className={`group relative flex items-center gap-3 rounded-xl py-2 pl-9 pr-3 text-sm transition-colors ${active ? "text-ink" : "text-muted hover:text-ink"}`}>
                    {active && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl border border-accent/25 bg-accent/[0.07]" transition={{ type: "spring", bounce: 0.18, duration: 0.5 }} />}
                    <span className={`absolute left-[11px] h-[3px] w-[14px] rounded-full transition-all ${active ? "bg-accent shadow-glow" : "bg-faint/40 group-hover:bg-accent/60"}`} aria-hidden />
                    <Icon size={15} className={`relative ${active ? "text-accent" : ""}`} />
                    <span className="relative flex-1">{n.label}</span>
                    <span className="data relative text-[9px] text-faint">{n.band}</span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="border-t border-line px-5 py-3 text-[10.5px] leading-snug text-faint">
          Data: gnomAD · ClinVar (NCBI). Research use only – not for clinical decisions.
        </div>
      </aside>
    </>
  );
}

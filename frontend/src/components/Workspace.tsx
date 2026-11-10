import { AnimatePresence, motion } from "framer-motion";
import { Menu, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useAnalysis } from "../lib/analysis";
import { useTheme } from "../lib/theme";
import DnaHelix from "./DnaHelix";
import ProvenanceSwitch from "./ProvenanceSwitch";
import Sidebar, { NAV } from "./Sidebar";
import { HelixLoader } from "./ui";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button onClick={toggle} className="btn-ghost !px-2.5" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span key={theme} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.25 }}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

const COLLAPSE_KEY = "genelens-sidebar-collapsed";

export default function Workspace() {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0"); } catch { /* */ } }, [collapsed]);
  const { pathname } = useLocation();
  const { loading } = useAnalysis();
  const current = NAV.find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
  return (
    <div className="min-h-screen lab-grid">
      <div className="pointer-events-none fixed right-0 top-0 h-screen w-[180px] opacity-[0.18]" aria-hidden><DnaHelix orientation="vertical" particles={14} /></div>
      <Sidebar open={open} onClose={() => setOpen(false)} collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div className={`relative transition-[padding] duration-300 ${collapsed ? "lg:pl-[84px]" : "lg:pl-[284px]"}`}>
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-line/70 bg-bg/75 px-4 py-3 backdrop-blur-xl md:px-8">
          <button className="btn-ghost !px-2.5 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu size={16} /></button>
          <div className="eyebrow hidden sm:block">GeneLens / <span className="text-ink">{current?.label ?? "Workspace"}</span></div>
          <div className="flex-1" />
          {loading && <HelixLoader label="Loading analysis" />}
          <ProvenanceSwitch />
          <ThemeToggle />
        </header>
        <AnimatePresence mode="wait">
          <motion.main key={pathname} initial={{ opacity: 0, y: 10, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }} className="relative mx-auto max-w-[1440px] px-4 py-8 md:px-8">
            <Outlet />
          </motion.main>
        </AnimatePresence>
      </div>
    </div>
  );
}

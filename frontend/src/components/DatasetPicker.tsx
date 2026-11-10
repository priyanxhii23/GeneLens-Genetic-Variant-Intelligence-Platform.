/** Dataset selector: all ten registry datasets with provider, assembly, release, type and live status. */
import { motion } from "framer-motion";
import AnchoredPortal from "./AnchoredPortal";
import { Check, ChevronDown, CircleDot, Database } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DatasetEntry } from "../lib/types";

const TYPE_LABEL: Record<string, string> = {
  population_frequency: "Population frequency", clinical_annotation: "Clinical annotation", variant_catalogue: "Variant catalogue",
};

export default function DatasetPicker({ datasets, value, onChange, loading }: {
  datasets: DatasetEntry[] | null; value: string; onChange: (id: string) => void; loading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const list = datasets ?? [];
  const sel = list.find((d) => d.id === value);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!ref.current?.contains(t) && !panel.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  useEffect(() => { if (open) setHi(Math.max(0, list.findIndex((d) => d.id === value))); }, [open]); // eslint-disable-line

  const choose = (d: DatasetEntry) => { if (d.status === "available") { onChange(d.id); setOpen(false); } };
  const onKey = (e: React.KeyboardEvent) => {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ")) { e.preventDefault(); setOpen(true); return; }
    if (!open) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(list.length - 1, h + 1)); }
    if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    if (e.key === "Enter") { e.preventDefault(); if (list[hi]) choose(list[hi]); }
    if (e.key === "Escape") setOpen(false);
  };
  const groups = ["population_frequency", "clinical_annotation", "variant_catalogue"];

  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen(!open)} onKeyDown={onKey} aria-haspopup="listbox" aria-expanded={open}
        className={`input flex items-center gap-2 text-left ${open ? "border-accent/60 shadow-glow-sm" : ""}`}>
        <Database size={15} className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-semibold">{sel?.name ?? (loading ? "Checking datasets…" : value)}</span>
          {sel && <span className="block truncate text-[12px] text-faint">{sel.provider} · {sel.assembly} · {TYPE_LABEL[sel.data_type]}</span>}
        </span>
        <ChevronDown size={16} className={`shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <AnchoredPortal anchor={ref} open={open} minWidth={Math.min(560, typeof window !== "undefined" ? window.innerWidth - 32 : 560)} maxHeight={520} onPanel={(el) => { panel.current = el; }}>
          <motion.ul role="listbox" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
            className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-line bg-surface p-1.5 shadow-lift scrollbar-thin">
            {groups.map((g) => {
              const items = list.filter((d) => d.data_type === g);
              if (!items.length) return null;
              return (
                <li key={g} role="presentation">
                  <div className="eyebrow px-3 pb-1 pt-2">{TYPE_LABEL[g]}</div>
                  <ul>
                    {items.map((d) => {
                      const i = list.indexOf(d);
                      const ok = d.status === "available";
                      return (
                        <li key={d.id} role="option" aria-selected={d.id === value} aria-disabled={!ok}
                          onMouseEnter={() => setHi(i)} onClick={() => choose(d)}
                          className={`flex cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 ${hi === i ? "bg-raised" : ""} ${ok ? "" : "cursor-not-allowed opacity-60"}`}>
                          <span className="mt-1 w-4 shrink-0">{d.id === value && <Check size={15} className="text-accent" />}</span>
                          <span className="min-w-0 flex-1">
                            <span className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold">{d.name}</span>
                              <span className="chip border-line font-mono text-[11px] text-muted">{d.assembly}</span>
                            </span>
                            <span className="block text-[12.5px] text-muted">{d.provider} · {d.release}</span>
                          </span>
                          <span className={`chip shrink-0 ${ok ? "border-good/40 text-good" : "border-bad/40 text-bad"}`} title={d.status_detail}>
                            <CircleDot size={10} />{ok ? "available" : "unavailable"}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
          </motion.ul>
      </AnchoredPortal>
      {sel && (
        <motion.p key={sel.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-2 text-[13.5px] leading-relaxed text-muted">
          {sel.description} <span className="text-faint">({sel.status_detail})</span>
        </motion.p>
      )}
    </div>
  );
}

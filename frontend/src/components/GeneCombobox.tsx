/**
 * Gene search combobox.
 * - Suggestions on focus (8 starting genes + recent searches), before typing.
 * - Two-phase search: the local catalogue answers instantly, live gnomAD
 *   results are merged in a moment later.
 * - Rendered in a portal (AnchoredPortal) so it is never hidden behind cards.
 * - Keyboard: ↑/↓ to move, Enter to select, Escape to close; click outside closes.
 */
import { motion } from "framer-motion";
import { Clock, Search, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import type { GeneSuggestion } from "../lib/types";
import AnchoredPortal from "./AnchoredPortal";

const RECENT_KEY = "genelens-recent-genes";
const readRecent = (): string[] => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; } };
export function rememberGene(symbol: string) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify([symbol, ...readRecent().filter((g) => g !== symbol)].slice(0, 6))); } catch { /* storage blocked */ }
}

export default function GeneCombobox({ value, onChange, onSubmit, dataset }: {
  value: string; onChange: (v: string) => void; onSubmit?: (v: string) => void; dataset: string;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<GeneSuggestion[]>([]);
  const [hi, setHi] = useState(0);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState<string | null>(null);
  const [recent, setRecent] = useState<string[]>(readRecent);
  const wrap = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const seq = useRef(0);

  // Phase 1: local catalogue (instant). Phase 2: live gnomAD search, merged in.
  useEffect(() => {
    const id = ++seq.current;
    const q = value.trim();
    setLoading(true);
    api.suggestGenes(q, false).then((r) => { if (id === seq.current) { setItems(r.results); setHi(0); } }).catch(() => {});
    if (!q) { setLoading(false); setLive(null); return; }
    const t = window.setTimeout(() => {
      api.suggestGenes(q, true).then((r) => {
        if (id !== seq.current) return;
        setItems((cur) => [...cur, ...r.results.filter((x) => !cur.some((c) => c.symbol === x.symbol))].slice(0, 12));
        setLive(r.live_search);
      }).catch(() => {}).finally(() => { if (id === seq.current) setLoading(false); });
    }, 350);
    return () => window.clearTimeout(t);
  }, [value]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!wrap.current?.contains(t) && !panel.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const recentItems = useMemo(() => (value ? [] : recent.filter((r) => !items.some((i) => i.symbol === r))), [recent, items, value]);
  const options: { symbol: string; s?: GeneSuggestion; recent?: boolean }[] = [
    ...recentItems.map((r) => ({ symbol: r, recent: true })), ...items.map((s) => ({ symbol: s.symbol, s })),
  ];
  useEffect(() => { listRef.current?.querySelector(`[data-index="${hi}"]`)?.scrollIntoView({ block: "nearest" }); }, [hi]);

  const pick = (sym: string) => { onChange(sym); rememberGene(sym); setRecent(readRecent()); setOpen(false); };
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi((h) => Math.min(options.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (open && options[hi]) pick(options[hi].symbol);
      else if (value.trim()) { rememberGene(value.trim().toUpperCase()); onSubmit?.(value.trim().toUpperCase()); }
    } else if (e.key === "Escape") { setOpen(false); }
    else if (e.key === "Tab") setOpen(false);
  };

  return (
    <div ref={wrap} className="relative">
      <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
      <input ref={inputRef} className="input !pl-9 !pr-9 font-mono uppercase" placeholder="Search genes, e.g. HBB or 'hemoglobin'"
        value={value} onChange={(e) => { onChange(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onClick={() => setOpen(true)} onKeyDown={onKey}
        role="combobox" aria-expanded={open} aria-controls="gene-listbox" aria-autocomplete="list" aria-label="Gene symbol" autoComplete="off"
        aria-activedescendant={open && options[hi] ? `gene-opt-${options[hi].symbol}` : undefined} />
      {value && <button type="button" onClick={() => { onChange(""); setOpen(true); inputRef.current?.focus(); }} className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-faint hover:text-ink" aria-label="Clear search"><X size={14} /></button>}
      <AnchoredPortal anchor={wrap} open={open} minWidth={380} maxHeight={460} onPanel={(el) => { panel.current = el; }}>
        <motion.ul ref={listRef} id="gene-listbox" role="listbox" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
          className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-line bg-surface p-1.5 shadow-lift scrollbar-thin">
          {!value && <li className="eyebrow flex items-center gap-1.5 px-3 pb-1 pt-2" role="presentation"><Sparkles size={12} className="text-accent" />{recentItems.length ? "Recent & suggested genes" : "Suggested starting genes"}</li>}
          {options.map((o, i) => {
            const s = o.s;
            const compatible = !s || s.compatible_datasets.includes(dataset);
            return (
              <li key={`${o.recent ? "r" : "s"}-${o.symbol}`} id={`gene-opt-${o.symbol}`} data-index={i} role="option" aria-selected={hi === i}
                onMouseEnter={() => setHi(i)} onMouseDown={(e) => { e.preventDefault(); pick(o.symbol); }}
                className={`flex cursor-pointer gap-3 rounded-xl px-3 py-2.5 transition-colors ${hi === i ? "bg-raised ring-1 ring-accent/30" : ""}`}>
                <span className="mt-0.5 w-16 shrink-0 font-mono text-[14px] font-medium text-accent">{o.symbol}</span>
                <span className="min-w-0 flex-1">
                  {o.recent ? <span className="flex items-center gap-1.5 text-[13px] text-muted"><Clock size={12} />Recently searched</span> : (
                    <>
                      <span className="block text-[14px] font-semibold">{s?.name ?? "Gene found by gnomAD search"}</span>
                      {s?.description && <span className="block text-[13px] leading-snug text-muted">{s.description}</span>}
                      <span className="mt-1 flex flex-wrap gap-1.5">
                        <span className={`chip ${s?.analysed ? "border-good/40 text-good" : "border-line text-faint"}`}>{s?.data_status}</span>
                        {s?.chrom && <span className="chip border-line font-mono text-faint">chr{s.chrom}</span>}
                        <span className={`chip ${compatible ? "border-accent/40 text-accent" : "border-warn/40 text-warn"}`}>{compatible ? "compatible with selected dataset" : "limited dataset support"}</span>
                      </span>
                    </>
                  )}
                </span>
              </li>
            );
          })}
          {!loading && options.length === 0 && <li className="px-3 py-3 text-sm text-muted">No matching genes{live?.startsWith("unavailable") ? " (live search unavailable)" : ""}. Press Enter to try “{value.toUpperCase()}” anyway.</li>}
          {loading && value && <li className="px-3 py-2 text-xs text-faint">Searching gnomAD…</li>}
          {value && live && !live.startsWith("unavailable") && <li className="px-3 pb-1 pt-2 text-[11.5px] text-faint">Includes live results from {live}</li>}
        </motion.ul>
      </AnchoredPortal>
    </div>
  );
}

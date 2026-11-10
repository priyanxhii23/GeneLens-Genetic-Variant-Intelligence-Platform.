import { AnimatePresence, animate, motion, useInView, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { AlertTriangle, BookOpen, ChevronDown, FlaskConical, Lightbulb, ShieldCheck, Star } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CLASS_META, MATCH_LABELS } from "../lib/format";
import { GLOSSARY } from "../lib/glossary";
import type { CoarseClass, Provenance } from "../lib/types";

export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
export const rise = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } } };

/** GeneLens mark: the double-helix tile (same drawing as the favicon). */
export function LogoMark({ size = 46 }: { size?: number }) {
  return (
    <span className="relative inline-grid shrink-0 place-items-center rounded-[14px] border border-accent/35 bg-gradient-to-br from-accent/15 via-surface to-violet/15 shadow-glow-sm"
      style={{ width: size, height: size }} aria-hidden>
      <svg viewBox="0 0 32 32" width={size * 0.66} height={size * 0.66}>
        <path d="M10 4c0 8 12 8 12 16s-12 8-12 8M22 4c0 8-12 8-12 16s12 8 12 8" fill="none" stroke="rgb(var(--accent))" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M12 9h8M12 23h8M14 16h4" stroke="rgb(var(--violet))" strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function Panel({ title, eyebrow, actions, children, className = "", bodyClass = "p-5" }: {
  title?: ReactNode; eyebrow?: string; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <motion.section variants={rise} className={`panel ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
          <div>
            {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
            {title && <h3 className="card-title">{title}</h3>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </motion.section>
  );
}

export function PageHeader({ index, title, subtitle, actions }: { index: string; title: string; subtitle: ReactNode; actions?: ReactNode }) {
  return (
    <motion.header variants={rise} className="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <div className="eyebrow mb-2 flex items-center gap-2"><span className="text-accent">{index}</span><span className="h-px w-10 bg-gradient-to-r from-accent/60 to-transparent" /></div>
        <h1 className="page-title">{title}</h1>
        <p className="mt-2.5 text-[16px] leading-relaxed text-muted">{subtitle}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </motion.header>
  );
}

/**
 * Smoothly counts to `value` when visible. A value that changes while the
 * counter is off-screen is applied immediately, so the number is never stale.
 */
export function Counter({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref);
  const reduce = useReducedMotion();
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => v.toLocaleString(undefined, { maximumFractionDigits: decimals, minimumFractionDigits: decimals }));
  useEffect(() => {
    if (reduce || !inView) { mv.set(value); return; }
    const c = animate(mv, value, { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
    return () => { c.stop(); mv.set(value); };
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // first reveal: count up from zero once
    if (!inView || reduce || mv.get() !== value || value === 0 || ref.current?.dataset.revealed) return;
    ref.current!.dataset.revealed = "1";
    mv.set(0);
    const c = animate(mv, value, { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
    return () => { c.stop(); mv.set(value); };
  }, [inView]); // eslint-disable-line react-hooks/exhaustive-deps
  return <motion.span ref={ref}>{text}</motion.span>;
}

export function Metric({ label, value, value2, hint, tone = "accent", icon, decimals, glow = false }: {
  label: string; value: number | null | undefined; value2?: number | null; hint?: ReactNode; tone?: string;
  icon?: ReactNode; decimals?: number; glow?: boolean;
}) {
  return (
    <motion.div variants={rise} whileHover={{ y: -3 }} className={`panel group overflow-hidden p-4 ${glow ? "shadow-glow-sm" : ""}`}>
      <div className={`absolute inset-x-4 top-0 h-px bg-gradient-to-r from-transparent via-${tone}/70 to-transparent opacity-60 transition-opacity group-hover:opacity-100`} />
      <div className="flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        {icon && <span className={`text-${tone}`}>{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="data text-[28px] font-medium md:text-[32px]">{value === null || value === undefined ? "—" : <Counter value={value} decimals={decimals} />}</span>
        {value2 !== undefined && value2 !== null && (
          <span className="data text-[15px] text-pink" title="synthetic records"><Counter value={value2} /> syn</span>
        )}
      </div>
      {hint && <div className="mt-1 text-[12.5px] text-muted">{hint}</div>}
    </motion.div>
  );
}

export function ClassBadge({ cls, label }: { cls: CoarseClass | string | null | undefined; label?: string | null }) {
  const m = CLASS_META[(cls as CoarseClass) ?? "OTHER"] ?? CLASS_META.OTHER;
  return (
    <span className={`chip border-${m.color}/40 bg-${m.color}/10 text-ink`} title={label ?? m.label}>
      <span className={`h-1.5 w-1.5 rounded-full bg-${m.color}`} />{m.short}
    </span>
  );
}

export function ProvenanceBadge({ p, source }: { p: Provenance; source?: string | null }) {
  return p === "SYNTHETIC" ? (
    <span className="chip border-pink/50 bg-pink/10 text-pink" title="Simulated record – not a real observation">
      <FlaskConical size={11} />SYNTHETIC
    </span>
  ) : (
    <span className="chip border-gold/50 bg-gold/10 text-gold" title="Record retrieved from a public database">
      <ShieldCheck size={11} />REAL{source ? ` · ${source}` : ""}
    </span>
  );
}

export function MatchBadge({ s }: { s: string }) {
  const tone = s === "exact" ? "good" : s === "normalized" ? "accent" : s === "ambiguous" ? "warn" : s === "synthetic" ? "pink" : "faint";
  return <span className={`chip border-${tone}/40 text-${tone}`}>{MATCH_LABELS[s] ?? s}</span>;
}

export function Stars({ n }: { n: number | null | undefined }) {
  if (n === null || n === undefined) return <span className="text-faint">—</span>;
  return (
    <span className="inline-flex" aria-label={`${n} of 4 review stars`} title={`${n}/4 ClinVar review stars`}>
      {[0, 1, 2, 3].map((i) => <Star key={i} size={12} className={i < n ? "fill-vus text-vus" : "text-line"} />)}
    </span>
  );
}

/** Technical term with an accessible tooltip definition from the glossary. */
export function Term({ k, children }: { k: string; children?: ReactNode }) {
  const g = GLOSSARY[k];
  const [open, setOpen] = useState(false);
  const id = useId();
  if (!g) return <>{children ?? k}</>;
  return (
    <span className="relative inline-block" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <b className="term" tabIndex={0} aria-describedby={id} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>{children ?? k}</b>
      <AnimatePresence>
        {open && (
          <motion.span id={id} role="tooltip" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-xl border border-line bg-surface p-3 text-left text-[13px] font-normal leading-snug text-muted shadow-lift">
            <span className="mb-1 block font-semibold text-ink">{g.label}</span>{g.def}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

/** Two-level explanation: a prominent main reason, then the detailed explanation (Part 4). */
export function Insight({ label = "Why this result appears", reason, children, tone = "accent", compact = false }: {
  label?: string; reason: ReactNode; children?: ReactNode; tone?: string; compact?: boolean;
}) {
  return (
    <motion.div variants={rise} className={`relative rounded-2xl border border-line/80 bg-raised/40 ${compact ? "p-4" : "p-5"}`}>
      <span className={`absolute left-0 top-5 h-8 w-[3px] rounded-r-full bg-${tone}`} aria-hidden />
      <div className="eyebrow mb-1.5 flex items-center gap-1.5 !text-[12.5px]"><Lightbulb size={13} className={`text-${tone}`} />{label}</div>
      <p className="insight-reason">{reason}</p>
      {children && <div className="insight-detail mt-3 space-y-3">{children}</div>}
    </motion.div>
  );
}

/** "How to read this" educational section – open by default, collapsible. */
export function Guide({ title = "How to read this", children, defaultOpen = true }: { title?: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <motion.section variants={rise} className="panel">
      <button className="flex w-full items-center gap-2.5 px-5 py-4 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/10 text-accent"><BookOpen size={16} /></span>
        <span className="section-title !text-[21px]">{title}</span>
        <ChevronDown size={18} className={`ml-auto text-faint transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }} className="overflow-hidden">
            <div className="guide grid gap-x-10 gap-y-4 px-5 pb-5 md:grid-cols-2">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

/** One entry inside a Guide: a bold heading term plus plain-language text. */
export function GuideItem({ term, children }: { term: ReactNode; children: ReactNode }) {
  return <div><div className="mb-0.5 text-[15px] font-bold text-ink">{term}</div><div>{children}</div></div>;
}

/** Kept for compatibility: collapsed guide. */
export function Explain({ children, title = "How to read this" }: { children: ReactNode; title?: string }) {
  return <Guide title={title} defaultOpen={false}>{children}</Guide>;
}

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/5 text-warn ${compact ? "px-3 py-2 text-[13px]" : "px-4 py-3 text-sm"}`}>
      <AlertTriangle size={compact ? 14 : 16} className="mt-0.5 shrink-0" />
      <span>Exploratory research tool – <b>not</b> for diagnosis or clinical decision-making. Flags are prompts for expert review, never verdicts.</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-bad/40 bg-bad/5 px-4 py-3 text-sm text-bad">
      <AlertTriangle size={16} /> <span className="flex-1">{message}</span>
      {onRetry && <button className="btn-ghost !py-1 text-xs" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function HelixLoader({ label = "Processing" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-muted" role="status">
      <svg width="40" height="20" viewBox="0 0 40 20" aria-hidden>
        {Array.from({ length: 8 }).map((_, i) => (
          <motion.circle key={i} cx={3 + i * 4.9} cy={10} r={2} fill={i % 2 ? "rgb(var(--violet))" : "rgb(var(--accent))"} initial={{ cy: 4 }}
            animate={{ cy: [4, 16, 4], opacity: [1, 0.4, 1] }} transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.11, ease: "easeInOut" }} />
        ))}
      </svg>
      {label}
    </div>
  );
}

export function Skeleton({ className = "h-24" }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-xl bg-raised/70 ${className}`} aria-hidden>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-accent/10 to-transparent" />
    </div>
  );
}

export function NeedsAnalysis() {
  return (
    <div className="panel flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="section-title">No analysis selected</div>
      <p className="max-w-md text-muted">Run an analysis for a gene in the Command Center, or reopen a previous one from the Report Generator's analysis history. Every module works on the selected analysis.</p>
      <div className="flex gap-2"><Link to="/workspace" className="btn-primary">Open Command Center</Link><Link to="/workspace/reports" className="btn-ghost">Analysis history</Link></div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[] }) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-raised/60 p-1" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={`relative rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors ${value === o.value ? "text-bg" : "text-muted hover:text-ink"}`}>
          {value === o.value && <motion.span layoutId={`tab-${options.map((x) => x.value).join()}`} className="absolute inset-0 rounded-lg bg-accent shadow-glow-sm" transition={{ type: "spring", bounce: 0.2, duration: 0.45 }} />}
          <span className="relative inline-flex items-center gap-1.5">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

export function PriorityBadge({ p }: { p: "high" | "medium" | "low" }) {
  const cls = p === "high" ? "border-bad/50 bg-bad/10 text-bad" : p === "medium" ? "border-warn/50 bg-warn/10 text-warn" : "border-line bg-raised text-muted";
  return (
    <span className={`chip ${cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${p === "high" ? "bg-bad pulse-high" : p === "medium" ? "bg-warn" : "bg-faint"}`} />
      {p[0].toUpperCase() + p.slice(1)} priority
    </span>
  );
}

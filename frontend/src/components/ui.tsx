import { animate, motion, useInView, useMotionValue, useReducedMotion, useTransform } from "framer-motion";
import { AlertTriangle, FlaskConical, Info, Star } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CLASS_META, MATCH_LABELS } from "../lib/format";
import type { CoarseClass, Provenance } from "../lib/types";

export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06 } } };
export const rise = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } } };

export function Panel({ title, eyebrow, actions, children, className = "", bodyClass = "p-5" }: {
  title?: ReactNode; eyebrow?: string; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <motion.section variants={rise} className={`panel ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
          <div>
            {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
            {title && <h3 className="font-display text-lg leading-tight">{title}</h3>}
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
    <motion.header variants={rise} className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        <div className="eyebrow mb-2 flex items-center gap-2"><span className="text-accent">{index}</span><span className="h-px w-8 bg-line" /></div>
        <h1 className="font-display text-3xl font-light tracking-tight md:text-4xl">{title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">{subtitle}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </motion.header>
  );
}

/** Smoothly counts up to `value` when scrolled into view. */
export function Counter({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => v.toLocaleString(undefined, { maximumFractionDigits: decimals, minimumFractionDigits: decimals }));
  useEffect(() => {
    if (!inView) return;
    if (reduce) { mv.set(value); return; }
    const c = animate(mv, value, { duration: 1.2, ease: [0.22, 1, 0.36, 1] });
    return () => c.stop();
  }, [inView, value, reduce, mv]);
  return <motion.span ref={ref}>{text}</motion.span>;
}

export function Metric({ label, value, hint, tone = "accent", icon, decimals }: {
  label: string; value: number | null | undefined; hint?: ReactNode; tone?: string; icon?: ReactNode; decimals?: number;
}) {
  return (
    <motion.div variants={rise} whileHover={{ y: -2 }} className="panel group relative overflow-hidden p-4">
      <div className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-${tone}/60 to-transparent opacity-60 group-hover:opacity-100`} />
      <div className="flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        {icon && <span className={`text-${tone}`}>{icon}</span>}
      </div>
      <div className="data mt-2 text-2xl font-medium md:text-3xl">{value === null || value === undefined ? "—" : <Counter value={value} decimals={decimals} />}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </motion.div>
  );
}

export function ClassBadge({ cls, label }: { cls: CoarseClass; label?: string | null }) {
  const m = CLASS_META[cls] ?? CLASS_META.OTHER;
  return (
    <span className={`chip border-${m.color}/40 bg-${m.color}/10 text-ink`} title={label ?? m.label}>
      <span className={`h-1.5 w-1.5 rounded-full bg-${m.color}`} />{m.short}
    </span>
  );
}

export function ProvenanceBadge({ p }: { p: Provenance }) {
  return p === "SYNTHETIC" ? (
    <span className="chip synthetic-hatch border-violet/50 text-violet" title="Simulated record – not a real observation">
      <FlaskConical size={11} />SYNTHETIC
    </span>
  ) : (
    <span className="chip border-accent/40 text-accent" title="Record retrieved from a public database">REAL</span>
  );
}

export function MatchBadge({ s }: { s: string }) {
  const tone = s === "exact" ? "good" : s === "normalized" ? "accent" : s === "ambiguous" ? "warn" : "faint";
  return <span className={`chip border-${tone}/40 text-${tone}`}>{MATCH_LABELS[s] ?? s}</span>;
}

export function Stars({ n }: { n: number | null | undefined }) {
  if (n === null || n === undefined) return <span className="text-faint">—</span>;
  return (
    <span className="inline-flex" aria-label={`${n} of 4 review stars`} title={`${n}/4 ClinVar review stars`}>
      {[0, 1, 2, 3].map((i) => <Star key={i} size={11} className={i < n ? "fill-vus text-vus" : "text-line"} />)}
    </span>
  );
}

export function Explain({ children, title = "How to read this" }: { children: ReactNode; title?: string }) {
  return (
    <details className="group rounded-xl border border-line/70 bg-raised/50 px-4 py-3 text-sm text-muted">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-ink"><Info size={14} className="text-accent" />{title}</summary>
      <div className="mt-2 space-y-2 leading-relaxed">{children}</div>
    </details>
  );
}

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/5 text-warn ${compact ? "px-3 py-2 text-xs" : "px-4 py-3 text-sm"}`}>
      <AlertTriangle size={compact ? 13 : 16} className="mt-0.5 shrink-0" />
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
      <svg width="34" height="20" viewBox="0 0 34 20" aria-hidden>
        {Array.from({ length: 7 }).map((_, i) => (
          <motion.circle key={i} cx={3 + i * 4.6} cy={10} r={2} fill="rgb(var(--accent))" initial={{ cy: 4 }}
            animate={{ cy: [4, 16, 4], opacity: [1, 0.4, 1] }} transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.12 }} />
        ))}
      </svg>
      {label}
    </div>
  );
}

export function NeedsAnalysis() {
  return (
    <div className="panel flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="font-display text-2xl font-light">No analysis selected</div>
      <p className="max-w-md text-sm text-muted">Run an analysis for a gene in the Command Center, or reopen one from Research History. Every module works on the selected analysis.</p>
      <div className="flex gap-2"><Link to="/workspace" className="btn-primary">Open Command Center</Link><Link to="/workspace/history" className="btn-ghost">History</Link></div>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-raised/60 p-1" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={value === o.value} onClick={() => onChange(o.value)}
          className={`relative rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${value === o.value ? "text-bg" : "text-muted hover:text-ink"}`}>
          {value === o.value && <motion.span layoutId={`tab-${options.map((x) => x.value).join()}`} className="absolute inset-0 rounded-lg bg-accent" transition={{ type: "spring", bounce: 0.2, duration: 0.45 }} />}
          <span className="relative">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

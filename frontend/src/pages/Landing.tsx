import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, CircleDot, FlaskConical, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import DnaHelix from "../components/DnaHelix";
import { LogoMark } from "../components/ui";
import { NAV } from "../components/Sidebar";
import { ThemeToggle } from "../components/Workspace";
import { api } from "../lib/api";
import type { SourceStatus } from "../lib/types";

const PIPELINE = ["Collection", "Validation", "Preprocessing", "Normalization", "gnomAD–ClinVar matching",
  "Statistics", "Anomaly screening", "Visualization", "Interpretation", "Report"];

const MODULE_COPY: Record<string, string> = {
  "Command Center": "Launch gene analyses, watch data-source health and see live counts computed from loaded records.",
  "Variant Explorer": "Search, filter, sort and inspect every allele with its matching evidence, then export to CSV.",
  "Pathogenicity Lab": "Compare P, LP, VUS, LB and B variants on log-frequency scales with review-status context.",
  "Population Observatory": "Allele frequencies across gnomAD genetic-ancestry groups, with missing data shown explicitly.",
  "Constraint Observatory": "pLI, LOEUF and observed/expected counts – with what each metric does and does not mean.",
  "Anomaly Engine": "Rules, robust outliers and Isolation Forest, each flag with evidence, priority and an explanation.",
  "Statistics Studio": "Mann–Whitney, chi-square, Fisher, Spearman – assumptions checked, FDR-corrected, explained.",
  "Synthetic Lab": "Seeded generator fitted to real distributions. Every simulated record is permanently labelled.",
  "Report Generator": "PDF and CSV research reports with methodology, charts, limitations and citations.",
  "Gene Comparison Lab": "Compare 2–5 genes, re-filter by population, class and review status, and run what-if screening scenarios.",
  "Source Manager": "Seven live connectors – gnomAD, ClinVar (API + bulk), Ensembl, dbSNP, IGSR/1000 Genomes, UCSC – with honest status.",
};

function Schematic({ index }: { index: number }) {
  // Abstract schematic only – deliberately not a chart of invented data.
  const reduce = useReducedMotion();
  const bars = Array.from({ length: 14 }, (_, i) => 0.25 + 0.7 * Math.abs(Math.sin((i + 1) * (index + 2) * 0.7)));
  return (
    <svg viewBox="0 0 280 150" className="h-full w-full" aria-hidden>
      {bars.map((b, i) => (
        <motion.rect key={`${index}-${i}`} x={12 + i * 19} width={11} rx={3} fill={i % 3 === 0 ? "rgb(var(--violet))" : "rgb(var(--accent))"} fillOpacity={0.75}
          initial={{ height: 0, y: 140 }} animate={{ height: b * 110, y: 140 - b * 110 }} transition={{ duration: reduce ? 0 : 0.6, delay: reduce ? 0 : i * 0.03 }} />
      ))}
      <line x1="8" x2="272" y1="140.5" y2="140.5" stroke="rgb(var(--line))" />
    </svg>
  );
}

function Headline() {
  const words = ["Where", "population", "frequency", "meets", "clinical", "meaning."];
  return (
    <h1 className="font-display text-[clamp(2.6rem,7vw,5.6rem)] font-light leading-[0.98] tracking-tight">
      {words.map((w, i) => (
        <motion.span key={w} className={`mr-[0.22em] inline-block ${i >= 4 ? "italic text-accent" : ""}`}
          initial={{ opacity: 0, y: 40, filter: "blur(8px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.8, delay: 0.15 + i * 0.09, ease: [0.22, 1, 0.36, 1] }}>{w}</motion.span>
      ))}
    </h1>
  );
}

export default function Landing() {
  const [status, setStatus] = useState<SourceStatus | null>(null);
  const [statusErr, setStatusErr] = useState(false);
  const [active, setActive] = useState(0);
  const heroRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  const helixY = useTransform(scrollYProgress, [0, 1], ["0%", "30%"]);
  const fade = useTransform(scrollYProgress, [0, 0.8], [1, 0]);

  useEffect(() => { api.sources().then(setStatus).catch(() => setStatusErr(true)); }, []);
  const mods = NAV.map((n) => n.label);

  return (
    <div className="relative overflow-x-hidden">
      <nav className="fixed inset-x-0 top-0 z-30 flex items-center justify-between px-5 py-4 md:px-10">
        <div className="flex items-center gap-3 font-display text-[26px]"><LogoMark size={44} />GeneLens</div>
        <div className="flex items-center gap-2"><ThemeToggle /><Link to="/workspace" className="btn-ghost hidden sm:inline-flex">Workspace</Link></div>
      </nav>

      {/* HERO */}
      <section ref={heroRef} className="relative flex min-h-[100svh] items-center">
        <motion.div style={{ y: helixY }} className="absolute inset-0"><DnaHelix /></motion.div>
        <div className="absolute inset-0 bg-gradient-to-b from-bg/30 via-bg/50 to-bg" />
        <motion.div style={{ opacity: fade }} className="relative mx-auto w-full max-w-6xl px-5 pt-24 md:px-10">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="eyebrow mb-6 flex items-center gap-2">
            <span className="h-px w-10 bg-accent" />gnomAD × ClinVar · genetic variant intelligence
          </motion.div>
          <Headline />
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.9 }}
            className="mt-7 max-w-2xl text-base leading-relaxed text-muted md:text-lg">
            GeneLens retrieves real allele frequencies from gnomAD and clinical classifications from ClinVar,
            matches them allele-by-allele, and lets you investigate how frequency and interpretation relate –
            with every statistic computed, every flag explained, and every simulated record labelled.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.05 }} className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/workspace" className="btn-primary group relative overflow-hidden !px-7 !py-3.5 text-[16px] shadow-glow">
              <span className="absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/30 to-transparent transition-transform duration-700 group-hover:translate-x-full" aria-hidden />
              <span className="relative">Enter Research Workspace</span> <ArrowRight size={18} className="relative transition-transform group-hover:translate-x-1" />
            </Link>
            <div className="flex flex-wrap gap-2 text-xs">
              {statusErr && <span className="chip border-warn/40 text-warn">backend offline – start the API to connect</span>}
              {status && (["gnomad", "clinvar"] as const).map((k) => (
                <span key={k} className={`chip ${status[k].available ? "border-good/40 text-good" : "border-bad/40 text-bad"}`} title={status[k].detail}>
                  <CircleDot size={10} />{k === "gnomad" ? "gnomAD" : "ClinVar"} {status[k].available ? "live" : "unavailable"}
                </span>
              ))}
            </div>
          </motion.div>
        </motion.div>
        <motion.div animate={{ y: [0, 8, 0] }} transition={{ repeat: Infinity, duration: 2.2 }} className="eyebrow absolute bottom-6 left-1/2 hidden -translate-x-1/2 md:block">scroll</motion.div>
      </section>

      {/* PROBLEM */}
      <section className="mx-auto max-w-6xl px-5 py-24 md:px-10">
        <div className="grid gap-12 md:grid-cols-[1fr_1.3fr]">
          <motion.div initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true, margin: "-80px" }}>
            <div className="eyebrow mb-3">The research question</div>
            <h2 className="font-display text-3xl font-light leading-tight md:text-4xl">How often do clinical classifications agree with what populations tell us?</h2>
          </motion.div>
          <motion.div initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} className="space-y-4 text-muted">
            <p>A variant labelled <em className="text-ink">pathogenic</em> for a rare disease is usually rare in the general population. When it is not – or when a <em className="text-ink">benign</em> label sits on an allele seen once in a million chromosomes – the combination deserves a closer look.</p>
            <p>Sometimes there is a biological explanation: recessive carriers, reduced penetrance, founder effects, balancing selection. Sometimes the record itself is incomplete. GeneLens separates those possibilities instead of declaring anything “misclassified”.</p>
          </motion.div>
        </div>
      </section>

      {/* MODULE PREVIEWS */}
      <section className="mx-auto max-w-6xl px-5 pb-24 md:px-10">
        <div className="eyebrow mb-3">Eleven research modules · ten datasets · seven integrated sources</div>
        <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
          <ul className="space-y-1">
            {mods.map((m, i) => (
              <li key={m}>
                <button onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onClick={() => setActive(i)}
                  className={`group flex w-full items-baseline gap-4 rounded-xl px-4 py-3 text-left transition-colors ${active === i ? "bg-surface/80" : "hover:bg-surface/40"}`}>
                  <span className="data text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <span className={`font-display text-xl transition-colors ${active === i ? "text-accent" : ""}`}>{m}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="panel sticky top-24 h-fit overflow-hidden p-6">
            <motion.div key={active} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
              <div className="eyebrow mb-2">module {String(active + 1).padStart(2, "0")} · schematic</div>
              <h3 className="font-display text-2xl">{mods[active]}</h3>
              <p className="mt-2 text-sm text-muted">{MODULE_COPY[mods[active]]}</p>
              <div className="mt-6 h-40"><Schematic index={active} /></div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* PIPELINE */}
      <section className="border-y border-line bg-surface/40 py-20">
        <div className="mx-auto max-w-6xl px-5 md:px-10">
          <div className="eyebrow mb-3">Reproducible methodology</div>
          <h2 className="mb-10 font-display text-3xl font-light">One pipeline, testable stage by stage.</h2>
          <ol className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {PIPELINE.map((p, i) => (
              <motion.li key={p} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }}
                className="panel relative p-4">
                <span className="data text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>
                <div className="mt-1 text-sm">{p}</div>
              </motion.li>
            ))}
          </ol>
        </div>
      </section>

      {/* PRINCIPLES */}
      <section className="mx-auto grid max-w-6xl gap-5 px-5 py-24 md:grid-cols-3 md:px-10">
        {[
          { icon: ShieldCheck, t: "Real data, stated provenance", d: "Every dataset records source, release, genome build, access mode and retrieval date. Offline snapshots are labelled as such." },
          { icon: FlaskConical, t: "Synthetic, never disguised", d: "Simulated records carry a permanent SYNTHETIC label, hatched styling and SYN- identifiers in every table, chart and export." },
          { icon: Sparkles, t: "Explanations over verdicts", d: "Flags separate data-quality problems from biologically interesting observations. Nothing is called a false classification." },
        ].map(({ icon: Icon, t, d }, i) => (
          <motion.div key={t} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.08 }} className="panel p-6">
            <Icon className="text-accent" size={22} />
            <h3 className="mt-4 font-display text-xl">{t}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{d}</p>
          </motion.div>
        ))}
      </section>

      <section className="mx-auto max-w-6xl px-5 pb-24 text-center md:px-10">
        <Link to="/workspace" className="btn-primary !px-7 !py-3 text-base">Enter Research Workspace <ArrowRight size={18} /></Link>
        <p className="mx-auto mt-8 max-w-2xl text-xs leading-relaxed text-faint">
          GeneLens is an exploratory research and education tool. It is not a medical device and must not be used for diagnosis,
          screening or clinical decision-making. Data: gnomAD (Broad Institute) and ClinVar (NCBI) – see the README for citations.
        </p>
      </section>
    </div>
  );
}

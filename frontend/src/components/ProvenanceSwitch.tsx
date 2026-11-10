import { motion } from "framer-motion";
import { PROV_META, useProvenance } from "../lib/provenance";
import type { ProvMode } from "../lib/types";

const ACTIVE: Record<ProvMode, string> = {
  REAL: "border-gold/60 bg-gold/10 shadow-glow-gold",
  SYNTHETIC: "border-pink/60 bg-pink/10 shadow-glow-pink",
  BOTH: "border-accent/50 bg-accent/10 shadow-glow-sm",
};

/** REAL / SYNTHETIC / BOTH segmented control. Drives filtering everywhere. */
export default function ProvenanceSwitch() {
  const { mode, setMode } = useProvenance();
  return (
    <div className="inline-flex items-center rounded-xl border border-line bg-raised/70 p-1" role="radiogroup" aria-label="Data display mode">
      {(Object.keys(PROV_META) as ProvMode[]).map((m) => {
        const meta = PROV_META[m];
        const on = mode === m;
        return (
          <button key={m} role="radio" aria-checked={on} title={meta.hint} onClick={() => setMode(m)}
            className={`relative flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12.5px] font-semibold transition-colors ${on ? "text-ink" : "text-muted hover:text-ink"}`}>
            {on && <motion.span layoutId="prov-switch" className={`absolute inset-0 rounded-lg border ${ACTIVE[m]}`}
              transition={{ type: "spring", bounce: 0.2, duration: 0.45 }} />}
            <span className="relative flex items-center gap-1.5">
              {m === "BOTH" ? <span className="flex"><span className="h-2 w-2 rounded-full bg-gold" /><span className="-ml-0.5 h-2 w-2 rounded-full bg-pink" /></span>
                : <span className={`h-2 w-2 rounded-full bg-${meta.color}`} />}
              {meta.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

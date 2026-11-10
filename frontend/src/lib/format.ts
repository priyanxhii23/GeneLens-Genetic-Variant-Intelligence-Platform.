import type { CoarseClass } from "./types";

export const CLASS_META: Record<CoarseClass, { label: string; short: string; color: string }> = {
  P_LP: { label: "Pathogenic / Likely pathogenic", short: "P/LP", color: "plp" },
  VUS: { label: "Uncertain significance", short: "VUS", color: "vus" },
  B_LB: { label: "Benign / Likely benign", short: "B/LB", color: "blb" },
  CONFLICTING: { label: "Conflicting", short: "Conflicting", color: "conf" },
  OTHER: { label: "Other / not provided", short: "Other", color: "other" },
  NOT_IN_CLINVAR: { label: "Not in ClinVar", short: "No ClinVar", color: "other" },
};
export const MAIN_CLASSES: CoarseClass[] = ["P_LP", "VUS", "B_LB", "CONFLICTING"];

export const FINE_LABELS: Record<string, string> = {
  pathogenic: "Pathogenic", likely_pathogenic: "Likely pathogenic", pathogenic_likely_pathogenic: "Pathogenic/Likely pathogenic",
  uncertain_significance: "Uncertain significance", likely_benign: "Likely benign", benign: "Benign",
  benign_likely_benign: "Benign/Likely benign", conflicting: "Conflicting", other: "Other", not_provided: "Not provided",
};

export const POP_LABELS: Record<string, string> = {
  afr: "African / African American", ami: "Amish", amr: "Admixed American", asj: "Ashkenazi Jewish",
  eas: "East Asian", fin: "Finnish", mid: "Middle Eastern", nfe: "Non-Finnish European", sas: "South Asian",
  remaining: "Remaining", oth: "Other",
};

export const MATCH_LABELS: Record<string, string> = {
  exact: "Exact", normalized: "Normalized", ambiguous: "Ambiguous", gnomad_only: "gnomAD only",
  clinvar_only: "ClinVar only", unmatchable: "Unmatchable", secondary_clinvar: "Secondary ClinVar", synthetic: "Synthetic",
};

/** Read a CSS RGB-triplet token and return an rgb() string usable by Plotly. */
export function token(name: string, alpha = 1): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim().split(/\s+/).join(",");
  return alpha === 1 ? `rgb(${v})` : `rgba(${v},${alpha})`;
}

export function fmtAF(af: number | null | undefined): string {
  if (af === null || af === undefined) return "—";
  if (af === 0) return "0";
  if (af < 1e-3) return af.toExponential(2);
  return af.toPrecision(3);
}
export function fmtInt(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : n.toLocaleString();
}
export function fmtP(p: number | null | undefined): string {
  if (p === null || p === undefined) return "—";
  if (p === 0) return "< 1e-300";
  return p < 1e-3 ? p.toExponential(2) : p.toFixed(3);
}
export function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (Math.abs(v) !== 0 && (Math.abs(v) < 1e-3 || Math.abs(v) >= 1e6)) return v.toExponential(2);
  return Number(v.toPrecision(digits)).toString();
}
export function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
export const pct = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);

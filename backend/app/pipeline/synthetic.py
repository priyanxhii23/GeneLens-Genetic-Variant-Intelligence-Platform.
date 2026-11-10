"""Synthetic variant generation (Module 8).

Design principles
-----------------
* **Distributions, not records.** When a real analysis is supplied, only
  summary parameters are estimated from it (class proportions, a Gaussian
  mixture over log10 AF per class, a normal model of log10 AN, population
  AN shares and population AF dispersion). No real variant, coordinate or
  identifier is copied.
* **Internally consistent counts.** Population allele counts are drawn as
  Binomial(AN_pop, AF_pop); global AC/AN are their sums and AF = AC/AN.
* **No fabricated clinical evidence.** Synthetic records get a simulated
  classification label but no conditions, submitters or review stars.
* **Permanent provenance.** Every record has ``provenance = "SYNTHETIC"``,
  a ``SYN-`` identifier and chromosome ``SYN``.
* **Reproducible.** All randomness flows from one ``numpy`` Generator seeded
  by the user-supplied seed.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import stats

from app.pipeline.preprocessing import FINE_LABELS, POPULATION_LABELS

CLASSES = ["P_LP", "VUS", "B_LB", "CONFLICTING"]
FINE_FOR_COARSE = {"P_LP": ["pathogenic", "likely_pathogenic"], "VUS": ["uncertain_significance"],
                   "B_LB": ["benign", "likely_benign"], "CONFLICTING": ["conflicting"]}
DEFAULT_POPULATIONS = ["afr", "amr", "asj", "eas", "fin", "mid", "nfe", "sas", "remaining"]
# Parametric defaults used only when no real dataset is supplied. They are
# rough, documented priors – not estimates from any particular gene.
DEFAULT_MODEL = {
    "source": "parametric_default",
    "class_weights": {"P_LP": 0.25, "VUS": 0.35, "B_LB": 0.35, "CONFLICTING": 0.05},
    "log10_af": {"P_LP": [[1.0, -5.3, 0.6]], "VUS": [[1.0, -5.0, 0.8]],
                 "B_LB": [[1.0, -3.8, 1.2]], "CONFLICTING": [[1.0, -4.5, 1.0]]},
    "log10_an": {"mean": 6.1, "sd": 0.15, "min": 4.0, "max": 6.5},
    "population_an_share": {"afr": 0.04, "amr": 0.03, "asj": 0.02, "eas": 0.03, "fin": 0.04,
                            "mid": 0.005, "nfe": 0.74, "sas": 0.055, "remaining": 0.04},
    "population_log10_dispersion": 0.5,
    "fine_split": {"P_LP": {"pathogenic": 0.6, "likely_pathogenic": 0.4},
                   "B_LB": {"benign": 0.3, "likely_benign": 0.7}},
    "variant_types": {"SNV": 0.85, "deletion": 0.1, "insertion": 0.05},
}


@dataclass
class SyntheticParams:
    n_records: int = 1000
    seed: int = 42
    class_distribution: dict[str, float] | None = None  # None => mirror fitted/real
    missing_rate: float = 0.0
    conflicting_rate: float = 0.0
    unusual_rate: float = 0.0
    populations: list[str] = field(default_factory=lambda: list(DEFAULT_POPULATIONS))

    def validate(self):
        if not 1 <= self.n_records <= 100_000:
            raise ValueError("n_records must be between 1 and 100,000")
        for name in ("missing_rate", "conflicting_rate", "unusual_rate"):
            v = getattr(self, name)
            if not 0 <= v <= 0.5:
                raise ValueError(f"{name} must be between 0 and 0.5")
        if self.class_distribution:
            if any(k not in CLASSES for k in self.class_distribution):
                raise ValueError(f"class_distribution keys must be in {CLASSES}")
            if sum(self.class_distribution.values()) <= 0:
                raise ValueError("class_distribution weights must sum to > 0")
        if not self.populations:
            raise ValueError("at least one population is required")


# ---------------------------------------------------------------------------
# Model fitting
# ---------------------------------------------------------------------------
def _fit_mixture(x: np.ndarray, seed: int) -> list[list[float]]:
    from sklearn.mixture import GaussianMixture

    if x.size < 5 or np.ptp(x) == 0:
        mu = float(x.mean()) if x.size else -5.0
        return [[1.0, mu, 0.5]]
    k = 1 if x.size < 30 else 2 if x.size < 200 else 3
    gm = GaussianMixture(n_components=k, random_state=seed).fit(x.reshape(-1, 1))
    return [[float(w), float(m[0]), float(math.sqrt(c.ravel()[0]))]
            for w, m, c in zip(gm.weights_, gm.means_, gm.covariances_)]


def fit_model(real_rows: list[dict], seed: int = 0) -> dict:
    """Estimate summary distributions from real, matched variants."""
    rows = [r for r in real_rows if r.get("provenance", "REAL") == "REAL" and r.get("in_gnomad")
            and r.get("in_clinvar") and (r.get("af") or 0) > 0 and r.get("coarse_class") in CLASSES
            and r.get("match_status") in ("exact", "normalized")]
    if len(rows) < 20:
        model = {**DEFAULT_MODEL, "note": f"Only {len(rows)} usable real variants – parametric defaults used."}
        return model
    model: dict = {"source": "fitted_from_real", "n_real_used": len(rows)}
    counts = {c: sum(1 for r in rows if r["coarse_class"] == c) for c in CLASSES}
    model["class_weights"] = {c: counts[c] / len(rows) for c in CLASSES}
    model["log10_af"] = {}
    for c in CLASSES:
        x = np.log10([r["af"] for r in rows if r["coarse_class"] == c])
        model["log10_af"][c] = _fit_mixture(np.asarray(x), seed) if x.size else DEFAULT_MODEL["log10_af"][c]
    an = np.log10([r["an"] for r in rows if r.get("an")])
    model["log10_an"] = {"mean": float(an.mean()), "sd": float(max(an.std(), 0.01)),
                         "min": float(an.min()), "max": float(an.max())}
    shares, disp = {}, []
    for r in rows:
        tot = sum(p["an"] for p in r.get("populations") or [] if p.get("an"))
        for p in r.get("populations") or []:
            if tot and p.get("an"):
                shares.setdefault(p["id"], []).append(p["an"] / tot)
            if p.get("af") and r["af"]:
                disp.append(math.log10(p["af"] / r["af"]))
    model["population_an_share"] = {k: float(np.mean(v)) for k, v in shares.items()} or \
        DEFAULT_MODEL["population_an_share"]
    model["population_log10_dispersion"] = float(np.std(disp)) if len(disp) > 10 else 0.5
    fine = {}
    for c in ("P_LP", "B_LB"):
        sub = [r["classification"] for r in rows if r["coarse_class"] == c]
        opts = FINE_FOR_COARSE[c]
        cnt = {o: sum(1 for s in sub if s == o) for o in opts}
        tot = sum(cnt.values())
        fine[c] = {o: (cnt[o] / tot if tot else 1 / len(opts)) for o in opts}
    model["fine_split"] = fine
    vt = {}
    for r in rows:
        vt[r.get("variant_type", "SNV")] = vt.get(r.get("variant_type", "SNV"), 0) + 1
    model["variant_types"] = {k: v / len(rows) for k, v in vt.items() if k in ("SNV", "deletion", "insertion")} \
        or DEFAULT_MODEL["variant_types"]
    return model


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _sample_mixture(rng, comps, n):
    w = np.array([c[0] for c in comps], float)
    w = w / w.sum()
    idx = rng.choice(len(comps), size=n, p=w)
    mu = np.array([c[1] for c in comps])[idx]
    sd = np.array([c[2] for c in comps])[idx]
    return rng.normal(mu, sd)


def _random_alleles(rng, vtype):
    bases = np.array(list("ACGT"))
    ref = rng.choice(bases)
    if vtype == "SNV":
        alt = rng.choice(bases[bases != ref])
        return str(ref), str(alt)
    ins = "".join(rng.choice(bases, size=int(rng.integers(1, 4))))
    return (str(ref), str(ref) + ins) if vtype == "insertion" else (str(ref) + ins, str(ref))


def generate(params: SyntheticParams, model: dict, job_id: str) -> list[dict]:
    params.validate()
    rng = np.random.default_rng(params.seed)
    n = params.n_records
    weights = params.class_distribution or model["class_weights"]
    cls_names = [c for c in CLASSES if weights.get(c, 0) > 0]
    p = np.array([weights[c] for c in cls_names], float)
    classes = rng.choice(cls_names, size=n, p=p / p.sum())

    # injected scenarios (ground-truth labels recorded in qc_flags)
    scenario = np.array([""] * n, dtype=object)
    order = rng.permutation(n)
    n_conf = int(round(params.conflicting_rate * n))
    n_unusual = int(round(params.unusual_rate * n))
    scenario[order[:n_conf]] = "conflict"
    scenario[order[n_conf:n_conf + n_unusual]] = "unusual"
    classes[scenario == "conflict"] = "CONFLICTING"

    log_af = np.empty(n)
    for c in CLASSES:
        m = classes == c
        if m.any():
            log_af[m] = _sample_mixture(rng, model["log10_af"][c], int(m.sum()))
    unusual_idx = np.where(scenario == "unusual")[0]
    for j, i in enumerate(unusual_idx):
        if j % 2 == 0:  # frequent pathogenic
            classes[i] = "P_LP"
            log_af[i] = rng.uniform(-2.0, -1.0)
        else:           # very rare benign
            classes[i] = "B_LB"
            log_af[i] = rng.uniform(-6.5, -5.3)
    log_af = np.clip(log_af, -7.0, -0.05)

    an_cfg = model["log10_an"]
    log_an = np.clip(rng.normal(an_cfg["mean"], an_cfg["sd"], n), an_cfg["min"], an_cfg["max"])
    total_an = (np.round(10 ** log_an / 2) * 2).astype(int)

    pops = [pp for pp in params.populations if pp in model["population_an_share"]] or params.populations
    base_share = np.array([model["population_an_share"].get(pp, 1 / len(pops)) for pp in pops], float)
    base_share = base_share / base_share.sum()
    disp = model.get("population_log10_dispersion", 0.5)
    vtypes = list(model["variant_types"].keys())
    vprobs = np.array(list(model["variant_types"].values()), float)

    records = []
    for i in range(n):
        shares = rng.dirichlet(base_share * 300 + 1e-3)
        pop_an = np.maximum((np.round(shares * total_an[i] / 2) * 2).astype(int), 0)
        pop_af = np.clip(10 ** (log_af[i] + rng.normal(0, disp, len(pops))), 0, 1)
        pop_ac = rng.binomial(pop_an, pop_af)
        if pop_ac.sum() == 0:  # a variant listed in a frequency database has AC ≥ 1
            k = int(rng.choice(len(pops), p=shares / shares.sum()))
            pop_ac[k] = 1 if pop_an[k] > 0 else 0
        ac, an = int(pop_ac.sum()), int(pop_an.sum())
        populations = [{"id": pp, "label": POPULATION_LABELS.get(pp, pp), "ac": int(a), "an": int(b),
                        "homozygote_count": 0, "af": (int(a) / int(b)) if b > 0 else None}
                       for pp, a, b in zip(pops, pop_ac, pop_an)]
        coarse = str(classes[i])
        if coarse in model.get("fine_split", {}):
            split = model["fine_split"][coarse]
            fine = str(rng.choice(list(split.keys()), p=np.array(list(split.values())) / sum(split.values())))
        else:
            fine = FINE_FOR_COARSE[coarse][0]
        vtype = str(rng.choice(vtypes, p=vprobs / vprobs.sum()))
        ref, alt = _random_alleles(rng, vtype)
        qc = ["simulated_record"]
        if scenario[i] == "conflict":
            qc.append("simulated_conflict")
        if scenario[i] == "unusual":
            qc.append("simulated_unusual_frequency")
        rec = {
            "provenance": "SYNTHETIC", "vcf_key": f"SYN-{job_id}-{i + 1:06d}", "gene_symbol": "SYNTHETIC",
            "chrom": "SYN", "pos": i + 1, "ref": ref, "alt": alt, "variant_type": vtype,
            "in_gnomad": True, "in_clinvar": True, "ac": ac, "an": an, "af": ac / an if an else None,
            "populations": populations, "homozygote_count": 0,
            "classification": fine, "coarse_class": coarse,
            "clinical_significance": f"{FINE_LABELS[fine]} (simulated)",
            "review_status": None, "gold_stars": None, "conditions": None,
            "match_status": "synthetic", "match_method": "generated", "qc_flags": qc,
        }
        eligible = [pp for pp in populations if pp["id"] not in {"ami", "asj", "fin", "mid", "remaining"}
                    and pp["af"] and pp["ac"] > 0]
        top = max(eligible, key=lambda x: x["af"]) if eligible else None
        rec["popmax_af"], rec["popmax_population"] = (top["af"], top["id"]) if top else (None, None)
        records.append(rec)

    # missingness – applied last so it never breaks AC/AN consistency of kept values
    n_missing = int(round(params.missing_rate * n))
    for i in rng.choice(n, size=n_missing, replace=False) if n_missing else []:
        r = records[int(i)]
        what = rng.choice(["frequency", "populations", "classification"])
        if what == "frequency":
            r.update(ac=None, an=None, af=None, popmax_af=None, popmax_population=None)
            r["qc_flags"] += ["simulated_missing_frequency", "missing_ac_an"]
        elif what == "populations":
            r["populations"] = []
            r["qc_flags"].append("simulated_missing_populations")
        else:
            r.update(classification="not_provided", coarse_class="OTHER",
                     clinical_significance="Not provided (simulated)")
            r["qc_flags"].append("simulated_missing_classification")
    return records


# ---------------------------------------------------------------------------
# Real vs synthetic comparison
# ---------------------------------------------------------------------------
def compare(real_rows: list[dict], synth_rows: list[dict]) -> dict:
    def usable(rows, real):
        return [r for r in rows if (r.get("af") or 0) > 0 and r.get("coarse_class") in CLASSES and
                (r.get("match_status") in ("exact", "normalized") if real else True)]

    real = usable(real_rows, True)
    syn = usable(synth_rows, False)
    edges = np.arange(-7, 0.25, 0.25)
    out = {"edges": edges.tolist(), "classes": {}, "class_proportions": {}}
    for c in CLASSES:
        a = np.log10([r["af"] for r in real if r["coarse_class"] == c]) if real else np.array([])
        b = np.log10([r["af"] for r in syn if r["coarse_class"] == c]) if syn else np.array([])
        entry = {"n_real": int(a.size), "n_synthetic": int(b.size),
                 "real_hist": np.histogram(np.clip(a, -7, 0), edges)[0].tolist() if a.size else [],
                 "synthetic_hist": np.histogram(np.clip(b, -7, 0), edges)[0].tolist() if b.size else [],
                 "real_median_log10": float(np.median(a)) if a.size else None,
                 "synthetic_median_log10": float(np.median(b)) if b.size else None}
        if a.size >= 5 and b.size >= 5:
            ks = stats.ks_2samp(a, b)
            entry["ks"] = {"statistic": float(ks.statistic), "p_value": float(ks.pvalue)}
        out["classes"][c] = entry
        out["class_proportions"][c] = {
            "real": sum(1 for r in real if r["coarse_class"] == c) / len(real) if real else None,
            "synthetic": sum(1 for r in syn if r["coarse_class"] == c) / len(syn) if syn else None}
    tv = [abs((v["real"] or 0) - (v["synthetic"] or 0)) for v in out["class_proportions"].values()]
    out["class_total_variation_distance"] = 0.5 * sum(tv) if real and syn else None
    out["explanation"] = ("The two-sample Kolmogorov–Smirnov statistic (0–1) is the largest gap between the real "
                          "and synthetic cumulative distributions of log10 AF; small values mean the synthetic "
                          "generator reproduces the real shape. Total variation distance compares class mixes.")
    return out


def params_to_dict(p: SyntheticParams) -> dict:
    return asdict(p)

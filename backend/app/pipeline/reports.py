"""Stage 10 – report generation (PDF via ReportLab, charts via Matplotlib/Seaborn, CSV via pandas)."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.pipeline.preprocessing import COARSE_LABELS, FINE_LABELS  # noqa: E402

NAVY = colors.HexColor("#0b1b33")
TEAL = colors.HexColor("#0f8b8d")
PALETTE = {"P_LP": "#d1495b", "VUS": "#edae49", "B_LB": "#00798c", "CONFLICTING": "#8e6bbf",
           "OTHER": "#8a8f98", "NOT_IN_CLINVAR": "#4b5563"}

SHORT_LABELS = {"P_LP": "P/LP", "VUS": "VUS", "B_LB": "B/LB", "CONFLICTING": "Conflicting"}

CITATIONS = [
    "Chen S, et al. A genomic mutational constraint map using variation in 76,156 human genomes. Nature 625, "
    "92–100 (2024). gnomAD: https://gnomad.broadinstitute.org",
    "Karczewski KJ, et al. The mutational constraint spectrum quantified from variation in 141,456 humans. "
    "Nature 581, 434–443 (2020).",
    "Landrum MJ, et al. ClinVar: improvements to accessing data. Nucleic Acids Res 48, D835–D844 (2020). "
    "https://www.ncbi.nlm.nih.gov/clinvar/",
    "Richards S, et al. Standards and guidelines for the interpretation of sequence variants (ACMG/AMP). "
    "Genet Med 17, 405–424 (2015).",
    "Benjamini Y, Hochberg Y. Controlling the false discovery rate. J R Stat Soc B 57, 289–300 (1995).",
    "Liu FT, Ting KM, Zhou ZH. Isolation Forest. ICDM 2008.",
    "Virtanen P, et al. SciPy 1.0. Nat Methods 17, 261–272 (2020); Pedregosa F, et al. Scikit-learn. JMLR 12 (2011).",
]


def _fig_to_image(fig, width_cm=16):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    w, h = fig.get_size_inches()
    return Image(buf, width=width_cm * cm, height=width_cm * cm * h / w)


def _style():
    sns.set_theme(style="whitegrid", context="paper")
    plt.rcParams.update({"axes.edgecolor": "#cbd5e1", "font.size": 8})


def chart_classification(counts: dict):
    _style()
    items = sorted(counts.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.barh([FINE_LABELS.get(k, k) for k, _ in items][::-1], [v for _, v in items][::-1], color="#0f8b8d")
    ax.set_xlabel("ClinVar records")
    ax.set_title("Clinical classification distribution (REAL data)")
    return _fig_to_image(fig)


def chart_af_box(box: dict):
    _style()
    data, labels, cols = [], [], []
    for k in ("P_LP", "VUS", "B_LB", "CONFLICTING"):
        v = [x for x in box.get(k, []) if x and x > 0]
        if v:
            data.append(np.log10(v))
            labels.append(f"{SHORT_LABELS[k]}\n(n={len(v)})")
            cols.append(PALETTE[k])
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(7, 3.2))
    bp = ax.boxplot(data, patch_artist=True, showfliers=True, flierprops={"markersize": 2})
    for patch, c in zip(bp["boxes"], cols):
        patch.set_facecolor(c)
        patch.set_alpha(0.75)
    ax.set_xticks(range(1, len(labels) + 1), labels)
    ax.set_ylabel("log10(allele frequency)")
    ax.set_title("Allele frequency by classification (matched variants, REAL data)")
    return _fig_to_image(fig)


def chart_populations(pops: dict):
    groups = pops.get("groups") or []
    if not groups:
        return None
    _style()
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ids = [g["id"] for g in groups]
    ax.bar(ids, [g["variants_observed"] for g in groups], color="#3b6ea5")
    ax.set_ylabel("variants with AC > 0")
    ax.set_title("Variants observed per gnomAD genetic-ancestry group")
    return _fig_to_image(fig)


def chart_constraint(constraint: dict):
    rows = constraint.get("observed_expected") or []
    if not rows:
        return None
    _style()
    fig, ax = plt.subplots(figsize=(7, 2.4))
    for i, r in enumerate(rows):
        if r["oe"] is None:
            continue
        lo, hi = r.get("oe_lower") or r["oe"], r.get("oe_upper") or r["oe"]
        ax.errorbar(r["oe"], i, xerr=[[r["oe"] - lo], [hi - r["oe"]]], fmt="o", color="#0f8b8d", capsize=4)
    ax.axvline(1, color="#94a3b8", ls="--", lw=1)
    ax.set_yticks(range(len(rows)), [r["class"].upper() for r in rows])
    ax.set_xlabel("observed / expected (90% CI)")
    ax.set_title("gnomAD constraint: observed vs expected")
    return _fig_to_image(fig)


def chart_anomalies(summary: dict):
    cats = summary.get("by_category") or {}
    if not cats:
        return None
    _style()
    items = sorted(cats.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(7, 2.8))
    ax.barh([k.replace("_", " ") for k, _ in items], [v for _, v in items], color="#8e6bbf")
    ax.set_xlabel("flags")
    ax.set_title("Anomaly screening flags by category (for review, not verdicts)")
    return _fig_to_image(fig)


def _table(data, col_widths=None, font=7):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), font), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f1ea")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _fmt(v, nd=3):
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:.2e}" if (abs(v) < 1e-3 and v != 0) else f"{v:.{nd}g}"
    return str(v)


def build_pdf(path: Path, analysis: dict, datasets: list[dict], flags: list[dict]) -> Path:
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], textColor=NAVY, fontSize=22)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=TEAL, spaceBefore=10)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=10)
    warn = ParagraphStyle("w", parent=body, textColor=colors.HexColor("#9a3412"), alignment=TA_CENTER)
    res = analysis["results"]
    stats = res["statistics"]
    story = [
        Paragraph("GeneLens Research Report", h1),
        Paragraph(f"Genetic Variant Intelligence Platform · Gene <b>{analysis['gene_symbol']}</b> · "
                  f"Analysis {analysis['id']}", body),
        Paragraph(f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. All records in this report are "
                  "<b>REAL</b> (retrieved from public databases) unless explicitly marked SYNTHETIC.", body),
        Spacer(1, 6),
        Paragraph("Research use only – not for diagnosis or clinical decision-making.", warn),
        Paragraph("1. Dataset information", h2),
    ]
    ds_rows = [["Source", "Dataset / release", "Genome", "Access", "Records", "Retrieved"]]
    for d in datasets:
        ds_rows.append([d["source"], Paragraph(d.get("release") or d["dataset"], small), d.get("reference_genome"),
                        d["access_mode"], f"{d['record_count']:,}", str(d["retrieved_at"])[:19]])
    story.append(_table(ds_rows, [2.6 * cm, 5.2 * cm, 1.6 * cm, 2.4 * cm, 1.6 * cm, 3.2 * cm]))
    g = res.get("gene", {})
    story.append(Paragraph(f"Gene {g.get('symbol')} ({g.get('gene_id')}), chr{g.get('chrom')}:{g.get('start'):,}-"
                           f"{g.get('stop'):,}; canonical transcript {g.get('canonical_transcript_id')}.", body)
                 if g.get("start") else Spacer(1, 1))

    story.append(Paragraph("2. Methodology", h2))
    for line in [
        "Pipeline: collection → validation → preprocessing → normalisation → gnomAD–ClinVar matching → "
        "statistics → anomaly screening → visualisation → interpretation → report.",
        "AF = AC/AN computed from gnomAD joint (exome+genome) counts; records with AN = 0 or AC > AN are flagged.",
        "Matching uses exact chrom-pos-ref-alt keys, then minimal (trimmed) allele representations for indels; "
        "records are never joined by gene name. Haplotype/CNV ClinVar records are reported as unmatchable.",
        "Group comparisons use Mann–Whitney U on log10 AF (rank-biserial effect size, bootstrap 95% CI of the median "
        "difference), chi-square and Fisher's exact tests, and Spearman correlation. p-values are corrected with "
        "Benjamini–Hochberg (FDR) and Bonferroni.",
        "Anomaly screening combines configurable rules, robust (median/MAD) outliers and an Isolation Forest.",
    ]:
        story.append(Paragraph("• " + line, body))

    story.append(Paragraph("3. Dataset statistics & matching", h2))
    m = res["matching"]
    mrows = [["Metric", "Value"], [f"{m.get('frequency_source') or 'Frequency-dataset'} records", f"{m['gnomad_records']:,}"],
             ["ClinVar records", f"{m['clinvar_records']:,}"],
             ["ClinVar records with allele coordinates", f"{m['clinvar_with_allele_coordinates']:,}"],
             ["Matched alleles", f"{m['matched_variants']:,}"],
             ["ClinVar match rate", f"{(m['clinvar_match_rate'] or 0):.1%}"]]
    for k, v in m["status_counts"].items():
        mrows.append([f"  status: {k}", f"{v:,}"])
    story.append(_table(mrows, [9 * cm, 6 * cm]))

    story.append(Paragraph("4. Variant classification analysis", h2))
    if stats.get("classification_counts"):
        story.append(chart_classification(stats["classification_counts"]))
    img = chart_af_box(stats.get("box_data", {}))
    if img:
        story.append(img)
    drows = [["Class", "n", "mean AF", "median AF", "SD", "Q1", "Q3", "min", "max"]]
    for k, d in stats["descriptive"].items():
        if d.get("n"):
            drows.append([COARSE_LABELS.get(k, k), d["n"]] + [_fmt(d.get(x)) for x in
                                                               ("mean", "median", "std", "q1", "q3", "min", "max")])
    story.append(_table(drows))

    story.append(Paragraph("5. Population frequency analysis", h2))
    img = chart_populations(res.get("populations", {}))
    if img:
        story.append(img)
    prow = [["Group", "Label", "Variants AC>0", "Median AN", "Missing"]]
    for gp in res.get("populations", {}).get("groups", []):
        prow.append([gp["id"], gp["label"], gp["variants_observed"], f"{gp['median_an']:,.0f}",
                     f"{(gp['missing_fraction'] or 0):.1%}"])
    story.append(_table(prow))
    story.append(Paragraph("Population groups are gnomAD genetic-ancestry labels for reference samples; they do "
                           "not indicate individual ancestry or disease risk.", small))

    story.append(Paragraph("6. Gene constraint findings", h2))
    c = res.get("constraint", {})
    img = chart_constraint(c)
    if img:
        story.append(img)
    for line in c.get("interpretation", []) or [c.get("message", "")]:
        story.append(Paragraph("• " + line, body))
    story.append(Paragraph(c.get("disclaimer", ""), small))

    story.append(PageBreak())
    story.append(Paragraph("7. Statistical results", h2))
    trows = [["Test", "Comparison", "n", "Statistic", "p", "p (BH)", "Effect size"]]
    for t in stats["tests"]:
        n = t.get("n")
        n_txt = ", ".join(f"{k}:{v}" for k, v in n.items()) if isinstance(n, dict) else _fmt(n)
        eff = t.get("effect_size") or {}
        trows.append([Paragraph(t["test"], small), Paragraph(t.get("comparison") or t.get("variables", ""), small),
                      Paragraph(n_txt, small), _fmt(t.get("statistic")) if t.get("ran") else "not run",
                      _fmt(t.get("p_value")), _fmt(t.get("p_adjusted_bh")),
                      Paragraph(f"{eff.get('name', '')} {_fmt(eff.get('value'))}" if eff else
                                (t.get("reason") or ""), small)])
    story.append(_table(trows, [3 * cm, 3.6 * cm, 2.4 * cm, 1.6 * cm, 1.6 * cm, 1.6 * cm, 3.2 * cm]))
    prop = stats.get("proportions", {}).get("pathogenic_fraction_of_clinvar", {})
    if prop.get("estimate") is not None:
        lo, hi = prop["ci95_wilson"]
        story.append(Paragraph(f"P/LP fraction of ClinVar records: {prop['estimate']:.1%} "
                               f"(95% Wilson CI {lo:.1%}–{hi:.1%}, n={prop['n']}).", body))

    story.append(Paragraph("8. Flagged variants (top 25 by priority)", h2))
    img = chart_anomalies(res.get("anomaly_summary", {}))
    if img:
        story.append(img)
    frows = [["Variant", "Category", "Kind", "Priority", "Explanation"]]
    for f in flags[:25]:
        frows.append([Paragraph(f["variant_key"], small), Paragraph(f["category"].replace("_", " "), small),
                      f["kind"].replace("_", " "), f["priority"], Paragraph(f["explanation"][:300], small)])
    story.append(_table(frows, [3.6 * cm, 2.6 * cm, 2.4 * cm, 1.4 * cm, 7 * cm]))

    interp = res.get("interpretation", {})
    story.append(Paragraph("9. Research interpretation", h2))
    for line in interp.get("findings", []):
        story.append(Paragraph("• " + line, body))
    story.append(Paragraph("10. Limitations", h2))
    for line in interp.get("limitations", []):
        story.append(Paragraph("• " + line, body))
    story.append(Paragraph("11. Data sources & citations", h2))
    for line in CITATIONS:
        story.append(Paragraph(line, small))
    story.append(KeepTogether([Paragraph("12. Medical and research disclaimer", h2),
                               Paragraph(interp.get("disclaimer", ""), body)]))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(1.5 * cm, 1 * cm, f"GeneLens · {analysis['gene_symbol']} · research use only")
        canvas.drawRightString(A4[0] - 1.5 * cm, 1 * cm, f"page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.6 * cm,
                            title=f"GeneLens report – {analysis['gene_symbol']}", author="GeneLens")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def build_csv_report(path: Path, analysis: dict, datasets: list[dict]) -> Path:
    """Flat CSV of all computed statistics, with provenance columns."""
    res = analysis["results"]
    rows = []
    for d in datasets:
        rows.append({"section": "dataset", "item": d["source"], "metric": "release", "value": d.get("release"),
                     "detail": f"{d['access_mode']}; retrieved {d['retrieved_at']}; n={d['record_count']}"})
    for k, v in res["matching"]["status_counts"].items():
        rows.append({"section": "matching", "item": k, "metric": "count", "value": v})
    rows.append({"section": "matching", "item": "clinvar_match_rate", "metric": "fraction",
                 "value": res["matching"]["clinvar_match_rate"]})
    for cls, d in res["statistics"]["descriptive"].items():
        for metric in ("n", "mean", "median", "std", "min", "max", "q1", "q3"):
            if d.get(metric) is not None:
                rows.append({"section": "descriptive_af", "item": cls, "metric": metric, "value": d[metric]})
    for t in res["statistics"]["tests"]:
        base = {"section": "test", "item": f"{t['test']} | {t.get('comparison') or t.get('variables')}"}
        if not t.get("ran"):
            rows.append({**base, "metric": "not_run", "value": None, "detail": t.get("reason")})
            continue
        for metric in ("statistic", "p_value", "p_adjusted_bh", "p_adjusted_bonferroni"):
            rows.append({**base, "metric": metric, "value": t.get(metric)})
        eff = t.get("effect_size") or {}
        rows.append({**base, "metric": f"effect:{eff.get('name')}", "value": eff.get("value")})
    for k, v in (res.get("anomaly_summary", {}).get("by_category") or {}).items():
        rows.append({"section": "anomalies", "item": k, "metric": "count", "value": v})
    for k, v in (res.get("constraint", {}).get("metrics") or {}).items():
        if not isinstance(v, list):
            rows.append({"section": "constraint", "item": k, "metric": "value", "value": v})
    df = pd.DataFrame(rows)
    df.insert(0, "provenance", "REAL")
    df.insert(0, "gene", analysis["gene_symbol"])
    df.insert(0, "analysis_id", analysis["id"])
    df.to_csv(path, index=False)
    return path

"""Stage 2 – data validation.

Checks are deliberately explicit so each failure can be shown to the user
as a QC flag rather than silently dropping the record.
"""
from __future__ import annotations

import math

AF_TOLERANCE = 1e-6  # absolute tolerance when comparing reported AF with AC/AN


def compute_af(ac, an) -> float | None:
    """AF = AC / AN, defined only when AN > 0 and 0 <= AC <= AN."""
    if ac is None or an is None:
        return None
    try:
        ac, an = int(ac), int(an)
    except (TypeError, ValueError):
        return None
    if an <= 0 or ac < 0 or ac > an:
        return None
    return ac / an


def check_counts(ac, an, af_reported=None) -> list[str]:
    """Return QC flag codes for an AC/AN/AF triple."""
    flags: list[str] = []
    if ac is None or an is None:
        flags.append("missing_ac_an")
        return flags
    if an == 0:
        flags.append("zero_an")
    if ac < 0 or an < 0:
        flags.append("negative_count")
    if an > 0 and ac > an:
        flags.append("ac_exceeds_an")
    if af_reported is not None and not (isinstance(af_reported, float) and math.isnan(af_reported)):
        expected = compute_af(ac, an)
        if expected is not None and abs(expected - af_reported) > max(AF_TOLERANCE, 1e-3 * expected):
            flags.append("af_inconsistent")
        if af_reported < 0 or af_reported > 1:
            flags.append("af_out_of_range")
    return flags


def validate_gnomad_payload(gene: dict) -> list[str]:
    """Structural validation of a gnomAD gene payload. Returns error strings."""
    errors = []
    if not isinstance(gene, dict):
        return ["gene payload is not an object"]
    if "variants" not in gene or not isinstance(gene["variants"], list):
        errors.append("gene payload has no variants list")
    for field in ("chrom", "start", "stop"):
        if gene.get(field) is None:
            errors.append(f"gene payload missing '{field}'")
    return errors


def validate_clinvar_record(rec: dict) -> list[str]:
    flags = []
    if not rec.get("clinvar_variation_id"):
        flags.append("missing_variation_id")
    if not rec.get("clinical_significance"):
        flags.append("missing_classification")
    if rec.get("coordinate_source") in ("missing", "location_only"):
        flags.append("missing_alleles")
    if rec.get("coordinate_source") == "multi_allele_record":
        flags.append("multi_allele_record")
    return flags

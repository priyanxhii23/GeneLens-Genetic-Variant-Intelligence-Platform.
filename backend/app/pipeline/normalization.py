"""Stage 4 – variant normalisation.

Two representations are produced for every variant:

* **VCF key** ``chrom-pos-ref-alt`` exactly as the source reports it
  (gnomAD and ClinVar's VCF columns are both left-aligned).
* **Minimal key** – the allele pair trimmed of shared suffix then shared
  prefix (empty alleles allowed), in 0-based interbase coordinates. This is
  the representation used to reconcile records whose anchor bases differ,
  e.g. ClinVar canonical SPDI (fully justified) vs gnomAD (left-aligned VCF).

Full left-alignment needs the reference genome sequence, which GeneLens does
not download. Both sources used here are already left-aligned/justified, so
trimming suffix-first yields the same leftmost minimal representation; this
assumption is documented in docs/methodology.md.
"""
from __future__ import annotations

import re

VALID_ALLELE = re.compile(r"^[ACGTN]*$")
VALID_CHROMS = {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}


def normalize_chrom(chrom) -> str | None:
    if chrom is None:
        return None
    c = str(chrom).strip().upper()
    if c.startswith("CHR"):
        c = c[3:]
    if c == "M":
        c = "MT"
    return c if c in VALID_CHROMS else None


def normalize_allele(allele) -> str | None:
    if allele is None:
        return None
    a = str(allele).strip().upper()
    if a in {"", "-", "."}:
        return ""
    return a if VALID_ALLELE.match(a) else None


def minimal_representation(pos: int, ref: str, alt: str) -> tuple[int, str, str]:
    """Return (start0, ref_min, alt_min) using suffix-then-prefix trimming.

    ``pos`` is 1-based (VCF). ``start0`` is the 0-based interbase start of the
    minimal allele pair. Examples::

        >>> minimal_representation(100, "A", "G")
        (99, 'A', 'G')
        >>> minimal_representation(100, "CTT", "CT")    # left-aligned deletion of T
        (100, 'T', '')
    """
    start0 = pos - 1
    while ref and alt and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    while ref and alt and ref[0] == alt[0]:
        ref, alt = ref[1:], alt[1:]
        start0 += 1
    return start0, ref, alt


def variant_type(ref: str | None, alt: str | None) -> str:
    if ref is None or alt is None:
        return "unknown"
    _, r, a = minimal_representation(1, ref, alt)
    if len(r) == 1 and len(a) == 1:
        return "SNV"
    if len(r) == len(a):
        return "MNV"
    if not r:
        return "insertion"
    if not a:
        return "deletion"
    return "complex"


def vcf_key(chrom, pos, ref, alt) -> str:
    return f"{chrom}-{pos}-{ref}-{alt}"


def minimal_key(chrom: str, pos: int, ref: str, alt: str) -> str:
    s, r, a = minimal_representation(pos, ref, alt)
    return f"{chrom}:{s}:{r or '-'}:{a or '-'}"


def normalize_record(rec: dict) -> dict:
    """Normalise coordinates in-place-copy; adds ``coords_valid`` + keys."""
    out = dict(rec)
    chrom = normalize_chrom(rec.get("chrom"))
    ref = normalize_allele(rec.get("ref"))
    alt = normalize_allele(rec.get("alt"))
    pos = rec.get("pos")
    try:
        pos = int(pos) if pos is not None else None
    except (TypeError, ValueError):
        pos = None
    valid = (chrom is not None and pos is not None and pos > 0 and ref is not None
             and alt is not None and (ref != "" or alt != "") and ref != alt)
    out.update(chrom=chrom, pos=pos, ref=ref, alt=alt, coords_valid=valid)
    if valid:
        out["vcf_key"] = vcf_key(chrom, pos, ref, alt)
        out["minimal_key"] = minimal_key(chrom, pos, ref, alt)
        out["variant_type"] = variant_type(ref, alt)
    else:
        out["vcf_key"] = out["minimal_key"] = None
        out["variant_type"] = "unknown"
    return out

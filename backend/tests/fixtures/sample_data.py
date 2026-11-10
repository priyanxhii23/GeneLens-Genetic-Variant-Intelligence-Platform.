"""Hand-built TEST FIXTURE data (not real records) exercising edge cases.

Reference context used for the indel case (chr1, 1-based):
    pos 200 = C, 201 = T, 202 = T, 203 = G   ->  deleting one T
    gnomAD (left-aligned VCF):     1-200-CT-C
    ClinVar canonical SPDI:        NC_000001.11:200:TT:T  (fully justified)
"""
from __future__ import annotations

import copy

import numpy as np


def _pop(id_, ac, an, hom=0):
    return {"id": id_, "ac": ac, "an": an, "homozygote_count": hom}


def _variant(vid, ac, an, pops=None, filters=None, exome=None):
    chrom, pos, ref, alt = vid.split("-")
    return {"variant_id": vid, "chrom": chrom, "pos": int(pos), "ref": ref, "alt": alt, "rsids": [],
            "consequence": "missense_variant", "hgvsc": None, "hgvsp": None, "lof": None, "flags": [],
            "exome": exome, "genome": None,
            "joint": {"ac": ac, "an": an, "homozygote_count": 0, "filters": filters or [],
                      "populations": pops or [_pop("nfe", ac, an)]}}


def gnomad_gene() -> dict:
    variants = [
        _variant("1-100-A-G", 10, 100_000, [_pop("afr", 8, 10_000), _pop("nfe", 2, 90_000), _pop("afr_XX", 4, 5000)],
                 exome={"ac": 10, "an": 100_000, "af": 1e-4, "homozygote_count": 0, "filters": [], "populations": []}),
        _variant("1-200-CT-C", 3, 100_000),          # matches SPDI via minimal representation
        _variant("1-300-G-A", 1, 100_000),           # gnomAD only
        _variant("1-400-C-T", 20_000, 100_000),      # common benign
        _variant("1-500-T-C", 0, 0),                 # AN = 0 -> incomplete
        _variant("1-600-A-C", 600, 100_000),         # discordant duplicate ClinVar records -> ambiguous
        _variant("1-700-G-T", 5, 100_000, filters=["AS_VQSR"]),
    ]
    # extra matched SNVs so that statistical tests have n >= 5 per group
    rng = np.random.default_rng(1)
    for i in range(12):
        variants.append(_variant(f"1-{1000 + i}-A-G", int(rng.integers(1, 20)), 100_000))
        variants.append(_variant(f"1-{2000 + i}-C-T", int(rng.integers(50, 5000)), 100_000))
    return {"gene_id": "ENSGTEST", "symbol": "TESTG", "name": "test gene", "chrom": "1", "start": 1, "stop": 3000,
            "strand": "+", "canonical_transcript_id": "ENSTTEST", "mane_select_transcript": None,
            "gnomad_constraint": {"pli": 0.95, "oe_lof_upper": 0.3, "oe_lof": 0.2, "oe_lof_lower": 0.1,
                                  "exp_lof": 30.0, "obs_lof": 6, "mis_z": 3.5, "oe_mis": 0.7, "exp_mis": 300.0,
                                  "obs_mis": 210, "oe_syn": 1.0, "exp_syn": 100.0, "obs_syn": 100, "flags": []},
            "variants": copy.deepcopy(variants)}


def _cv(uid, spdi, sig, review="criteria provided, single submitter", multi=False):
    vset = [{"measure_id": f"A{uid}", "canonical_spdi": spdi, "variation_xrefs": [], "variation_loc": []}]
    if multi:
        vset.append({"measure_id": f"B{uid}", "canonical_spdi": "NC_000001.11:899:A:T", "variation_loc": []})
    return {"uid": str(uid), "obj_type": "Haplotype" if multi else "single nucleotide variant",
            "title": f"test variant {uid}", "variation_set": vset, "genes": [{"symbol": "TESTG"}],
            "germline_classification": {"description": sig, "review_status": review,
                                        "last_evaluated": "2024/01/01 00:00",
                                        "trait_set": [{"trait_name": "Test condition"}]},
            "supporting_submissions": {"scv": ["SCV1"]}}


def clinvar_raw() -> list[dict]:
    recs = [
        _cv(1, "NC_000001.11:99:A:G", "Pathogenic", "reviewed by expert panel"),
        _cv(2, "NC_000001.11:200:TT:T", "Likely pathogenic"),
        _cv(3, "NC_000001.11:799:G:C", "Uncertain significance"),            # ClinVar only
        _cv(4, "NC_000001.11:399:C:T", "Benign", "criteria provided, multiple submitters, no conflicts"),
        _cv(5, "NC_000001.11:99:A:G", "Pathogenic; other", multi=True),     # haplotype -> unmatchable
        _cv(6, "NC_000001.11:599:A:C", "Pathogenic"),
        _cv(7, "NC_000001.11:599:A:C", "Benign"),                            # discordant duplicate
        _cv(8, "NC_000001.11:699:G:T", "Conflicting classifications of pathogenicity",
            "criteria provided, conflicting classifications"),
    ]
    for i in range(12):
        recs.append(_cv(100 + i, f"NC_000001.11:{999 + i}:A:G", "Pathogenic" if i % 2 else "Likely pathogenic"))
        recs.append(_cv(200 + i, f"NC_000001.11:{1999 + i}:C:T", "Benign" if i % 2 else "Likely benign"))
    return recs


def clinvar_records() -> list[dict]:
    from app.services.clinvar_client import parse_esummary_record

    return [parse_esummary_record(r) for r in clinvar_raw()]

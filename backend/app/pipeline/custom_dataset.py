"""Custom Dataset Lab – inspect, map, validate and analyse researcher-uploaded variant files.

Supported formats: CSV, TSV, TXT (delimiter sniffed), VCF, VCF.GZ, JSON.

Integrity rules (enforced here, tested in ``tests/test_custom_dataset.py``):
* The genome assembly is **never guessed** from coordinates. It is taken from
  explicit file metadata (VCF ``##reference``/``##contig assembly``, or an
  ``assembly`` column) or from the user; otherwise it stays ``unknown``.
* Missing values stay missing – never zero. AF is only computed from AC/AN when
  both are present; a reported AF is checked against AC/AN when all exist.
* Classifications present in the file are never overwritten. ClinVar is used
  as a *retrieved annotation* only when the file has no classification column,
  and only when the assembly is known.
* Every record is stored with ``provenance = CUSTOM`` and the dataset id.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from app.pipeline.normalization import normalize_record
from app.pipeline.preprocessing import GRPMAX_EXCLUDED, POPULATION_LABELS, gold_stars, normalize_classification
from app.pipeline.validation import check_counts, compute_af

ALLOWED_EXT = {".csv": "csv", ".tsv": "tsv", ".txt": "txt", ".vcf": "vcf", ".json": "json"}
PREVIEW_ROWS = 20
FIELDS = ["chrom", "pos", "ref", "alt", "variant_id", "rsid", "gene", "af", "ac", "an", "clinical_significance",
          "review_status", "assembly", "homozygote_count"]
FIELD_LABELS = {
    "chrom": "Chromosome", "pos": "Position", "ref": "Reference allele", "alt": "Alternate allele",
    "variant_id": "Variant identifier (chrom-pos-ref-alt)", "rsid": "dbSNP rsID", "gene": "Gene symbol",
    "af": "Allele frequency", "ac": "Allele count", "an": "Allele number",
    "clinical_significance": "Clinical classification", "review_status": "Review status",
    "assembly": "Genome assembly column", "homozygote_count": "Homozygote count",
}
SYNONYMS = {
    "chrom": ["chrom", "#chrom", "chr", "chromosome", "seqname", "contig", "chrom_id", "chromosomes"],
    "pos": ["pos", "position", "start", "bp", "positionvcf", "pos_vcf", "location", "coordinate"],
    "ref": ["ref", "reference", "ref_allele", "referenceallele", "referencealleleVCF".lower(), "reference_allele"],
    "alt": ["alt", "alternate", "alt_allele", "alternateallele", "alternatealleleVCF".lower(), "alternate_allele", "allele"],
    "variant_id": ["variant_id", "variant", "variantid", "var_id", "gnomad_id", "key", "variant_key"],
    "rsid": ["rsid", "rs", "rs_id", "dbsnp", "snp", "id", "rs#", "rs# (dbsnp)", "snp_id"],
    "gene": ["gene", "gene_symbol", "symbol", "genesymbol", "gene_name", "hgnc_symbol", "geneinfo"],
    "af": ["af", "allele_frequency", "freq", "frequency", "maf", "gnomad_af", "af_total", "global_af", "alt_freq"],
    "ac": ["ac", "allele_count", "alt_count", "ac_total", "count"],
    "an": ["an", "allele_number", "total_alleles", "an_total", "chromosomes"],
    "clinical_significance": ["clinical_significance", "clinicalsignificance", "clnsig", "clinvar", "classification",
                              "significance", "clin_sig", "pathogenicity", "acmg_class", "interpretation"],
    "review_status": ["review_status", "reviewstatus", "clnrevstat", "review"],
    "assembly": ["assembly", "genome", "genome_build", "build", "reference_genome", "grch"],
    "homozygote_count": ["homozygote_count", "nhomalt", "hom", "homozygotes", "ac_hom"],
}
POP_IDS = {"afr", "amr", "asj", "eas", "fin", "mid", "nfe", "sas", "remaining", "eur", "oth", "ami"}
POP_RE = [re.compile(r"^(af|ac|an)[_\-]([a-z]{3,9})$"), re.compile(r"^([a-z]{3,9})[_\-](af|ac|an)$")]
VARIANT_ID_RE = re.compile(r"^(?:chr)?([0-9]{1,2}|X|Y|MT|M)[-:_](\d+)[-:_]([ACGTN]+)[-:_>/]([ACGTN]+)$", re.I)


class DatasetError(ValueError):
    """User-facing problem with an uploaded file."""


# --------------------------------------------------------------------------- format
def detect_format(filename: str, head: bytes) -> str:
    name = filename.lower()
    if name.endswith(".vcf.gz") or name.endswith(".vcf.bgz"):
        if head[:2] != b"\x1f\x8b":
            raise DatasetError("The file is named .vcf.gz but is not gzip-compressed.")
        text = gzip.GzipFile(fileobj=io.BytesIO(head)).read(512) if len(head) >= 2 else b""
        if not text.startswith(b"##fileformat=VCF"):
            raise DatasetError("The compressed file does not start with a VCF header (##fileformat=VCF).")
        return "vcf.gz"
    ext = Path(name).suffix
    if ext not in ALLOWED_EXT:
        raise DatasetError(f"Unsupported file type '{ext or name}'. Upload CSV, TSV, TXT, VCF, VCF.GZ or JSON.")
    if b"\x00" in head[:4096]:
        raise DatasetError("The file appears to be binary, not text. Upload CSV, TSV, TXT, VCF, VCF.GZ or JSON.")
    fmt = ALLOWED_EXT[ext]
    try:
        sample = head[:8192].decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetError("The file is not valid UTF-8 text.") from exc
    if fmt == "vcf" and not sample.startswith("##fileformat=VCF"):
        raise DatasetError("A VCF file must start with the header line ##fileformat=VCF.")
    if fmt == "json" and sample.lstrip()[:1] not in ("[", "{"):
        raise DatasetError("A JSON dataset must be a list of records or an object containing one.")
    return fmt


def _open_text(path: Path, fmt: str):
    return gzip.open(path, "rt", encoding="utf-8", errors="replace") if fmt == "vcf.gz" else \
        open(path, "r", encoding="utf-8-sig", errors="replace")


# --------------------------------------------------------------------------- readers
def _vcf_header(fh) -> tuple[list[str], dict]:
    meta: dict = {"info": {}, "assembly_evidence": []}
    for line in fh:
        if line.startswith("##"):
            low = line.lower()
            if low.startswith("##reference=") or ("##contig" in low and "assembly=" in low):
                meta["assembly_evidence"].append(line.strip()[:200])
            m = re.match(r'##INFO=<ID=([^,]+),Number=([^,]+),Type=([^,]+)', line)
            if m:
                meta["info"][m.group(1)] = {"number": m.group(2), "type": m.group(3)}
        elif line.startswith("#CHROM"):
            return line.lstrip("#").rstrip("\n").split("\t"), meta
    raise DatasetError("The VCF has no #CHROM header line.")


def _vcf_records(fh, info_meta: dict, limit: int | None = None):
    """Yield one dict per ALT allele with INFO fields expanded (Number=A values split per allele)."""
    n = 0
    for line in fh:
        if not line.strip() or line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        if len(f) < 5:
            continue
        info = {}
        if len(f) > 7 and f[7] not in (".", ""):
            for kv in f[7].split(";"):
                k, _, v = kv.partition("=")
                info[k] = v if _ else "true"
        alts = f[4].split(",")
        for i, alt in enumerate(alts):
            rec = {"CHROM": f[0], "POS": f[1], "ID": f[2], "REF": f[3], "ALT": alt,
                   "FILTER": f[6] if len(f) > 6 else ""}
            for k, v in info.items():
                parts = v.split(",")
                per_allele = info_meta.get(k, {}).get("number") == "A" or (len(alts) > 1 and len(parts) == len(alts))
                rec[k] = parts[i] if per_allele and i < len(parts) else v
            yield rec
            n += 1
            if limit and n >= limit:
                return


def _sniff_sep(sample: str, fmt: str) -> str:
    if fmt == "tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(sample.split("\n", 20)[0] + "\n" + "\n".join(sample.split("\n")[1:6]),
                                   delimiters=",\t;|").delimiter
    except csv.Error:
        return "\t" if sample.count("\t") > sample.count(",") else ","


def iter_records(path: Path, fmt: str, chunksize: int = 50_000):
    """Yield pandas DataFrames (all string columns) in chunks, plus header metadata once via .attrs."""
    if fmt in ("vcf", "vcf.gz"):
        with _open_text(path, fmt) as fh:
            _, meta = _vcf_header(fh)
            batch = []
            for rec in _vcf_records(fh, meta["info"]):
                batch.append(rec)
                if len(batch) >= chunksize:
                    yield pd.DataFrame(batch, dtype=str)
                    batch = []
            if batch:
                yield pd.DataFrame(batch, dtype=str)
        return
    if fmt == "json":
        with open(path, "r", encoding="utf-8-sig") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"Invalid JSON: {exc.msg} (line {exc.lineno}).") from exc
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), None)
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise DatasetError("The JSON must contain a list of variant records (objects).")
        for i in range(0, len(data), chunksize):
            yield pd.DataFrame(data[i:i + chunksize]).astype("string").astype(object)
        return
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(16384)
    sep = _sniff_sep(sample, fmt)
    try:
        for chunk in pd.read_csv(path, sep=sep, dtype=str, chunksize=chunksize, comment=None,
                                 keep_default_na=False, na_values=[""], skip_blank_lines=True,
                                 encoding="utf-8-sig", on_bad_lines="warn"):
            yield chunk
    except pd.errors.ParserError as exc:
        raise DatasetError(f"Could not parse the table: {str(exc).splitlines()[0]}") from exc


# --------------------------------------------------------------------------- inspection
def suggest_mapping(columns: list[str]) -> dict[str, str | None]:
    norm = {c: re.sub(r"\s+", "_", c.strip().lower()) for c in columns}
    used: set[str] = set()
    out: dict[str, str | None] = {}
    for field in FIELDS:
        hit = None
        for syn in SYNONYMS[field]:
            hit = next((c for c, n in norm.items() if n == syn and c not in used), None)
            if hit:
                break
        out[field] = hit
        if hit:
            used.add(hit)
    return out


def population_columns(columns: list[str]) -> dict[str, dict[str, str]]:
    pops: dict[str, dict[str, str]] = {}
    for c in columns:
        n = c.strip().lower()
        for rx in POP_RE:
            m = rx.match(n)
            if not m:
                continue
            a, b = m.groups()
            metric, pop = (a, b) if a in ("af", "ac", "an") else (b, a)
            if pop in POP_IDS:
                pops.setdefault(pop, {})[metric] = c
            break
    return pops


def detect_assembly(path: Path, fmt: str, columns: list[str]) -> dict:
    """Assembly only from explicit metadata. Coordinates alone never decide it."""
    evidence: list[str] = []
    if fmt in ("vcf", "vcf.gz"):
        with _open_text(path, fmt) as fh:
            _, meta = _vcf_header(fh)
        evidence = meta["assembly_evidence"]
    text = " ".join(evidence).lower()
    hits = {"GRCh38": any(k in text for k in ("grch38", "hg38", "b38")),
            "GRCh37": any(k in text for k in ("grch37", "hg19", "b37", "hs37d5"))}
    if hits["GRCh38"] != hits["GRCh37"]:
        val = "GRCh38" if hits["GRCh38"] else "GRCh37"
        return {"value": val, "source": "file_header", "evidence": evidence[:3]}
    note = ("Header mentions both assemblies – please choose." if all(hits.values()) else
            "No assembly information in the file. GeneLens will not infer it from coordinates – please choose.")
    return {"value": "unknown", "source": None, "evidence": evidence[:3], "note": note}


def inspect(path: Path, fmt: str) -> dict:
    """Preview, column detection, row count, missing values and duplicates (streamed)."""
    preview: pd.DataFrame | None = None
    total = 0
    missing: Counter = Counter()
    columns: list[str] = []
    for chunk in iter_records(path, fmt):
        if preview is None:
            preview = chunk.head(PREVIEW_ROWS)
            columns = [str(c) for c in chunk.columns]
        total += len(chunk)
        for c in chunk.columns:
            col = chunk[c]
            missing[str(c)] += int((col.isna() | col.astype(str).str.strip().isin(["", ".", "NA", "nan", "None"])).sum())
    if preview is None or total == 0:
        raise DatasetError("The file contains no records.")
    mapping = suggest_mapping(columns)
    pops = population_columns(columns)
    asm = detect_assembly(path, fmt, columns)
    if mapping.get("assembly") and asm["value"] == "unknown":
        asm["note"] = f"An assembly column '{mapping['assembly']}' exists; its values are checked during processing."
    issues = []
    if not (mapping["chrom"] and mapping["pos"] and mapping["ref"] and mapping["alt"]) and not mapping["variant_id"]:
        issues.append("No complete set of coordinate columns (chromosome, position, reference, alternate) or variant "
                      "identifier was recognised – please map them manually.")
    return {
        "columns": columns, "row_count": total,
        "preview": json.loads(preview.astype(object).where(pd.notna(preview), None).to_json(orient="records")),
        "suggested_mapping": mapping, "field_labels": FIELD_LABELS, "population_columns": pops,
        "missing_by_column": {c: missing[c] for c in columns}, "assembly": asm, "issues": issues,
    }


# --------------------------------------------------------------------------- processing
def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    s = str(v).strip()
    return None if s in ("", ".", "NA", "N/A", "nan", "None", "null", "-") else s


def _num(v, as_int=False):
    """Parse a number; None when missing, the string "invalid" when unparseable."""
    s = _clean(v)
    if s is None:
        return None
    try:
        x = float(s)
    except ValueError:
        return "invalid"
    if np.isnan(x):
        return None
    if as_int:
        return int(x) if x.is_integer() else "invalid"
    return x


def build_rows(path: Path, fmt: str, mapping: dict, pops: dict, assembly: str) -> tuple[list[dict], dict]:
    """Turn the file into normalised GeneLens rows + quality statistics. Nothing is imputed."""
    rows: list[dict] = []
    stats = {"total": 0, "valid": 0, "invalid": 0, "duplicates": 0, "missing": Counter(), "invalid_values": Counter(),
             "assembly_column_values": Counter()}
    seen: dict[str, int] = {}
    g = lambda r, f: r.get(mapping[f]) if mapping.get(f) else None  # noqa: E731
    for chunk in iter_records(path, fmt):
        for rec in chunk.to_dict("records"):
            stats["total"] += 1
            i = stats["total"]
            chrom, pos, ref, alt = (_clean(g(rec, f)) for f in ("chrom", "pos", "ref", "alt"))
            vid = _clean(g(rec, "variant_id"))
            if (not chrom or not pos or not ref or not alt) and vid and (m := VARIANT_ID_RE.match(vid)):
                chrom, pos, ref, alt = m.groups()
            for f, val in (("chrom", chrom), ("pos", pos), ("ref", ref), ("alt", alt)):
                if val is None:
                    stats["missing"][f] += 1
            if mapping.get("assembly") and _clean(g(rec, "assembly")):
                stats["assembly_column_values"][_clean(g(rec, "assembly"))] += 1
            qc: list[str] = []
            ac, an, af_rep = _num(g(rec, "ac"), True), _num(g(rec, "an"), True), _num(g(rec, "af"))
            for f, val in (("ac", ac), ("an", an), ("af", af_rep)):
                if val == "invalid":
                    stats["invalid_values"][f] += 1
                    qc.append(f"invalid_{f}")
                elif val is None and mapping.get(f):
                    stats["missing"][f] += 1
            ac = None if ac == "invalid" else ac
            an = None if an == "invalid" else an
            af_rep = None if af_rep == "invalid" else af_rep
            if ac is not None and an is not None:
                qc += check_counts(ac, an, af_rep)
                af = compute_af(ac, an)
            else:
                af = af_rep if af_rep is not None and 0 <= af_rep <= 1 else None
                if af_rep is not None and af is None:
                    qc.append("af_out_of_range")
                if af is not None:
                    qc.append("af_reported_without_counts")
            populations = []
            for pid, cols in pops.items():
                p_ac = _num(rec.get(cols.get("ac")), True) if cols.get("ac") else None
                p_an = _num(rec.get(cols.get("an")), True) if cols.get("an") else None
                p_af = _num(rec.get(cols.get("af"))) if cols.get("af") else None
                p_ac = None if p_ac == "invalid" else p_ac
                p_an = None if p_an == "invalid" else p_an
                p_af = None if p_af == "invalid" else p_af
                if p_ac is not None and p_an:
                    populations.append({"id": pid, "label": POPULATION_LABELS.get(pid, pid), "ac": p_ac, "an": p_an,
                                        "af": compute_af(p_ac, p_an), "homozygote_count": None})
                elif p_af is not None:  # frequency only – AC/AN not reported (kept as None, not derived)
                    populations.append({"id": pid, "label": POPULATION_LABELS.get(pid, pid), "ac": None, "an": None,
                                        "af": p_af, "homozygote_count": None})
            elig = [p for p in populations if p["id"] not in GRPMAX_EXCLUDED and p["af"]]
            top = max(elig, key=lambda p: p["af"]) if elig else None
            sig = _clean(g(rec, "clinical_significance"))
            fine, coarse = normalize_classification(sig) if sig else (None, "NOT_IN_CLINVAR")
            review = _clean(g(rec, "review_status"))
            rs = _clean(g(rec, "rsid"))
            row = normalize_record({"chrom": chrom, "pos": pos, "ref": ref, "alt": alt})
            if not row["coords_valid"]:
                stats["invalid"] += 1
                qc.append("invalid_coordinates")
                row["vcf_key"] = f"custom:row{i}"
            else:
                stats["valid"] += 1
                if row["vcf_key"] in seen:
                    stats["duplicates"] += 1
                    qc.append("duplicate_record")
                    row["vcf_key"] = f"{row['vcf_key']}#dup{i}"
                else:
                    seen[row["vcf_key"]] = i
            rows.append({
                **row, "provenance": "CUSTOM", "gene_symbol": _clean(g(rec, "gene")),
                "rsid": rs if rs and rs.lower().startswith("rs") else None,
                "ac": ac, "an": an, "af": af, "populations": populations,
                "popmax_af": top["af"] if top else None, "popmax_population": top["id"] if top else None,
                "homozygote_count": (lambda x: None if x in (None, "invalid") else x)(_num(g(rec, "homozygote_count"), True)),
                "in_gnomad": af is not None,  # "has a frequency" in the shared schema
                "in_clinvar": sig is not None,
                "clinical_significance": sig, "classification": fine, "coarse_class": coarse,
                "review_status": review, "gold_stars": gold_stars(review) if review else None,
                "match_status": "custom", "match_method": "custom_upload", "qc_flags": sorted(set(qc)),
                "gnomad_filters": [], "gnomad_flags": [],
            })
    stats["missing"] = dict(stats["missing"])
    stats["invalid_values"] = dict(stats["invalid_values"])
    stats["assembly_column_values"] = dict(stats["assembly_column_values"])
    return rows, stats


def concordance(own: list[dict], clinvar_rows: list[dict]) -> dict:
    """Compare the dataset's own classifications with ClinVar for the same alleles (no overwriting)."""
    by_key = {c["vcf_key"]: c for c in clinvar_rows if c.get("coords_valid")}
    pairs = [(r["coarse_class"], by_key[r["vcf_key"]]["coarse_class"]) for r in own
             if r.get("vcf_key") in by_key and r.get("in_clinvar")]
    agree = sum(1 for a, b in pairs if a == b)
    return {"compared": len(pairs), "agree": agree, "disagree": len(pairs) - agree,
            "agreement_rate": round(agree / len(pairs), 4) if pairs else None,
            "pairs": dict(Counter(f"{a} vs ClinVar {b}" for a, b in pairs).most_common(12))}


def write_cleaned(rows: list[dict], path: Path, dataset_name: str, assembly: str) -> Path:
    cols = ["variant_key", "provenance", "chrom", "pos", "ref", "alt", "variant_type", "gene_symbol", "rsid", "ac", "an",
            "af", "popmax_af", "popmax_population", "clinical_significance", "classification", "coarse_class",
            "classification_source", "review_status", "match_status", "qc_flags"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# GeneLens cleaned export of CUSTOM dataset '{dataset_name}' (assembly: {assembly}). "
                 "Empty cells = not available in the uploaded file (never zero). Research use only.\n")
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            src = ("ClinVar (retrieved, exact allele match)" if (r.get("match_method") or "").endswith("clinvar")
                   else "uploaded file" if r.get("clinical_significance") else "")
            out = {**r, "variant_key": r["vcf_key"], "classification_source": src,
                   "qc_flags": "|".join(r.get("qc_flags") or [])}
            w.writerow(["" if out.get(c) is None else out.get(c) for c in cols])
    return path


# --------------------------------------------------------------------------- orchestration
MAX_CLINVAR_GENES = 10
_TRUNC = {"chrom": 8, "gene_symbol": 32, "rsid": 32, "classification": 48, "review_status": 128,
          "clinical_significance": 256, "variant_type": 16, "popmax_population": 16, "match_method": 64}


def _event(ds, action: str, detail: str | None = None):
    from app.models import utcnow

    ds.history = [*(ds.history or []), {"at": utcnow().isoformat(), "action": action, "detail": detail}]


def _af_histogram(rows: list[dict]) -> dict:
    edges = np.arange(-7, 0.25, 0.5)
    vals = np.array([r["af"] for r in rows if r.get("af")], dtype=float)
    counts = np.histogram(np.clip(np.log10(vals), -7, 0), bins=edges)[0].tolist() if vals.size else [0] * (len(edges) - 1)
    zero = sum(1 for r in rows if r.get("af") == 0)
    return {"edges": edges.tolist(), "counts": counts, "with_af": int(vals.size), "af_zero": zero,
            "af_missing": sum(1 for r in rows if r.get("af") is None)}


def _clinvar_annotate(rows: list[dict], assembly: str, clinvar, has_own_class: bool, progress) -> dict:
    """Retrieve ClinVar for the dataset's genes and match **by exact allele** (then minimal representation).

    Own classifications are never overwritten; with them, a concordance table is produced instead."""
    from app.pipeline.preprocessing import preprocess_clinvar
    from app.services.clinvar_client import to_grch37

    if assembly not in ("GRCh37", "GRCh38"):
        return {"status": "unavailable", "reason": "The genome assembly is unknown, so coordinates cannot be "
                                                    "compared with ClinVar. Choose GRCh37 or GRCh38 and reprocess."}
    genes = [g for g, _ in Counter(r["gene_symbol"] for r in rows if r.get("gene_symbol") and r.get("coords_valid"))
             .most_common(MAX_CLINVAR_GENES)]
    if not genes:
        return {"status": "unavailable", "reason": "No gene symbol column is mapped, so GeneLens cannot decide which "
                                                    "ClinVar records to retrieve (it never matches by gene name alone, "
                                                    "but needs the gene to query ClinVar)."}
    cv_rows, errors = [], []
    for i, g in enumerate(genes):
        progress(f"Retrieving ClinVar records for {g}", i / len(genes))
        try:
            raw, _meta = clinvar.fetch_gene_eutils(g)
            if assembly == "GRCh37":
                raw = [to_grch37(r) for r in raw]
            cv_rows += preprocess_clinvar(raw)
        except Exception as exc:  # noqa: BLE001 – recorded, never fatal
            from app.utils import user_message
            errors.append({"gene": g, "message": user_message(exc)})
    by_vcf: dict[str, list[dict]] = {}
    by_min: dict[str, list[dict]] = {}
    for c in cv_rows:
        if c.get("coords_valid"):
            by_vcf.setdefault(c["vcf_key"], []).append(c)
            by_min.setdefault(c["minimal_key"], []).append(c)
    counts = Counter()
    for r in rows:
        if not r.get("coords_valid"):
            continue
        key = r["vcf_key"].split("#dup")[0]
        hits, method = by_vcf.get(key), "exact"
        if not hits and r.get("minimal_key") in by_min:
            hits, method = by_min[r["minimal_key"]], "normalized"
        if not hits:
            counts["no_clinvar_record"] += 1
            continue
        if len({h["coarse_class"] for h in hits}) > 1:
            counts["ambiguous"] += 1
            r["qc_flags"] = sorted(set(r["qc_flags"]) | {"ambiguous_match"})
            continue
        h = hits[0]
        counts[method] += 1
        r["clinvar_variation_id"] = h.get("clinvar_variation_id")
        if has_own_class:
            r["_clinvar_coarse"] = h["coarse_class"]
            continue
        r.update({k: h.get(k) for k in ("clinical_significance", "classification", "coarse_class", "review_status",
                                         "gold_stars", "conditions", "last_evaluated", "submitter_count", "name")})
        r["in_clinvar"] = True
        r["match_method"] = f"custom_upload+{method}_clinvar"
    out = {"status": "completed" if not errors else ("partial" if cv_rows else "failed"),
           "genes_queried": genes, "clinvar_records_retrieved": len(cv_rows), "errors": errors,
           "matched_exact": counts["exact"], "matched_normalized": counts["normalized"],
           "ambiguous": counts["ambiguous"], "no_clinvar_record": counts["no_clinvar_record"],
           "mode": "concordance" if has_own_class else "annotation",
           "note": ("The file's own classifications are kept; ClinVar is shown only for comparison." if has_own_class
                    else "Classifications were retrieved from ClinVar for exact allele matches only.")}
    if has_own_class:
        pairs = [(r["coarse_class"], r.pop("_clinvar_coarse")) for r in rows if "_clinvar_coarse" in r]
        pairs = [(a, b) for a, b in pairs if a != "NOT_IN_CLINVAR"]
        agree = sum(1 for a, b in pairs if a == b)
        out["concordance"] = {"compared": len(pairs), "agree": agree, "disagree": len(pairs) - agree,
                              "agreement_rate": round(agree / len(pairs), 4) if pairs else None,
                              "pairs": dict(Counter(f"{a} → ClinVar {b}" for a, b in pairs).most_common(12))}
    return out


def process(db, ds_id: str, clinvar=None) -> None:
    """Background job: validate → normalise → store → (ClinVar) → statistics → populations → anomalies."""
    import logging
    import time
    import traceback

    from sqlalchemy import delete, insert

    from app.config import get_settings
    from app.models import CustomDataset, Variant, utcnow
    from app.pipeline import anomalies as anomaly_mod
    from app.pipeline import rowcache
    from app.pipeline.populations import population_summary
    from app.pipeline.runner import VARIANT_COLUMNS
    from app.pipeline.statistics import run_statistics
    from app.utils import json_safe, user_message

    log = logging.getLogger("genelens.custom")
    ds = db.get(CustomDataset, ds_id)
    if ds is None:
        return
    t0 = time.time()

    def stage(name: str, p: float):
        ds.stage, ds.progress, ds.updated_at = name, round(p, 3), utcnow()
        db.commit()

    try:
        ds.status, ds.error, ds.summary = "processing", None, None
        mapping = ds.mapping or (ds.inspection or {}).get("suggested_mapping") or {}
        pops = (ds.inspection or {}).get("population_columns") or {}
        if not ((mapping.get("chrom") and mapping.get("pos") and mapping.get("ref") and mapping.get("alt"))
                or mapping.get("variant_id")):
            raise DatasetError("Map the chromosome, position, reference and alternate columns (or a variant "
                               "identifier column) before running the analysis.")
        stage("Validating and normalising records", 0.1)
        rows, qstats = build_rows(Path(ds.stored_path), ds.file_format, mapping, pops, ds.assembly)
        if qstats["valid"] == 0:
            raise DatasetError("None of the records has valid chromosome / position / REF / ALT values with the "
                               "current column mapping.")
        asm_values = qstats["assembly_column_values"]
        if ds.assembly != "unknown" and asm_values:
            other = [v for v in asm_values if ds.assembly.lower()[-2:] not in v.lower()]
            if other:
                raise DatasetError(f"The file's assembly column contains {', '.join(other[:3])}, which conflicts "
                                   f"with the selected assembly {ds.assembly}. GeneLens does not mix assemblies.")
        has_own_class = bool(mapping.get("clinical_significance"))
        opts = ds.options or {}
        if opts.get("clinvar", True):
            stage("Matching with ClinVar", 0.3)
            if clinvar is None:
                from app.services.clinvar_client import ClinVarClient
                clinvar = ClinVarClient()
            matching = _clinvar_annotate(rows, ds.assembly, clinvar, has_own_class,
                                         lambda s, f: stage(s, 0.3 + 0.3 * f))
        else:
            matching = {"status": "skipped", "reason": "ClinVar matching was turned off for this dataset."}

        stage("Storing records", 0.62)
        db.execute(delete(Variant).where(Variant.custom_dataset_id == ds.id))
        payload = []
        for r in rows:
            rec = {k: r.get(k) for k in VARIANT_COLUMNS if k in r}
            for k, n in _TRUNC.items():
                if isinstance(rec.get(k), str):
                    rec[k] = rec[k][:n]
            rec.update(custom_dataset_id=ds.id, analysis_id=None, synthetic_job_id=None, provenance="CUSTOM",
                       variant_key=r["vcf_key"][:512], in_gnomad=bool(r.get("in_gnomad")),
                       in_clinvar=bool(r.get("in_clinvar")))
            payload.append(rec)
        for i in range(0, len(payload), 2000):
            db.execute(insert(Variant), payload[i:i + 2000])
        db.commit()
        rowcache.invalidate()
        stored = rowcache.rows(db, ("CUSTOM", ds.id), Variant.custom_dataset_id == ds.id,
                               Variant.provenance == "CUSTOM")

        stage("Running statistics", 0.75)
        # statistics use each distinct valid allele once (invalid rows and repeated records are excluded)
        valid_rows = [r for r in stored if not {"invalid_coordinates", "duplicate_record"} & set(r.get("qc_flags") or [])]
        stats = run_statistics(valid_rows)
        stage("Population summary", 0.84)
        pop = population_summary(valid_rows) if pops else None
        stage("Screening for anomalies", 0.9)
        an = json_safe(anomaly_mod.detect_anomalies(valid_rows, None))
        flags = [{k: f.get(k) for k in ("variant_id", "variant_key", "category", "kind", "priority", "headline",
                                         "reason", "why_it_matters", "recommendation")} for f in an["flags"][:300]]
        if has_own_class:  # the classification came from the user's file, not from ClinVar
            for f in flags:
                f["reason"] = (f.get("reason") or "").replace("in ClinVar", "in the uploaded file")

        stage("Writing cleaned dataset", 0.96)
        out_dir = get_settings().data_dir / "uploads" / ds.id
        out_dir.mkdir(parents=True, exist_ok=True)
        cleaned = write_cleaned(stored, out_dir / "cleaned.csv", ds.name, ds.assembly)

        cls = Counter(r.get("coarse_class") or "NOT_IN_CLINVAR" for r in valid_rows)
        n_af_computed = sum(1 for r in valid_rows if r.get("ac") is not None and r.get("an") and r.get("af") is not None)
        n_af_reported = sum(1 for r in valid_rows if r.get("af") is not None) - n_af_computed
        retrieved = sum(1 for r in valid_rows if (r.get("match_method") or "").endswith("clinvar"))
        field_status = {
            "allele_frequency": ("calculated from AC/AN" if n_af_computed and not n_af_reported else
                                 "reported in file" if n_af_reported and not n_af_computed else
                                 "mixed: calculated from AC/AN where available, otherwise reported" if n_af_computed
                                 else "unavailable"),
            "classification": ("from uploaded file" if has_own_class else
                               "retrieved from ClinVar (exact allele matches)" if retrieved else "unavailable"),
            "populations": "from uploaded file" if pops else "unavailable",
            "assembly": {"user": "selected by user", "file_header": "read from file header"}.get(ds.assembly_source or "",
                                                                                                 "unknown"),
            "review_status": ("from uploaded file" if mapping.get("review_status") else
                              "retrieved from ClinVar" if retrieved else "unavailable"),
        }
        ds.summary = json_safe({
            "totals": {"rows": qstats["total"], "valid": qstats["valid"], "invalid": qstats["invalid"],
                       "duplicates": qstats["duplicates"],
                       "unique_valid": len(valid_rows),
                       "records_with_missing_fields": sum(1 for r in stored if r.get("af") is None or
                                                          "invalid_coordinates" in (r.get("qc_flags") or []))},
            "missing_by_field": qstats["missing"], "invalid_values": qstats["invalid_values"],
            "field_status": field_status,
            "classification_distribution": dict(cls),
            "variant_types": dict(Counter(r.get("variant_type") or "unknown" for r in valid_rows)),
            "genes": dict(Counter(r.get("gene_symbol") or "not given" for r in valid_rows).most_common(15)),
            "af_distribution": _af_histogram(valid_rows),
            "statistics": stats, "populations": pop, "clinvar": matching,
            "quality": {"qc_flag_counts": dict(Counter(f for r in stored for f in (r.get("qc_flags") or []))),
                        "records_with_flags": sum(1 for r in stored if r.get("qc_flags"))},
            "anomaly_summary": an["summary"], "anomalies": flags,
            "runtime_seconds": round(time.time() - t0, 2),
        })
        ds.cleaned_path = str(cleaned)
        ds.status, ds.stage, ds.progress, ds.updated_at = "completed", "Completed", 1.0, utcnow()
        _event(ds, "processed", f"{qstats['valid']:,} valid of {qstats['total']:,} records")
        db.commit()
    except Exception as exc:  # noqa: BLE001 – stored as a user-facing message
        db.rollback()
        ds = db.get(CustomDataset, ds_id)
        ds.status, ds.error, ds.updated_at = "failed", (str(exc) if isinstance(exc, DatasetError)
                                                        else user_message(exc, log)), utcnow()
        _event(ds, "failed", ds.error)
        db.commit()
        log.error("Custom dataset %s failed: %s\n%s", ds_id, exc, traceback.format_exc())

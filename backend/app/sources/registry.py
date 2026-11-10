"""Central registry of GeneLens data sources (connectors).

Each adapter describes one provider and implements ``probe()``, which makes
a small *real* request and returns availability, a human-readable detail and,
where the provider publishes one, the current release. Probe results and
retrieval statistics are stored in the ``source_status`` table
(see :mod:`app.sources.tracking`).

To add a provider: subclass :class:`SourceAdapter`, implement ``probe`` and
append an instance to ``SOURCES``. Nothing else needs to change.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.services.http import request_with_retry
from app.sources.tracking import record_probe


log = logging.getLogger(__name__)


def describe_failure(exc: Exception) -> str:
    """Short, user-facing reason a source check failed (full details are logged)."""
    import httpx

    from app.services.http import ExternalServiceError

    text = str(exc).lower()
    if isinstance(exc, httpx.TimeoutException) or "timed out" in text or "timeout" in text:
        return "No response within 10 seconds – the service may be slow or unreachable from this network."
    if isinstance(exc, httpx.ConnectError) or "connect" in text or "403" in text and "tunnel" in text:
        return "Could not connect – the host may be down or blocked by a firewall/proxy on this network."
    if isinstance(exc, ExternalServiceError) and exc.status_code:
        return f"The service answered with HTTP {exc.status_code}; it may be temporarily unavailable or rate-limiting."
    return "The service returned an unexpected response; see the backend log for details."


@dataclass
class SourceAdapter:
    id: str
    name: str
    provider: str
    method: str                      # integration method shown in the UI
    endpoint: str
    category: str                    # population_frequency | clinical | annotation | variant_catalogue | reference
    provides: list[str] = field(default_factory=list)
    used_for: str = ""
    homepage: str = ""

    def probe(self) -> dict:  # pragma: no cover - overridden
        raise NotImplementedError

    def check(self) -> dict:
        from app.services.http import PROBE_MODE

        token = PROBE_MODE.set(True)
        t = time.time()
        try:
            out = self.probe()
            out.setdefault("available", True)
        except Exception as exc:  # noqa: BLE001 - any failure means "unavailable", with the reason
            log.warning("probe %s failed: %r", self.id, exc)
            out = {"available": False, "detail": describe_failure(exc), "release": None}
        finally:
            PROBE_MODE.reset(token)
        out["latency_ms"] = int((time.time() - t) * 1000)
        record_probe(self.id, out["available"], out.get("detail", ""), out.get("release"), out["latency_ms"])
        return out


class GnomadSource(SourceAdapter):
    def probe(self):
        from app.services.gnomad_client import GnomadClient

        meta = GnomadClient().ping()
        return {"detail": "GraphQL endpoint answered; schema introspection used for dataset checks",
                "release": f"Browser API (ClinVar mirror {meta.get('clinvar_release_date')})"}


class ClinVarEutilsSource(SourceAdapter):
    def probe(self):
        s = get_settings()
        d = request_with_retry("GET", f"{s.ncbi_eutils_url}/einfo.fcgi", "ClinVar",
                               params={"db": "clinvar", "retmode": "json"}).json()
        info = d["einforesult"]["dbinfo"][0]
        return {"detail": f"{int(info['count']):,} ClinVar records indexed",
                "release": f"ClinVar (last update {info.get('lastupdate')})"}


class ClinVarTsvSource(SourceAdapter):
    def probe(self):
        from app.services.clinvar_client import ClinVarClient

        s = get_settings()
        r = request_with_retry("HEAD", s.clinvar_tsv_url, "ClinVar FTP")
        size = int(r.headers.get("Content-Length", 0)) / 1e6
        local = ClinVarClient().tsv_path
        loc = (f"downloaded locally ({local.stat().st_size / 1e6:.0f} MB)" if local.exists()
               else "not downloaded yet – run python -m scripts.download_clinvar")
        return {"detail": f"variant_summary.txt.gz reachable ({size:.0f} MB); {loc}",
                "release": f"variant_summary.txt.gz, modified {r.headers.get('Last-Modified', '?')}",
                "local_file": local.exists(), "remote_size_mb": round(size, 1),
                "remote_file_available": r.status_code == 200}


class EnsemblSource(SourceAdapter):
    def probe(self):
        from app.services.ensembl_client import EnsemblClient

        return {"detail": "REST API answered (GRCh38 + GRCh37 servers)", "release": EnsemblClient().release()}


class DbSNPSource(SourceAdapter):
    def probe(self):
        from app.services.dbsnp_client import VARIATION_API, DbSNPClient

        info = DbSNPClient().info()
        request_with_retry("GET", f"{VARIATION_API}/spdi/NC_000011.10:5227001:T:A/rsids", "NCBI Variation")
        return {"detail": f"E-utilities db=snp ({int(info['count']):,} RefSNPs) and Variation Services API answered",
                "release": f"dbSNP {info['build']} (updated {info['last_update']})"}


class IGSRSource(SourceAdapter):
    def probe(self):
        from app.services.igsr_client import API, IGSRClient

        body = request_with_retry("POST", f"{API}/population/_search", "IGSR", json={"size": 0}).json()
        modified = IGSRClient().ping_files()
        return {"detail": f"Data portal lists {body['hits']['total']} populations; phase 3 VCF index reachable",
                "release": f"1000 Genomes phase 3 (20130502); files modified {modified}"}


class UCSCSource(SourceAdapter):
    def probe(self):
        from app.services.ucsc_client import UCSCClient

        a = UCSCClient().assemblies()
        return {"detail": "REST API answered", "release": f"hg38: {a['GRCh38']} · hg19: {a['GRCh37']}"}


SOURCES: list[SourceAdapter] = [
    GnomadSource("gnomad", "gnomAD GraphQL API", "Broad Institute", "GraphQL API (HTTPS)",
                 "https://gnomad.broadinstitute.org/api", "population_frequency",
                 ["Allele counts / numbers / frequencies", "Population-specific frequencies",
                  "Gene constraint (pLI, LOEUF, o/e)", "Gene search"],
                 "Population frequency datasets 1–7 and gene constraint", "https://gnomad.broadinstitute.org"),
    ClinVarEutilsSource("clinvar_eutils", "NCBI ClinVar E-utilities", "NCBI", "REST API (esearch + esummary)",
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils", "clinical",
                        ["Variation IDs", "Clinical significance", "Review status", "Conditions",
                         "GRCh38 SPDI + GRCh37/38 locations"],
                        "Clinical classifications for every analysis (default)", "https://www.ncbi.nlm.nih.gov/clinvar/"),
    ClinVarTsvSource("clinvar_tsv", "ClinVar Bulk TSV / FTP", "NCBI", "Bulk file download (HTTPS/FTP)",
                     "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/", "clinical",
                     ["variant_summary.txt.gz", "VCF-normalised positions (GRCh37 + GRCh38)", "Allele IDs"],
                     "Large-scale / offline clinical analysis; GRCh37 VCF positions", "https://www.ncbi.nlm.nih.gov/clinvar/"),
    EnsemblSource("ensembl", "Ensembl REST API", "EMBL-EBI", "REST API (HTTPS)", "https://rest.ensembl.org",
                  "annotation", ["Gene identifiers & names", "Gene coordinates (GRCh37/38)", "Canonical transcripts",
                                 "VEP variant annotation"],
                  "Gene annotation, GRCh37 coordinates for 1000 Genomes, on-demand VEP", "https://www.ensembl.org"),
    DbSNPSource("dbsnp", "NCBI dbSNP / Variation API", "NCBI", "REST APIs (E-utilities db=snp + Variation Services)",
                "https://api.ncbi.nlm.nih.gov/variation/v0", "variant_catalogue",
                ["RefSNP IDs", "Reference/alternate alleles (SPDI)", "Per-study allele frequencies", "Cross-references"],
                "dbSNP dataset (#10) and RefSNP details in the variant inspector", "https://www.ncbi.nlm.nih.gov/snp/"),
    IGSRSource("igsr", "International Genome Sample Resource", "IGSR / EMBL-EBI",
               "Data-portal API + tabix range requests on phase 3 VCFs", "https://www.internationalgenome.org",
               "population_frequency", ["1000 Genomes phase 3 variants", "Super-population frequencies",
                                        "Population & sample metadata"],
               "1000 Genomes dataset (#8)", "https://www.internationalgenome.org"),
    UCSCSource("ucsc", "UCSC Genome Browser API", "UC Santa Cruz", "REST API (HTTPS)", "https://api.genome.ucsc.edu",
               "reference", ["Assembly descriptions", "RefSeq gene coordinates", "Cytogenetic bands", "Genome tracks"],
               "Gene coordinate cross-check and cytoband for each analysis", "https://genome.ucsc.edu"),
]
BY_ID = {s.id: s for s in SOURCES}

"""Gene suggestions for the search box.

A local catalogue of commonly studied genes (official HGNC symbols and names,
plus a one-line plain-language description) answers instantly – including
before the user types – and is complemented by live gnomAD ``gene_search``
results for any other gene.
"""
from __future__ import annotations

from app.datasets import DATASETS
from app.services.gnomad_client import snapshot_path

STARTERS = ["HBB", "CFTR", "BRCA1", "BRCA2", "TP53", "LDLR", "G6PD", "PAH"]

# symbol: (official name, chromosome, plain-language description)
CATALOGUE: dict[str, tuple[str, str, str]] = {
    "HBB": ("Hemoglobin subunit beta", "11", "Beta chain of adult hemoglobin; variants cause sickle cell disease and beta-thalassemia."),
    "CFTR": ("CF transmembrane conductance regulator", "7", "Chloride channel in epithelial cells; biallelic variants cause cystic fibrosis."),
    "BRCA1": ("BRCA1 DNA repair associated", "17", "Homologous-recombination DNA repair; variants raise hereditary breast and ovarian cancer risk."),
    "BRCA2": ("BRCA2 DNA repair associated", "13", "Loads RAD51 for DNA repair; variants raise breast, ovarian, prostate and pancreatic cancer risk."),
    "TP53": ("Tumor protein p53", "17", "The 'guardian of the genome' tumour suppressor; germline variants cause Li-Fraumeni syndrome."),
    "LDLR": ("Low density lipoprotein receptor", "19", "Clears LDL cholesterol from blood; variants cause familial hypercholesterolemia."),
    "G6PD": ("Glucose-6-phosphate dehydrogenase", "X", "Protects red cells from oxidative stress; deficiency causes drug- or food-triggered hemolysis."),
    "PAH": ("Phenylalanine hydroxylase", "12", "Converts phenylalanine to tyrosine; biallelic variants cause phenylketonuria (PKU)."),
    "HBA1": ("Hemoglobin subunit alpha 1", "16", "Alpha chain of hemoglobin; deletions and variants cause alpha-thalassemia."),
    "MLH1": ("MutL homolog 1", "3", "DNA mismatch repair; germline variants cause Lynch syndrome."),
    "MSH2": ("MutS homolog 2", "2", "DNA mismatch repair; germline variants cause Lynch syndrome."),
    "MSH6": ("MutS homolog 6", "2", "DNA mismatch repair partner of MSH2; associated with Lynch syndrome."),
    "PMS2": ("PMS1 homolog 2, mismatch repair system component", "7", "DNA mismatch repair; associated with Lynch syndrome."),
    "APC": ("APC regulator of WNT signaling pathway", "5", "Tumour suppressor in WNT signalling; variants cause familial adenomatous polyposis."),
    "PTEN": ("Phosphatase and tensin homolog", "10", "Tumour suppressor in PI3K signalling; variants cause PTEN hamartoma tumour syndrome."),
    "PALB2": ("Partner and localizer of BRCA2", "16", "Links BRCA1 and BRCA2 in DNA repair; variants raise breast cancer risk."),
    "ATM": ("ATM serine/threonine kinase", "11", "DNA damage signalling kinase; biallelic variants cause ataxia-telangiectasia."),
    "CHEK2": ("Checkpoint kinase 2", "22", "Cell-cycle checkpoint kinase; some variants moderately raise cancer risk."),
    "MUTYH": ("MutY DNA glycosylase", "1", "Base-excision repair; biallelic variants cause MUTYH-associated polyposis."),
    "RB1": ("RB transcriptional corepressor 1", "13", "Cell-cycle gatekeeper; germline variants cause retinoblastoma."),
    "VHL": ("Von Hippel-Lindau tumor suppressor", "3", "Regulates hypoxia signalling; variants cause von Hippel-Lindau syndrome."),
    "MYH7": ("Myosin heavy chain 7", "14", "Cardiac muscle myosin; variants cause hypertrophic and dilated cardiomyopathy."),
    "MYBPC3": ("Myosin binding protein C3", "11", "Cardiac sarcomere protein; the most common hypertrophic cardiomyopathy gene."),
    "KCNQ1": ("Potassium voltage-gated channel subfamily Q member 1", "11", "Cardiac potassium channel; variants cause long QT syndrome type 1."),
    "KCNH2": ("Potassium voltage-gated channel subfamily H member 2", "7", "hERG cardiac potassium channel; variants cause long QT syndrome type 2."),
    "SCN5A": ("Sodium voltage-gated channel alpha subunit 5", "3", "Cardiac sodium channel; variants cause Brugada and long QT syndromes."),
    "TTN": ("Titin", "2", "Giant sarcomere protein; truncating variants are a major cause of dilated cardiomyopathy."),
    "FBN1": ("Fibrillin 1", "15", "Extracellular-matrix microfibril protein; variants cause Marfan syndrome."),
    "DMD": ("Dystrophin", "X", "Links muscle cytoskeleton to membrane; variants cause Duchenne and Becker muscular dystrophy."),
    "SMN1": ("Survival of motor neuron 1, telomeric", "5", "Motor-neuron survival protein; loss causes spinal muscular atrophy."),
    "HTT": ("Huntingtin", "4", "CAG repeat expansions cause Huntington disease."),
    "FMR1": ("FMRP translational regulator 1", "X", "CGG repeat expansions cause fragile X syndrome."),
    "GBA1": ("Glucosylceramidase beta 1", "1", "Lysosomal enzyme; biallelic variants cause Gaucher disease and raise Parkinson risk."),
    "HEXA": ("Hexosaminidase subunit alpha", "15", "Lysosomal enzyme; biallelic variants cause Tay-Sachs disease."),
    "HFE": ("Homeostatic iron regulator", "6", "Regulates iron uptake; C282Y homozygosity causes hereditary hemochromatosis."),
    "APOE": ("Apolipoprotein E", "19", "Lipid transport; the e4 allele is a major Alzheimer disease risk factor."),
    "APOB": ("Apolipoprotein B", "2", "LDL particle protein; variants cause familial hypercholesterolemia."),
    "PCSK9": ("Proprotein convertase subtilisin/kexin type 9", "1", "Degrades LDL receptors; gain-of-function variants raise LDL cholesterol."),
    "F5": ("Coagulation factor V", "1", "Clotting factor; the Leiden variant increases venous thrombosis risk."),
    "F8": ("Coagulation factor VIII", "X", "Clotting factor; variants cause hemophilia A."),
    "SERPINA1": ("Serpin family A member 1", "14", "Alpha-1 antitrypsin; variants cause alpha-1 antitrypsin deficiency."),
    "GJB2": ("Gap junction protein beta 2", "13", "Connexin 26; the most common cause of inherited non-syndromic hearing loss."),
    "PKD1": ("Polycystin 1, transient receptor potential channel interacting", "16", "Variants cause autosomal dominant polycystic kidney disease."),
    "RYR1": ("Ryanodine receptor 1", "19", "Skeletal-muscle calcium channel; variants cause malignant hyperthermia susceptibility."),
    "CYP2C19": ("Cytochrome P450 family 2 subfamily C member 19", "10", "Drug-metabolising enzyme; variants change response to clopidogrel and others."),
    "CYP2D6": ("Cytochrome P450 family 2 subfamily D member 6", "22", "Metabolises ~25% of common drugs; highly polymorphic."),
    "DPYD": ("Dihydropyrimidine dehydrogenase", "1", "Breaks down fluoropyrimidines; deficiency causes severe chemotherapy toxicity."),
    "TPMT": ("Thiopurine S-methyltransferase", "6", "Metabolises thiopurine drugs; variants raise toxicity risk."),
    "MECP2": ("Methyl-CpG binding protein 2", "X", "Chromatin regulator; variants cause Rett syndrome."),
    "SCN1A": ("Sodium voltage-gated channel alpha subunit 1", "2", "Neuronal sodium channel; variants cause Dravet syndrome."),
    "EGFR": ("Epidermal growth factor receptor", "7", "Growth-factor receptor; somatic variants drive some lung cancers (germline data here)."),
    "KRAS": ("KRAS proto-oncogene, GTPase", "12", "RAS signalling; germline variants cause Noonan syndrome."),
    "PTPN11": ("Protein tyrosine phosphatase non-receptor type 11", "12", "RAS-MAPK regulator; the most common Noonan syndrome gene."),
    "NF1": ("Neurofibromin 1", "17", "RAS GTPase-activating protein; variants cause neurofibromatosis type 1."),
    "TSC2": ("TSC complex subunit 2", "16", "mTOR regulator; variants cause tuberous sclerosis complex."),
}


def _compatible(chrom: str | None) -> list[str]:
    if chrom in ("MT", "Y"):
        return [d.id for d in DATASETS if d.kind in ("clinvar_only", "dbsnp")]
    return [d.id for d in DATASETS]


def _entry(symbol: str, analysed: dict[str, int], starter: bool) -> dict:
    name, chrom, desc = CATALOGUE.get(symbol, (None, None, None))
    snap = snapshot_path(symbol, "gnomad", "gnomad_r4").exists()
    return {"symbol": symbol, "name": name, "chrom": chrom, "description": desc, "starter": starter,
            "analysed": analysed.get(symbol, 0), "offline_snapshot": snap,
            "data_status": ("analysed – data stored locally" if analysed.get(symbol) else
                            "offline snapshot + live sources" if snap else "live sources"),
            "compatible_datasets": _compatible(chrom), "in_catalogue": symbol in CATALOGUE}


def suggest(q: str, limit: int, analysed: dict[str, int]) -> dict:
    q = (q or "").strip().upper()
    if not q:
        return {"query": "", "results": [_entry(s, analysed, True) for s in STARTERS], "live_search": None}
    local = [s for s in CATALOGUE if s.startswith(q)]
    local += [s for s, (n, _, d) in CATALOGUE.items() if s not in local and (q in n.upper() or q in d.upper())]
    results = [_entry(s, analysed, s in STARTERS) for s in local[:limit]]
    live = None
    if len(results) < limit:
        from app.services.gnomad_client import GnomadClient
        from app.services.http import ExternalServiceError

        try:
            hits = GnomadClient().search_genes(q)
            live = "gnomAD gene_search"
            for h in hits:
                if h["symbol"] not in {r["symbol"] for r in results} and len(results) < limit:
                    results.append({**_entry(h["symbol"], analysed, False), "ensembl_id": h.get("ensembl_id")})
        except ExternalServiceError as exc:
            live = f"unavailable ({exc})"
    return {"query": q, "results": results, "live_search": live}

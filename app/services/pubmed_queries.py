"""PubMed discovery search queries aligned with curator-desk / BugSigDB spec."""

from __future__ import annotations

# Spec Section 4.3 — recommended discovery search (recall-optimized).
RECOMMENDED_DISCOVERY_QUERY = """\
(
  ("Microbiota"[MeSH] OR "Gastrointestinal Microbiome"[MeSH] OR
   microbiome[Title/Abstract] OR microbiota[Title/Abstract] OR
   "microbial community"[Title/Abstract] OR "microbial communities"[Title/Abstract] OR
   "bacterial community"[Title/Abstract] OR "bacterial communities"[Title/Abstract])
  AND
  ("Sequence Analysis, DNA"[MeSH] OR "High-Throughput Nucleotide Sequencing"[MeSH] OR
   "Metagenomics"[MeSH] OR metagenomics[Title/Abstract] OR metagenome[Title/Abstract] OR
   "16S rRNA"[Title/Abstract] OR "16S ribosomal RNA"[Title/Abstract] OR
   "ITS"[Title/Abstract] OR "internal transcribed spacer"[Title/Abstract] OR
   "amplicon sequencing"[Title/Abstract] OR "shotgun sequencing"[Title/Abstract] OR
   "next-generation sequencing"[Title/Abstract] OR "whole genome sequencing"[Title/Abstract])
  AND
  (abundance[Title/Abstract] OR composition[Title/Abstract] OR
   diversity[Title/Abstract] OR dysbiosis[Title/Abstract] OR
   enriched[Title/Abstract] OR depleted[Title/Abstract] OR
   "community structure"[Title/Abstract] OR profiling[Title/Abstract])
)
NOT
(review[Publication Type] OR "systematic review"[Title/Abstract] OR
 "meta-analysis"[Publication Type] OR "meta-analysis"[Title/Abstract] OR
 protocol[Title] OR editorial[Publication Type] OR
 "methods paper"[Title/Abstract])\
"""

ULTRA_BROAD_QUERY = """\
("Microbiota"[MeSH] OR microbiome[Title/Abstract] OR microbiota[Title/Abstract])
AND
("Sequence Analysis, DNA"[MeSH] OR metagenom*[Title/Abstract] OR "16S"[Title/Abstract])
NOT
(review[Publication Type] OR "meta-analysis"[Publication Type])\
"""

HIGH_PRECISION_QUERY = """\
("Microbiota"[MeSH] AND
 ("High-Throughput Nucleotide Sequencing"[MeSH] OR "Metagenomics"[MeSH])
 AND "differential abundance"[Title/Abstract])
NOT
(review[Publication Type] OR protocol[Title])\
"""

SEARCH_PRESETS = {
    "discovery": RECOMMENDED_DISCOVERY_QUERY,
    "broad": ULTRA_BROAD_QUERY,
    "precision": HIGH_PRECISION_QUERY,
}

# Bulk-corpus MeSH queries (from Chloe, via Slack, 2026-08) - topic-scoped
# searches for scripts/bulk_pubmed_retrieval.py's ~10k-article retrieval
# round. Kept verbatim as provided; used as raw ESearch `term` strings.
WOMENS_HEALTH_QUERY = (
    '("Microbiota"[Mesh] OR "Gastrointestinal Microbiome"[Mesh] OR '
    '"Vagina/microbiology"[Mesh] OR microbiome*[tiab] OR microbiota*[tiab]) '
    'AND ("Female"[Mesh] OR women[tiab] OR woman[tiab] OR female*[tiab]) '
    'AND ("High-Throughput Nucleotide Sequencing"[Mesh] OR sequencing[tiab] '
    'OR metagenomic*[tiab] OR "16S"[tiab]) AND ("differential abundance"[tiab] '
    'OR "differentially abundant"[tiab] OR "dysbiosis"[tiab])'
)

MASLD_QUERY = (
    '("MASLD"[tiab] OR "Metabolic dysfunction-associated steatotic liver '
    'disease"[tiab] OR "MAFLD"[tiab] OR "NAFLD"[tiab] OR "nonalcoholic fatty '
    'liver disease"[tiab] OR "non-alcoholic steatohepatitis"[tiab] OR '
    '"NASH"[tiab] OR "steatotic liver disease"[tiab]) AND ("microbiome"[tiab] '
    'OR "microbiota"[tiab] OR "microbial community"[tiab] OR "gut flora"[tiab] '
    'OR "dysbiosis"[tiab] OR "gut bacteria"[tiab] OR "metagenomics"[tiab] OR '
    '"16S rRNA"[tiab])'
)

COLORECTAL_CANCER_QUERY = (
    '("CRC"[tiab] OR "colorectal cancer"[tiab] OR "colorectal carcinoma"[tiab] '
    'OR "colon cancer"[tiab] OR "rectal cancer"[tiab] OR "colorectal '
    'neoplasm"[tiab] OR "colonic neoplasm"[tiab] OR "colorectal adenoma"[tiab]) '
    'AND ("microbiome"[tiab] OR "microbiota"[tiab] OR "microbial '
    'community"[tiab] OR "gut flora"[tiab] OR "dysbiosis"[tiab] OR '
    '"metagenomics"[tiab] OR "16S rRNA"[tiab] OR "fecal microbiota"[tiab] OR '
    '"intestinal microbiome"[tiab] OR "Fusobacterium nucleatum"[tiab] OR '
    '"Bacteroides fragilis"[tiab])'
)

BULK_RETRIEVAL_QUERIES = {
    "womens_health": WOMENS_HEALTH_QUERY,
    "masld": MASLD_QUERY,
    "colorectal_cancer": COLORECTAL_CANCER_QUERY,
}

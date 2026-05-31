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

# Levi Main Points Implementation

This document tracks implementation of the decisions and sequence from curator-desk PR #13 discussion.

## Decision alignment

- [x] **Do not record "Taxa Level" in curator-desk scoring/display schema.**
  - `curator_table_r/R/config.R`: `STATUS_COLUMNS` now excludes `Taxa Level Status`.
  - `curator_table_r/docs/SPEC.md`: normalized to 5 prediction fields and 0-5 priority scale.

- [x] **Priority score and threshold are curator-desk post-BioAnalyzer decisions.**
  - `curator_table_r/R/data.R`: priority remains a simple sum over configured status columns.
  - `curator_table_r/docs/SPEC.md`: notes threshold should be refined with exploratory analysis.

## Ordered execution plan

### BioAnalyzer first (steps 1-4)

- [ ] **1) Align outputs to design specs, especially ontology translation quality.**
  - Implementation note: this requires robust ontology mapping (EFO/UBERON/NCBITaxon) and should be validated against curated references.

- [ ] **2) Run on a small random sample from a structured PubMed search.**
  - Suggested runbook: produce/query PMIDs, sample randomly, run CLI/API batch analysis, export predictions CSV.

- [ ] **3) Benchmark quality/speed/cost to choose a practical model setup.**
  - Existing repo already includes benchmarking/evaluation scripts and tests; use those against sampled data.

- [ ] **4) Scale to 10k+ PubMed entries after model/quality confidence.**
  - Requires operational batch orchestration and monitoring.

### Curator-desk second (steps 5-7)

- [x] **5) Calculate priority scores (starting with simple sum).**
  - Implemented in `curator_table_r/R/data.R::priority_score()`.

- [~] **6) Set triage threshold to keep table size reasonable.**
  - Baseline documented (`Priority Score >= 4`) but final threshold requires exploratory data analysis.

- [~] **7) Automate updates to keep curator-desk current with PubMed.**
  - `curator_table_r/.github/workflows/quarto-publish.yml` is aligned to `main` for deploy.
  - Remaining work: connect upstream automated BioAnalyzer data refresh into curator-desk input updates.

## Notes

- This checklist is intentionally explicit about what is already implemented vs what depends on forthcoming BioAnalyzer validation and scale-up work.

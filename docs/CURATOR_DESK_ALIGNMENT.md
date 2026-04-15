# BioAnalyzer to Curator-Desk Alignment Plan

This note captures the current cross-repo sequencing agreed in curator-desk PR #13.

## Scope

- BioAnalyzer work happens first (data quality and ontology alignment).
- Curator-desk tuning (priority formula/threshold and automation) follows after prediction quality is validated.

## Agreed near-term priorities

1. Align BioAnalyzer outputs with the design spec, especially robust ontology translation for structured fields.
2. Run BioAnalyzer on a small random sample from a structured PubMed search.
3. Benchmark model quality, speed, and cost to choose a reliable/efficient model setup.
4. Scale BioAnalyzer runs to a larger PubMed batch once confidence is acceptable.

## Curator-desk follow-up (after BioAnalyzer validation)

5. Calculate priority scores in curator-desk (start simple, then refine).
6. Set a practical triage threshold based on exploratory analysis.
7. Automate refresh workflows to keep curator-desk current with PubMed updates.

## Current schema direction

- Do not treat `Taxa Level` as a required curator-desk prediction/status field.
- Keep priority scoring as a curator-desk concern (not a BioAnalyzer contract).

# Signature detection on screened papers

Papers analysed: 374 of 374 (missing: 0). Scored (screener label Yes or No): 345.

| | Screener: Yes | Screener: No |
|---|---|---|
| BioAnalyzer flags signature | 235 | 23 |
| BioAnalyzer does not flag | 10 | 77 |

- Recall (Yes papers flagged): 235/245 (96%)
- False-positive rate (No papers flagged): 23/100 (23%)
- Precision (flagged papers that are Yes): 235/258 (91%)
- Yes papers not yet in BugSigDB that are flagged: 170/180 (94%)

Flag confidence threshold sweep (flag AND confidence >= t):

| t | recall | false-positive rate | precision |
|---|---|---|---|
| 0.0 | 235/245 (96%) | 23/100 (23%) | 235/258 (91%) |
| 0.5 | 235/245 (96%) | 23/100 (23%) | 235/258 (91%) |
| 0.6 | 235/245 (96%) | 23/100 (23%) | 235/258 (91%) |
| 0.7 | 234/245 (96%) | 23/100 (23%) | 234/257 (91%) |
| 0.8 | 234/245 (96%) | 23/100 (23%) | 234/257 (91%) |
| 0.9 | 105/245 (43%) | 4/100 (4%) | 105/109 (96%) |

Not scored: (blank): 8/12 flagged, ?: 1/2 flagged, Maybe: 6/15 flagged

## Spot-check of disagreements (see disagreements.csv)

Confidence takes only four values (0.0, 0.6, 0.8, 1.0), so the 0.9 row above means "confidence 1.0": 105 Yes vs 4 No (96% precision, 43% recall). Useful for ranking, not as a cutoff.

**Flagged but screener said No (23):**
- 6 are indexed in PubMed as a review, systematic review or meta-analysis. None of the 245 Yes papers is a review, so excluding PubMed publication type Review would cut false positives to 17/100 with no loss of recall (precision 235/252, 93%). Publication types fetched from PubMed esummary for all 345 scored papers.
- 5 are methods/technical papers (protein extraction, sequencing platform, stool collection, PCR diagnostic accuracy, metabolome model), 2 are environmental resistome studies, 4 are lab or chemistry studies with no community comparison, and 2 more read like reviews but are not indexed as one (immune checkpoint inhibitors, GABA-modulating bacteria).
- 4 could plausibly contain a signature and are worth a curator's second look: Parkinson's mouse model (30099890), long-term erythromycin RCT (29669883), Prevotella-to-Bacteroides ratio RCT (28883543), Blastocystis subtypes (30171064).

**Screener said Yes but not flagged (10):** 8 compare an exposure, intervention, time point or sampling method rather than a disease (dairy intake, probiotic, breastfeeding, hypnotherapy, bowel preparation, 10-month variability, aflatoxin, patient- vs provider-collected swabs). The other 2 are oral malodour prediction and Cutibacterium acnes in the shoulder. The flag under-calls non-disease comparisons.

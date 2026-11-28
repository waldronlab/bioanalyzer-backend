## Make studies searchable by condition, host species and body site

Goal (Levi, 2026-11-18): a high-recall, searchable list of studies likely to contain a microbial signature, using PubMed data only. Pre-filled curation values are out of scope.

### What changes
- **Search tags.** `fields.{condition,host_species,body_site}.tags` lists every value the paper names, each with its ontology ID, and the main value comes first. A study is found by any of its conditions, hosts or body sites, not just the first one. The tags are in the JSON/API output. The curator-desk CSV is unchanged.
- **More specific condition terms.** The prompt keeps disease type and subtype ("alcoholic cirrhosis", not "cirrhosis"). Inverted MeSH headings are put back in natural order. A specific disease wins over a broad term it contains. When matching to the BugSigDB vocabulary replaces a term, the original term is also kept as a tag, but only for ontologies BugSigDB uses.
- **Fix:** live-OLS lookups of EFO terms used the wrong IRI, so OLS returned nothing for them.
- **`search-recall` scoring** (`scripts/eval/bugsigdb_ground_truth_benchmark.py search-recall`). For each field, it checks whether the paper is found by its BugSigDB-curated value. It scores three ways: by the main value only, by any tag, and by any tag whose ontology parents include the curated term. The third way is how an ontology-aware search would behave; the app itself doesn't expand searches to parent terms yet.

### Results
Two 100-paper BugSigDB test sets. Settings: PubMed abstract + MeSH only, gemini-2.5-flash, BugSigDB vocabulary with the test papers' own curations removed, 3 runs, mean (min–max).

| Found by | Fresh: main value | Fresh: tags + parents | Original: main value | Original: tags + parents |
|---|---|---|---|---|
| Condition | 0.62 (0.60–0.63) | **0.68** (0.66–0.69) | 0.63 (0.62–0.63) | **0.71** (0.70–0.72) |
| Body site | 0.76 (0.75–0.77) | **0.79** (0.77–0.80) | 0.81 | **0.84** |
| Host species | 0.96 (0.96–0.97) | **0.98** (0.98–0.99) | 0.97 | **0.99** |
| All three | 0.45 (0.44–0.47) | **0.51** (0.50–0.53) | 0.51 (0.50–0.51) | **0.60** (0.60–0.61) |

<!-- drag search_recall.png here -->

### Signature flag on screened papers
374 papers screened by curators for "contains signatures", analysed with normal settings (full BugSigDB vocabulary, PubMed only). Scored on the 345 marked Yes or No:

| | Screener: Yes (245) | Screener: No (100) |
|---|---|---|
| Flagged | 235 | 23 |
| Not flagged | 10 | 77 |

Recall 96%, false-positive rate 23%, precision 91%. 170 of the 180 Yes papers not yet in BugSigDB (PMID match against the BugSigDB export) are flagged.
- 6 of the 23 false positives are PubMed-indexed reviews or meta-analyses; none of the Yes papers is. Excluding them by publication type would bring false positives to 17% with no loss of recall (not in this PR).
- 8 of the 10 misses compare an exposure or intervention (diet, probiotic, breastfeeding, bowel preparation) rather than a disease.

### Known gap
22% of condition tags have no ontology ID. These are non-disease factors such as antibiotic exposure, chemotherapy and diet. Mapping them to the EFO/CHEBI terms BugSigDB uses is the next step.

### Tests
Full suite: 1087 passed, 1 skipped. The new tests cover tag building, the recall scorer, and the prompt-leakage guard (no test-set labels in the prompt examples).

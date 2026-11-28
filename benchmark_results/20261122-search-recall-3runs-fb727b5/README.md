# Search-recall benchmark, 3 repeats per set — commit fb727b5 (feat/search-recall)

Question: how often can a BugSigDB-curated study be *found* by its curated
condition / body site / host species, using PubMed data only (no full text)?

Settings (see each `*/settings.txt`): gemini-2.5-flash, temperature 0,
USE_FULLTEXT=0, INCLUDE_INDEX_TERMS=1 (MeSH + keywords), held-out BugSigDB
Condition vocabulary (`bugsigdb_condition_vocabulary.heldout200.json`, the
200 test papers' own curations removed). Only uncommitted change at run
time: comment deletions in scripts/cli_rendering.py (see commit.txt).

Test sets: `fresh` = benchmark_results/testset-fresh-20261113 (100 papers),
`original` = pmids.txt (100 papers). All 600 analyses completed (0 missing).

Results: summary_3runs.md (mean and min-max), per-run folders hold
results.json, summary.md/csv and misses.csv.

Reproduce: `scripts/run_repeats.sh <out_dir>` from the repo root.

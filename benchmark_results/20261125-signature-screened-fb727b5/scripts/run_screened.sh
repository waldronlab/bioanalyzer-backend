#!/usr/bin/env bash
# Signature detection on 374 screened papers (labels.csv "Contains signatures").
# Normal production settings (default BugSigDB vocabulary), PubMed data only.
# Resumable: re-running keeps earlier attempt files and only analyses missing PMIDs.
# Usage (repo root): benchmark_results/20261125-signature-screened-fb727b5/scripts/run_screened.sh
set -uo pipefail
cd /home/ronald/Desktop/BioAnalyzer-Backend
D=benchmark_results/20261125-signature-screened-fb727b5
git rev-parse HEAD > $D/commit.txt; git diff --quiet -- app scripts tests || { echo "WARNING: uncommitted changes:"; git diff --stat -- app scripts tests; } >> $D/commit.txt
[ -f $D/settings.txt ] || { echo "commit $(git rev-parse --short HEAD); started $(date -Is)"; docker exec bioanalyzer-package env | grep -E "^(BUGSIGDB_CONDITION_VOCAB_PATH|LLM_TEMPERATURE|USE_FULLTEXT|INCLUDE_INDEX_TERMS|DEFAULT_MODEL)=" | sort; } > $D/settings.txt
[ -f $D/results.json ] || cp $D/pmids.txt $D/missing.txt
merge() {
  python3 - "$D" <<'PY'
import glob, json, sys
d = sys.argv[1]
def items(p):
    try: x = json.load(open(p))
    except Exception: return []
    if isinstance(x, dict): x = x.get("results", [x])
    return [r for r in x if isinstance(r, dict) and r.get("pmid") and r.get("fields")]
by = {}
for p in sorted(glob.glob(f"{d}/attempt-*.json")):
    for r in items(p): by[str(r["pmid"])] = r
json.dump(list(by.values()), open(f"{d}/results.json", "w"), indent=1)
want = open(f"{d}/pmids.txt").read().split()
open(f"{d}/missing.txt", "w").write("\n".join(p for p in want if p not in by))
print(len(by))
PY
}
for a in 1 2 3 4 5 6; do
  grep -q . $D/missing.txt || break
  until docker exec bioanalyzer-package python -c "import requests; requests.get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?db=pubmed&retmode=json', timeout=20).raise_for_status()" >/dev/null 2>&1; do
    echo "$(date -Is) waiting for NCBI" >> $D/analyze.log; sleep 60; done
  BioAnalyzer analyze --file $D/missing.txt --format json --refresh -o $D/attempt-$(date +%Y%m%d%H%M%S).json >> $D/analyze.log 2>&1
  echo "attempt $a: $(merge) papers with results" >> $D/analyze.log
done
echo "DONE: $(python3 -c "import json;print(len(json.load(open('$D/results.json'))))") results, missing $(grep -c . $D/missing.txt)"

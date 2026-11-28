#!/usr/bin/env bash
# Search-recall benchmark, 3 repeats per set, on a committed feat/search-recall HEAD:
# PubMed-only, MeSH on, held-out Condition vocab, 1 run per test set, JSON output
# (keeps fields.*.tags), then `search-recall` scoring. Usage: run_repeats.sh <out_dir>
set -uo pipefail
cd /home/ronald/Desktop/BioAnalyzer-Backend
B=${1:?usage: run_repeats.sh <out_dir>}; mkdir -p $B
F=benchmark_results/testset-fresh-20261113
git rev-parse HEAD > $B/commit.txt; git diff --quiet -- app scripts tests || { echo "WARNING: uncommitted changes:"; git diff --stat -- app scripts tests; } >> $B/commit.txt

INCLUDE_INDEX_TERMS=1 BUGSIGDB_CONDITION_VOCAB_PATH=/app/cache/bugsigdb_condition_vocabulary.heldout200.json \
  docker compose -p bioanalyzer-package up -d --force-recreate bioanalyzer-package >/dev/null 2>&1
for i in $(seq 1 60); do curl -sf localhost:8000/health >/dev/null && break; sleep 3; done
curl -sf localhost:8000/health >/dev/null || { echo "API did not become healthy"; exit 1; }

wait_for_ncbi() {
  until docker exec bioanalyzer-package python -c "import requests; requests.get('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?db=pubmed&retmode=json', timeout=20).raise_for_status()" >/dev/null 2>&1; do
    echo "$(date -Is) waiting for NCBI" >> "$1/analyze.log"; sleep 60; done
}

# results.json <- merge of all attempt files; prints PMIDs still missing to missing.txt
merge() {
  python3 - "$1" "$2" <<'PY'
import glob, json, sys
d, pmids = sys.argv[1], sys.argv[2]
def items(p):
    try: x = json.load(open(p))
    except Exception: return []
    if isinstance(x, dict): x = x.get("results", [x])
    return [r for r in x if isinstance(r, dict) and r.get("pmid") and r.get("fields")]
by = {}
for p in sorted(glob.glob(f"{d}/attempt-*.json")):
    for r in items(p): by[str(r["pmid"])] = r
json.dump(list(by.values()), open(f"{d}/results.json", "w"), indent=1)
want = open(pmids).read().split()
open(f"{d}/missing.txt", "w").write("\n".join(p for p in want if p not in by))
print(len(by))
PY
}

run() {  # $1 name, $2 pmids, $3 ground truth
  D=$B/$1; mkdir -p $D
  [ -f $D/summary.md ] && { echo "== $1: already done"; return; }
  [ -f $D/settings.txt ] || { echo "commit $(git rev-parse --short HEAD); started $(date -Is)"; docker exec bioanalyzer-package env | grep -E "^(BUGSIGDB_CONDITION_VOCAB_PATH|LLM_TEMPERATURE|USE_FULLTEXT|INCLUDE_INDEX_TERMS|DEFAULT_MODEL)=" | sort; } > $D/settings.txt
  [ -f $D/results.json ] || cp "$2" $D/missing.txt  # resume: keep earlier attempts
  for a in 1 2 3 4 5 6; do
    grep -q . $D/missing.txt || break
    wait_for_ncbi $D
    BioAnalyzer analyze --file $D/missing.txt --format json --refresh -o $D/attempt-$(date +%Y%m%d%H%M%S).json >> $D/analyze.log 2>&1
    echo "attempt $a: $(merge $D $2) papers with results" >> $D/analyze.log
  done
  python3 scripts/eval/bugsigdb_ground_truth_benchmark.py search-recall --results $D/results.json \
    --ground-truth "$3" --out $D > $D/search_recall.log 2>&1
  echo "== $1: $(python3 -c "import json;print(len(json.load(open('$D/results.json'))))") results, missing $(grep -c . $D/missing.txt) $(date +%H:%M)"
}
for r in 1 2 3; do
  run fresh-r$r $F/pmids.txt $F/pmids.ground_truth.json
  run original-r$r pmids.txt pmids.ground_truth.json
done
echo ALL_DONE

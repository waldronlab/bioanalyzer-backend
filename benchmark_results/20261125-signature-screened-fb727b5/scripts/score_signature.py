"""Score BioAnalyzer's "contains a microbial signature" flag (has_differential_abundance)
against the screeners' "Contains signatures" labels. Only Yes/No papers are scored;
Maybe, ?, and blank are listed but not counted.

Usage (repo root):
  python3 benchmark_results/20261125-signature-screened-fb727b5/scripts/score_signature.py
"""

import csv
import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent
labels = {r["PMID"]: r for r in csv.DictReader(open(D / "labels.csv", encoding="utf-8"))}
results = {str(r["pmid"]): r for r in json.load(open(D / "results.json", encoding="utf-8"))}


def flag(r):
    return bool(r.get("has_differential_abundance"))


def conf(r):
    try:
        return float(r.get("differential_abundance_confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


rows, missing = [], []
for pmid, lab in labels.items():
    r = results.get(pmid)
    if r is None:
        missing.append(pmid)
        continue
    rows.append((pmid, lab, r))

scored = [(p, lab, r) for p, lab, r in rows if lab["Contains signatures"] in ("Yes", "No")]
pos = [x for x in scored if x[1]["Contains signatures"] == "Yes"]
neg = [x for x in scored if x[1]["Contains signatures"] == "No"]
tp = sum(flag(r) for _, _, r in pos)
fp = sum(flag(r) for _, _, r in neg)
fn, tn = len(pos) - tp, len(neg) - fp


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"


out = ["# Signature detection on screened papers", ""]
out.append(f"Papers analysed: {len(rows)} of {len(labels)} (missing: {len(missing)}). "
           f"Scored (screener label Yes or No): {len(scored)}.")
out.append("")
out.append("| | Screener: Yes | Screener: No |")
out.append("|---|---|---|")
out.append(f"| BioAnalyzer flags signature | {tp} | {fp} |")
out.append(f"| BioAnalyzer does not flag | {fn} | {tn} |")
out.append("")
out.append(f"- Recall (Yes papers flagged): {pct(tp, len(pos))}")
out.append(f"- False-positive rate (No papers flagged): {pct(fp, len(neg))}")
out.append(f"- Precision (flagged papers that are Yes): {pct(tp, tp + fp)}")
uncur = [x for x in pos if x[1]["In BugSigDB dump"] == "no"]
out.append(f"- Yes papers not yet in BugSigDB that are flagged: "
           f"{pct(sum(flag(r) for _, _, r in uncur), len(uncur))}")
out.append("")
out.append("Flag confidence threshold sweep (flag AND confidence >= t):")
out.append("")
out.append("| t | recall | false-positive rate | precision |")
out.append("|---|---|---|---|")
for t in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
    tp_t = sum(flag(r) and conf(r) >= t for _, _, r in pos)
    fp_t = sum(flag(r) and conf(r) >= t for _, _, r in neg)
    out.append(f"| {t:.1f} | {pct(tp_t, len(pos))} | {pct(fp_t, len(neg))} | {pct(tp_t, tp_t + fp_t)} |")
other = {}
for _, lab, r in rows:
    k = lab["Contains signatures"]
    if k not in ("Yes", "No"):
        other.setdefault(k or "(blank)", [0, 0])
        other[k or "(blank)"][0] += 1
        other[k or "(blank)"][1] += flag(r)
out.append("")
out.append("Not scored: " + ", ".join(f"{k}: {v[1]}/{v[0]} flagged" for k, v in sorted(other.items())))
(D / "summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")

with open(D / "disagreements.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["PMID", "Screener", "BioAnalyzer flag", "Confidence", "Title",
                "Screener condition", "BioAnalyzer condition", "In BugSigDB dump"])
    for p, lab, r in scored:
        if flag(r) != (lab["Contains signatures"] == "Yes"):
            cond = ((r.get("fields") or {}).get("condition") or {}).get("value") or ""
            w.writerow([p, lab["Contains signatures"], "yes" if flag(r) else "no", conf(r),
                        r.get("title", ""), lab["Condition (screener)"], cond,
                        lab["In BugSigDB dump"]])
print("\n".join(out))

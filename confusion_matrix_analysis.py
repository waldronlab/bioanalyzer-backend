#!/usr/bin/env python3
"""
Formal validation of BioAnalyzer predictions using
confusion matrices and Matthews Correlation Coefficient (MCC).
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, matthews_corrcoef

CLASSES = ["ABSENT", "PARTIALLY_PRESENT", "PRESENT"]

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (10, 8)


def load_data(predictions: Path, feedback: Path):
    return pd.read_csv(predictions), pd.read_csv(feedback)


def merge_on_pmid(pred_df, fb_df):
    merged = pred_df.merge(fb_df, on="PMID", suffixes=("_predicted", "_actual"))
    if merged.empty:
        raise ValueError("No overlapping PMIDs found.")
    return merged


def binary_mcc(y_true, y_pred):
    y_true_bin = (y_true == "PRESENT").astype(int)
    y_pred_bin = (y_pred == "PRESENT").astype(int)
    return matthews_corrcoef(y_true_bin, y_pred_bin)


def multiclass_mcc(y_true, y_pred):
    return matthews_corrcoef(y_true, y_pred)


def analyze_variable(df, variable):
    yt = df[f"{variable}_actual"].dropna()
    yp = df[f"{variable}_predicted"].dropna()

    mask = yt.index.intersection(yp.index)
    yt, yp = yt.loc[mask], yp.loc[mask]

    cm = confusion_matrix(yt, yp, labels=CLASSES)

    return {
        "variable": variable,
        "n": len(yt),
        "accuracy": float((yt == yp).mean()),
        "mcc_binary": float(binary_mcc(yt, yp)),
        "mcc_multiclass": float(multiclass_mcc(yt, yp)),
        "confusion_matrix": cm.tolist(),
    }


def plot_cm(cm, variable, out):
    cmn = cm / cm.sum(axis=1, keepdims=True)
    sns.heatmap(cmn, annot=True, fmt=".2%", xticklabels=CLASSES, yticklabels=CLASSES)
    plt.title(variable)
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.tight_layout()
    plt.savefig(out, dpi=300)
    plt.close()


def main():
    preds, fb = load_data(
        Path("analysis_results.csv"),
        Path("feedback.csv"),
    )
    merged = merge_on_pmid(preds, fb)

    outdir = Path("confusion_matrix_results")
    outdir.mkdir(exist_ok=True)

    variables = [
        "Host Species Status",
        "Body Site Status",
        "Condition Status",
        "Sequencing Type Status",
        "Taxa Level Status",
        "Sample Size Status",
    ]

    results = []
    for v in variables:
        r = analyze_variable(merged, v)
        results.append(r)
        plot_cm(np.array(r["confusion_matrix"]), v, outdir / f"{v.replace(' ', '_')}.png")

    pd.DataFrame(results).to_csv(outdir / "summary_metrics.csv", index=False)
    json.dump(results, open(outdir / "detailed_results.json", "w"), indent=2)

    print("Validation complete. Results in:", outdir)


if __name__ == "__main__":
    main()

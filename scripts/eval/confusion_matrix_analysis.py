#!/usr/bin/env python3
"""
Formal validation of BioAnalyzer predictions using confusion matrices.

Following guidance from Levi Waldron:
- Include "PARTIALLY_PRESENT" as a separate row/column in the confusion matrix
- Hold off on MCC calculations for now (will help inform whether "partially present"
  is more likely to be present or absent by comparison to gold standard reference)

Predictions input must be generated with `--format detailed_csv` (the
Status-inclusive export over all ANALYSIS_FIELDS), not `--format csv` (nor
its `curator_desk_csv` alias) — those are the simplified, curator-facing
schema (Host Species/Body Site/Condition/Sample Size/Sequencing Type/
Differential Abundance/In bsgdb) and no longer carry per-field
PRESENT/PARTIALLY_PRESENT/ABSENT Status columns, which this script requires.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix

CLASSES = ["ABSENT", "PARTIALLY_PRESENT", "PRESENT"]

sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (10, 8)


def load_data(predictions: Path, feedback: Path):
    """Load prediction and feedback CSV files."""
    pred_df = pd.read_csv(predictions)
    fb_df = pd.read_csv(feedback)

    # Validate required columns
    required_cols = ["PMID"]
    for col in required_cols:
        if col not in pred_df.columns:
            raise ValueError(f"Missing required column '{col}' in predictions file")
        if col not in fb_df.columns:
            raise ValueError(f"Missing required column '{col}' in feedback file")

    return pred_df, fb_df


def merge_on_pmid(pred_df, fb_df):
    """Merge prediction and feedback dataframes on PMID."""
    merged = pred_df.merge(
        fb_df, on="PMID", suffixes=("_predicted", "_actual"), how="inner"
    )

    if merged.empty:
        pred_pmids = set(pred_df["PMID"].unique())
        fb_pmids = set(fb_df["PMID"].unique())
        overlap = pred_pmids.intersection(fb_pmids)

        raise ValueError(
            f"No overlapping PMIDs found after merge.\n"
            f"Predictions file has {len(pred_pmids)} unique PMIDs.\n"
            f"Feedback file has {len(fb_pmids)} unique PMIDs.\n"
            f"Overlapping PMIDs: {len(overlap)}\n"
            f"Please ensure both files contain matching PMIDs for comparison."
        )

    print(f"Successfully merged {len(merged)} rows with overlapping PMIDs.")
    return merged


def analyze_variable(df, variable):
    """
    Analyze a single variable by comparing predicted vs actual status.

    Args:
        df: Merged dataframe with predicted and actual columns
        variable: Variable name (e.g., "Host Species Status")

    Returns:
        Dictionary with analysis results including confusion matrix
    """
    pred_col = f"{variable}_predicted"
    actual_col = f"{variable}_actual"

    if pred_col not in df.columns:
        raise ValueError(f"Column '{pred_col}' not found in merged dataframe")
    if actual_col not in df.columns:
        raise ValueError(f"Column '{actual_col}' not found in merged dataframe")

    # Get non-null values from both columns
    yt = df[actual_col].dropna()
    yp = df[pred_col].dropna()

    # Find common indices (rows where both predicted and actual are not null)
    mask = yt.index.intersection(yp.index)
    yt = yt.loc[mask]
    yp = yp.loc[mask]

    if len(yt) == 0:
        print(f"Warning: No valid data points for {variable}")
        return {
            "variable": variable,
            "n": 0,
            "accuracy": None,
            "confusion_matrix": [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
        }

    # Validate that all values are in CLASSES
    invalid_actual = set(yt.unique()) - set(CLASSES)
    invalid_pred = set(yp.unique()) - set(CLASSES)

    if invalid_actual:
        print(
            f"Warning: Found invalid values in actual data for {variable}: {invalid_actual}"
        )
    if invalid_pred:
        print(
            f"Warning: Found invalid values in predicted data for {variable}: {invalid_pred}"
        )

    # Create confusion matrix with PARTIALLY_PRESENT as separate class
    cm = confusion_matrix(yt, yp, labels=CLASSES)

    # Calculate accuracy
    accuracy = float((yt == yp).mean())

    return {
        "variable": variable,
        "n": len(yt),
        "accuracy": accuracy,
        "confusion_matrix": cm.tolist(),
    }


def plot_cm(cm, variable, out):
    """
    Plot normalized confusion matrix as heatmap.

    Args:
        cm: Confusion matrix (numpy array)
        variable: Variable name for title
        out: Output file path
    """
    # Normalize by row (actual) to show percentages
    cm_sum = cm.sum(axis=1, keepdims=True)
    # Avoid division by zero
    cm_sum[cm_sum == 0] = 1
    cmn = cm / cm_sum

    # Create heatmap
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(
        cmn,
        annot=True,
        fmt=".2%",
        xticklabels=CLASSES,
        yticklabels=CLASSES,
        cmap="Blues",
        cbar_kws={"label": "Percentage"},
        ax=ax,
    )
    ax.set_title(f"Confusion Matrix: {variable}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Predicted", fontsize=12)
    ax.set_ylabel("Actual", fontsize=12)
    plt.tight_layout()
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()

    # Also save raw counts version
    out_counts = out.parent / f"{out.stem}_counts{out.suffix}"
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        xticklabels=CLASSES,
        yticklabels=CLASSES,
        cmap="Blues",
        cbar_kws={"label": "Count"},
        ax=ax,
    )
    ax.set_title(
        f"Confusion Matrix (Counts): {variable}", fontsize=14, fontweight="bold"
    )
    ax.set_xlabel("Predicted", fontsize=12)
    ax.set_ylabel("Actual", fontsize=12)
    plt.tight_layout()
    plt.savefig(out_counts, dpi=300, bbox_inches="tight")
    plt.close()


def main():
    """Main function to run confusion matrix analysis."""
    import sys

    # Allow command-line arguments for file paths
    if len(sys.argv) >= 3:
        predictions_path = Path(sys.argv[1])
        feedback_path = Path(sys.argv[2])
    else:
        predictions_path = Path("analysis_results.csv")
        feedback_path = Path("feedback.csv")

    # Validate input files exist
    if not predictions_path.exists():
        raise FileNotFoundError(f"Predictions file not found: {predictions_path}")
    if not feedback_path.exists():
        raise FileNotFoundError(f"Feedback file not found: {feedback_path}")

    print(f"Loading predictions from: {predictions_path}")
    print(f"Loading feedback from: {feedback_path}")

    preds, fb = load_data(predictions_path, feedback_path)
    merged = merge_on_pmid(preds, fb)

    outdir = Path("confusion_matrix_results")
    outdir.mkdir(exist_ok=True)
    print(f"Output directory: {outdir.absolute()}")

    variables = [
        "Host Species Status",
        "Body Site Status",
        "Condition Status",
        "Sequencing Type Status",
        "Sample Size Status",
    ]

    results = []
    for v in variables:
        print(f"\nAnalyzing {v}...")
        try:
            r = analyze_variable(merged, v)
            results.append(r)
            print(f"  - Sample size: {r['n']}")
            print(
                f"  - Accuracy: {r['accuracy']:.3f}"
                if r["accuracy"] is not None
                else "  - Accuracy: N/A"
            )

            # Plot confusion matrix
            cm_array = np.array(r["confusion_matrix"])
            plot_cm(cm_array, v, outdir / f"{v.replace(' ', '_')}.png")
            print(f"  - Saved plots to {outdir}")
        except Exception as e:
            print(f"  - Error analyzing {v}: {e}")
            continue

    # Save summary results
    summary_df = pd.DataFrame(results)
    summary_path = outdir / "summary_metrics.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\nSaved summary metrics to: {summary_path}")

    # Save detailed JSON results
    detailed_path = outdir / "detailed_results.json"
    with open(detailed_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved detailed results to: {detailed_path}")

    print(f"\n{'='*60}")
    print("Validation complete!")
    print(f"Results saved in: {outdir.absolute()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

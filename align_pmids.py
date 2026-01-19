#!/usr/bin/env python3
"""
Helper script to align PMIDs between predictions and feedback files.

This script helps ensure both CSV files have overlapping PMIDs for confusion matrix analysis.
"""

import pandas as pd
import sys
from pathlib import Path


def align_pmids(predictions_path, feedback_path, output_dir=None):
    """
    Align PMIDs between predictions and feedback files.
    
    Options:
    1. Filter predictions to match feedback PMIDs
    2. Filter feedback to match prediction PMIDs
    3. Find intersection and create aligned files
    """
    print("Loading files...")
    preds = pd.read_csv(predictions_path)
    fb = pd.read_csv(feedback_path)
    
    pred_pmids = set(preds["PMID"].unique())
    fb_pmids = set(fb["PMID"].unique())
    overlap = pred_pmids.intersection(fb_pmids)
    
    print(f"\nData Summary:")
    print(f"  Predictions file: {len(pred_pmids)} unique PMIDs")
    print(f"  Feedback file: {len(fb_pmids)} unique PMIDs")
    print(f"  Overlapping PMIDs: {len(overlap)}")
    
    if len(overlap) == 0:
        print("\n⚠️  WARNING: No overlapping PMIDs found!")
        print("You need to align the data before running confusion matrix analysis.")
        return
    
    if output_dir is None:
        output_dir = Path(".")
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
    
    # Create aligned files
    preds_aligned = preds[preds["PMID"].isin(overlap)].copy()
    fb_aligned = fb[fb["PMID"].isin(overlap)].copy()
    
    preds_output = output_dir / "analysis_results_aligned.csv"
    fb_output = output_dir / "feedback_aligned.csv"
    
    preds_aligned.to_csv(preds_output, index=False)
    fb_aligned.to_csv(fb_output, index=False)
    
    print(f"\n✅ Created aligned files:")
    print(f"  {preds_output} ({len(preds_aligned)} rows)")
    print(f"  {fb_output} ({len(fb_aligned)} rows)")
    print(f"\nYou can now run confusion_matrix_analysis.py with these aligned files:")
    print(f"  python confusion_matrix_analysis.py {preds_output} {fb_output}")
    
    # Show sample overlapping PMIDs
    if len(overlap) <= 10:
        print(f"\nOverlapping PMIDs: {sorted(overlap)}")
    else:
        print(f"\nSample overlapping PMIDs (first 10): {sorted(list(overlap))[:10]}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python align_pmids.py <predictions.csv> <feedback.csv> [output_dir]")
        print("\nExample:")
        print("  python align_pmids.py analysis_results.csv feedback.csv")
        sys.exit(1)
    
    predictions_path = Path(sys.argv[1])
    feedback_path = Path(sys.argv[2])
    output_dir = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not predictions_path.exists():
        print(f"Error: Predictions file not found: {predictions_path}")
        sys.exit(1)
    
    if not feedback_path.exists():
        print(f"Error: Feedback file not found: {feedback_path}")
        sys.exit(1)
    
    align_pmids(predictions_path, feedback_path, output_dir)

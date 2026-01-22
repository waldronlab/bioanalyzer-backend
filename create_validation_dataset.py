#!/usr/bin/env python3
"""
Create validation dataset in the format requested by Levi:
Study, PMID, Experiment, Outcome of the experiment, Prediction

Where:
- Study: Paper identifier (PMID or title)
- PMID: PubMed ID
- Experiment: Field being evaluated (e.g., "Host Species Status")
- Outcome of the experiment: Ground truth from expert curator (PRESENT/ABSENT/PARTIALLY_PRESENT)
- Prediction: BioAnalyzer prediction (PRESENT/ABSENT/PARTIALLY_PRESENT)
"""

import pandas as pd
import sys
from pathlib import Path


def create_validation_dataset(predictions_path, feedback_path, output_path=None):
    """
    Create validation dataset in requested format.
    
    Args:
        predictions_path: Path to BioAnalyzer predictions CSV
        feedback_path: Path to expert curator annotations CSV
        output_path: Output CSV path (default: validation_dataset.csv)
    """
    print("Loading data...")
    preds = pd.read_csv(predictions_path)
    fb = pd.read_csv(feedback_path)
    
    # Merge on PMID
    merged = preds.merge(fb, on="PMID", suffixes=("_predicted", "_actual"), how="inner")
    
    if merged.empty:
        raise ValueError("No overlapping PMIDs found between predictions and feedback files")
    
    print(f"Merged {len(merged)} papers with overlapping PMIDs")
    
    # Define fields to extract
    fields = [
        "Host Species Status",
        "Body Site Status",
        "Condition Status",
        "Sequencing Type Status",
        "Taxa Level Status",
        "Sample Size Status",
    ]
    
    # Create list to store results
    results = []
    
    # Get title for study identifier
    title_col = "Title_predicted" if "Title_predicted" in merged.columns else "Title_actual"
    if title_col not in merged.columns:
        title_col = None
    
    # Process each paper and field
    for idx, row in merged.iterrows():
        pmid = row["PMID"]
        study_id = row[title_col] if title_col and pd.notna(row[title_col]) else f"PMID_{pmid}"
        
        for field in fields:
            pred_col = f"{field}_predicted"
            actual_col = f"{field}_actual"
            
            # Skip if either value is missing
            if pred_col not in merged.columns or actual_col not in merged.columns:
                continue
            
            outcome = row[actual_col]
            prediction = row[pred_col]
            
            # Skip if either is NaN
            if pd.isna(outcome) or pd.isna(prediction):
                continue
            
            results.append({
                "Study": study_id,
                "PMID": pmid,
                "Experiment": field,
                "Outcome of the experiment": outcome,  # Ground truth
                "Prediction": prediction  # BioAnalyzer prediction
            })
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    # Set output path
    if output_path is None:
        output_path = Path("validation_dataset.csv")
    else:
        output_path = Path(output_path)
    
    # Save to CSV
    df.to_csv(output_path, index=False)
    
    print(f"\nCreated validation dataset: {output_path}")
    print(f"Total rows: {len(df)}")
    print(f"Unique papers: {df['PMID'].nunique()}")
    print(f"Fields: {df['Experiment'].nunique()}")
    print(f"\nFirst few rows:")
    print(df.head(10).to_string())
    
    # Summary statistics
    print(f"\n{'='*60}")
    print("Summary Statistics:")
    print(f"{'='*60}")
    print(f"\nBy Field:")
    for field in fields:
        field_data = df[df['Experiment'] == field]
        if len(field_data) > 0:
            accuracy = (field_data['Outcome of the experiment'] == field_data['Prediction']).mean()
            print(f"  {field}: {len(field_data)} comparisons, {accuracy:.1%} accuracy")
    
    print(f"\nBy Outcome (Ground Truth):")
    for outcome in ["ABSENT", "PARTIALLY_PRESENT", "PRESENT"]:
        outcome_data = df[df['Outcome of the experiment'] == outcome]
        if len(outcome_data) > 0:
            accuracy = (outcome_data['Outcome of the experiment'] == outcome_data['Prediction']).mean()
            print(f"  {outcome}: {len(outcome_data)} cases, {accuracy:.1%} accuracy")
    
    print(f"\nOverall Accuracy: {(df['Outcome of the experiment'] == df['Prediction']).mean():.1%}")
    
    return df


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python create_validation_dataset.py <predictions.csv> <feedback.csv> [output.csv]")
        print("\nExample:")
        print("  python create_validation_dataset.py new.csv feedback.csv validation_dataset.csv")
        sys.exit(1)
    
    predictions_path = Path(sys.argv[1])
    feedback_path = Path(sys.argv[2])
    output_path = sys.argv[3] if len(sys.argv) > 3 else None
    
    if not predictions_path.exists():
        print(f"Error: Predictions file not found: {predictions_path}")
        sys.exit(1)
    
    if not feedback_path.exists():
        print(f"Error: Feedback file not found: {feedback_path}")
        sys.exit(1)
    
    create_validation_dataset(predictions_path, feedback_path, output_path)

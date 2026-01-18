#!/usr/bin/env python3
"""
Confusion Matrix and Matthew's Correlation Coefficient Analysis

This script compares BioAnalyzer predictions (analysis_results.csv) with
curator feedback (feedback.csv) to generate confusion matrices and calculate
MCC for each variable.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, matthews_corrcoef
from pathlib import Path
import json
from typing import Dict, Tuple, List

# Set style for better-looking plots
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 8)


def load_data(analysis_file: str, feedback_file: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load and prepare the analysis results and feedback data."""
    print("Loading data files...")
    analysis_df = pd.read_csv(analysis_file)
    feedback_df = pd.read_csv(feedback_file)
    
    print(f"Analysis results: {len(analysis_df)} records")
    print(f"Feedback data: {len(feedback_df)} records")
    
    return analysis_df, feedback_df


def merge_data(analysis_df: pd.DataFrame, feedback_df: pd.DataFrame) -> pd.DataFrame:
    """Merge analysis results with feedback data on PMID."""
    print("\nMerging data on PMID...")
    
    # Merge on PMID, keeping only records that exist in both
    merged = analysis_df.merge(
        feedback_df,
        on='PMID',
        suffixes=('_predicted', '_actual'),
        how='inner'
    )
    
    print(f"Matched records: {len(merged)}")
    
    if len(merged) == 0:
        raise ValueError("No matching PMIDs found between the two files!")
    
    return merged


def calculate_binary_mcc(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calculate MCC for binary classification (PRESENT vs not PRESENT).
    Treats PARTIALLY_PRESENT as a separate category initially.
    """
    # Convert to binary: PRESENT = 1, everything else = 0
    y_true_binary = (y_true == 'PRESENT').astype(int)
    y_pred_binary = (y_pred == 'PRESENT').astype(int)
    
    return matthews_corrcoef(y_true_binary, y_pred_binary)


def calculate_multiclass_mcc(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calculate MCC for multi-class classification.
    Maps PRESENT=2, PARTIALLY_PRESENT=1, ABSENT=0
    """
    status_map = {'ABSENT': 0, 'PARTIALLY_PRESENT': 1, 'PRESENT': 2}
    
    y_true_mapped = np.array([status_map.get(s, 0) for s in y_true])
    y_pred_mapped = np.array([status_map.get(s, 0) for s in y_pred])
    
    return matthews_corrcoef(y_true_mapped, y_pred_mapped)


def create_confusion_matrix_data(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[np.ndarray, List[str]]:
    """Create confusion matrix with all three classes."""
    classes = ['ABSENT', 'PARTIALLY_PRESENT', 'PRESENT']
    
    # Filter out any NaN values
    mask = ~(pd.isna(y_true) | pd.isna(y_pred))
    y_true_clean = y_true[mask]
    y_pred_clean = y_pred[mask]
    
    cm = confusion_matrix(
        y_true_clean,
        y_pred_clean,
        labels=classes
    )
    
    return cm, classes


def plot_confusion_matrix(cm: np.ndarray, classes: List[str], variable_name: str, 
                         save_path: str = None) -> None:
    """Plot a confusion matrix with annotations."""
    plt.figure(figsize=(10, 8))
    
    # Normalize confusion matrix to show percentages
    cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
    cm_normalized = np.nan_to_num(cm_normalized)
    
    # Create heatmap
    sns.heatmap(
        cm_normalized,
        annot=True,
        fmt='.2%',
        cmap='Blues',
        xticklabels=classes,
        yticklabels=classes,
        cbar_kws={'label': 'Normalized Frequency'},
        annot_kws={'size': 12}
    )
    
    plt.title(f'Confusion Matrix: {variable_name}\n(Normalized)', fontsize=16, fontweight='bold')
    plt.ylabel('Actual (Curator)', fontsize=12)
    plt.xlabel('Predicted (BioAnalyzer)', fontsize=12)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"  Saved confusion matrix plot: {save_path}")
    
    plt.close()


def analyze_variable(merged_df: pd.DataFrame, variable: str) -> Dict:
    """Analyze a single variable and return metrics."""
    print(f"\nAnalyzing variable: {variable}")
    
    pred_col = f"{variable}_predicted"
    actual_col = f"{variable}_actual"
    
    if pred_col not in merged_df.columns or actual_col not in merged_df.columns:
        print(f"  Warning: Columns not found for {variable}")
        return None
    
    y_pred = merged_df[pred_col].values
    y_actual = merged_df[actual_col].values
    
    # Remove NaN values
    mask = ~(pd.isna(y_actual) | pd.isna(y_pred))
    y_pred_clean = y_pred[mask]
    y_actual_clean = y_actual[mask]
    
    if len(y_pred_clean) == 0:
        print(f"  Warning: No valid data for {variable}")
        return None
    
    # Create confusion matrix
    cm, classes = create_confusion_matrix_data(y_actual_clean, y_pred_clean)
    
    # Calculate MCCs
    mcc_binary = calculate_binary_mcc(y_actual_clean, y_pred_clean)
    mcc_multiclass = calculate_multiclass_mcc(y_actual_clean, y_pred_clean)
    
    # Calculate accuracy
    accuracy = np.sum(y_actual_clean == y_pred_clean) / len(y_actual_clean)
    
    # Calculate per-class metrics
    results = {
        'variable': variable,
        'confusion_matrix': cm.tolist(),
        'classes': classes,
        'mcc_binary': float(mcc_binary),
        'mcc_multiclass': float(mcc_multiclass),
        'accuracy': float(accuracy),
        'n_samples': int(len(y_pred_clean)),
        'class_distribution_actual': {
            cls: int(np.sum(y_actual_clean == cls)) for cls in classes
        },
        'class_distribution_predicted': {
            cls: int(np.sum(y_pred_clean == cls)) for cls in classes
        }
    }
    
    print(f"  Samples: {results['n_samples']}")
    print(f"  Accuracy: {results['accuracy']:.3f}")
    print(f"  MCC (Binary): {results['mcc_binary']:.3f}")
    print(f"  MCC (Multi-class): {results['mcc_multiclass']:.3f}")
    
    return results


def generate_summary_report(all_results: List[Dict], output_file: str) -> None:
    """Generate a summary report with all metrics."""
    print("\n" + "="*80)
    print("SUMMARY REPORT")
    print("="*80)
    
    # Create summary DataFrame
    summary_data = []
    for result in all_results:
        if result is None:
            continue
        summary_data.append({
            'Variable': result['variable'],
            'N Samples': result['n_samples'],
            'Accuracy': f"{result['accuracy']:.3f}",
            'MCC (Binary)': f"{result['mcc_binary']:.3f}",
            'MCC (Multi-class)': f"{result['mcc_multiclass']:.3f}"
        })
    
    summary_df = pd.DataFrame(summary_data)
    print("\n" + summary_df.to_string(index=False))
    
    # Save to CSV
    summary_df.to_csv(output_file, index=False)
    print(f"\nSummary saved to: {output_file}")


def main():
    """Main analysis function."""
    # File paths
    analysis_file = Path("analysis_results.csv")
    feedback_file = Path("feedback.csv")
    output_dir = Path("confusion_matrix_results")
    output_dir.mkdir(exist_ok=True)
    
    # Variables to analyze
    variables = [
        'Host Species Status',
        'Body Site Status',
        'Condition Status',
        'Sequencing Type Status',
        'Taxa Level Status',
        'Sample Size Status'
    ]
    
    # Load and merge data
    analysis_df, feedback_df = load_data(analysis_file, feedback_file)
    merged_df = merge_data(analysis_df, feedback_df)
    
    # Analyze each variable
    all_results = []
    
    for variable in variables:
        result = analyze_variable(merged_df, variable)
        if result:
            all_results.append(result)
            
            # Plot confusion matrix
            cm = np.array(result['confusion_matrix'])
            plot_path = output_dir / f"confusion_matrix_{variable.replace(' ', '_')}.png"
            plot_confusion_matrix(cm, result['classes'], variable, str(plot_path))
    
    # Generate summary report
    summary_file = output_dir / "summary_metrics.csv"
    generate_summary_report(all_results, str(summary_file))
    
    # Save detailed results as JSON
    json_file = output_dir / "detailed_results.json"
    with open(json_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nDetailed results saved to: {json_file}")
    
    # Create a comprehensive comparison table
    comparison_file = output_dir / "comparison_table.csv"
    comparison_data = []
    for result in all_results:
        if result is None:
            continue
        for i, actual_class in enumerate(result['classes']):
            for j, pred_class in enumerate(result['classes']):
                count = result['confusion_matrix'][i][j]
                comparison_data.append({
                    'Variable': result['variable'],
                    'Actual': actual_class,
                    'Predicted': pred_class,
                    'Count': count
                })
    
    comparison_df = pd.DataFrame(comparison_data)
    comparison_df.to_csv(comparison_file, index=False)
    print(f"Comparison table saved to: {comparison_file}")
    
    print("\n" + "="*80)
    print("Analysis complete!")
    print(f"Results saved in: {output_dir}")
    print("="*80)


if __name__ == "__main__":
    main()

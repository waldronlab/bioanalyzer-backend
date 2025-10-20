#!/usr/bin/env python3

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np

from app.services.preprocessing import TextPreprocessor
from app.models.model import MicrobeSigClassifier, ModelTrainer, PaperDataset
from app.utils.utils import config, get_sequencing_types, get_body_sites, format_prediction_output

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_pmids(filepath: str) -> List[str]:
    """Load PMIDs from a file.
    
    Args:
        filepath: Path to file containing PMIDs
        
    Returns:
        List of PMIDs
    """
    with open(filepath, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def save_predictions(predictions: List[Dict], output_path: str):
    """Save predictions to a JSON file.
    
    Args:
        predictions: List of prediction dictionaries
        output_path: Path to save predictions
    """
    with open(output_path, 'w') as f:
        json.dump(predictions, f, indent=2)

def train_model(
    retriever,
    preprocessor: TextPreprocessor,
    model_path: Optional[str] = None
) -> MicrobeSigClassifier:
    """Train the classification model.
    
    Args:
        retriever: PubMed data retriever
        preprocessor: Text preprocessor
        model_path: Optional path to save model
        
    Returns:
        Trained model
    """
    logger.info("Loading training data...")
    
    # Get positive examples from BugSigDB
    positive_pmids = retriever.get_bugsigdb_pmids()
    
    # Get negative examples
    negative_pmids = retriever.get_negative_examples(len(positive_pmids))
    
    # Combine and shuffle PMIDs
    all_pmids = positive_pmids + negative_pmids
    np.random.shuffle(all_pmids)
    
    # Create labels
    signature_labels = torch.tensor([1] * len(positive_pmids) + [0] * len(negative_pmids))
    
    # Get metadata and full texts
    metadata_list = []
    full_texts = []
    
    for pmid in all_pmids:
        metadata = retriever.get_paper_metadata(pmid)
        full_text = retriever.get_pmc_fulltext(pmid)
        
        metadata_list.append(metadata)
        full_texts.append(full_text)
    
    # Prepare features
    embeddings, additional_features = preprocessor.prepare_batch(metadata_list, full_texts)
    
    # Create random labels for sequencing type and body site (for demonstration)
    # In practice, these would come from labeled data
    num_samples = len(all_pmids)
    sequencing_labels = torch.randint(0, len(get_sequencing_types()), (num_samples,))
    body_site_labels = torch.randint(0, len(get_body_sites()), (num_samples,))
    
    # Create dataset
    dataset = PaperDataset(
        embeddings=embeddings,
        additional_features=additional_features,
        labels={
            "signature_label": signature_labels,
            "sequencing_label": sequencing_labels,
            "body_site_label": body_site_labels
        }
    )
    
    # Split into train and validation sets
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    
    train_dataset, val_dataset = torch.utils.data.random_split(
        dataset,
        [train_size, val_size]
    )
    
    # Create data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.BATCH_SIZE,
        shuffle=True
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=config.BATCH_SIZE
    )
    
    # Initialize and train model
    model = MicrobeSigClassifier()
    trainer = ModelTrainer(model)
    
    logger.info("Training model...")
    history = trainer.train(train_loader, val_loader)
    
    # Save model if path provided
    if model_path:
        torch.save(model.state_dict(), model_path)
        logger.info(f"Model saved to {model_path}")
    
    return model

def predict_papers(
    pmids: List[str],
    model: MicrobeSigClassifier,
    retriever,
    preprocessor: TextPreprocessor
) -> List[Dict]:
    """Make predictions for a list of papers.
    
    Args:
        pmids: List of PMIDs
        model: Trained model
        retriever: PubMed data retriever
        preprocessor: Text preprocessor
        
    Returns:
        List of prediction dictionaries
    """
    # Get metadata and full texts
    metadata_list = []
    full_texts = []
    
    for pmid in pmids:
        try:
            metadata = retriever.get_paper_metadata(pmid)
            full_text = retriever.get_pmc_fulltext(pmid)
            
            metadata_list.append(metadata)
            full_texts.append(full_text)
            
        except Exception as e:
            logger.error(f"Error processing PMID {pmid}: {str(e)}")
            continue
    
    # Prepare features
    embeddings, additional_features = preprocessor.prepare_batch(metadata_list, full_texts)
    
    # Make predictions
    trainer = ModelTrainer(model)
    predictions = trainer.predict(embeddings, torch.tensor(additional_features))
    
    # Format output
    results = []
    sequencing_types = get_sequencing_types()
    body_sites = get_body_sites()
    
    for i, pmid in enumerate(pmids):
        results.append(format_prediction_output(
            pmid=pmid,
            has_signature=bool(np.round(predictions["signature"][i])),
            signature_probability=float(predictions["signature"][i]),
            sequencing_type=sequencing_types[predictions["sequencing"][i]],
            metadata={
                "body_site": body_sites[predictions["body_site"][i]]
            }
        ))
    
    return results

class MicrobeSigClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        # Existing model definition...
        # Add any necessary layers if not present

    def analyze_text(self, text: str) -> Dict:
        """Analyze text for microbe signatures.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary with analysis results
        """
        # Implement text analysis logic here
        # For example:
        # 1. Preprocess text
        # 2. Extract features
        # 3. Run forward pass
        # 4. Process outputs
        
        # Placeholder implementation
        try:
            # Assuming preprocessor is available globally or passed
            preprocessor = TextPreprocessor()
            embeddings, additional_features = preprocessor.prepare_batch([], [text])  # Adjust for single text
            
            # Make prediction
            with torch.no_grad():
                self.eval()
                signature_out = self.signature_head(embeddings, additional_features)
                sequencing_out = self.sequencing_head(embeddings, additional_features)
                body_site_out = self.body_site_head(embeddings, additional_features)
                
            # Process outputs
            has_signature = bool(torch.sigmoid(signature_out) > 0.5)
            sequencing_type = get_sequencing_types()[torch.argmax(sequencing_out).item()]
            body_site = get_body_sites()[torch.argmax(body_site_out).item()]
            
            return {
                "has_signature": has_signature,
                "sequencing_type": sequencing_type,
                "body_site": body_site
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_text: {e}")
            return {}

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="MicrobeSig Miner: Identify microbial signatures in publications"
    )
    
    parser.add_argument(
        "--pmid_list",
        type=str,
        required=True,
        help="Path to file containing PMIDs to analyze"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path for output JSON file"
    )
    
    parser.add_argument(
        "--model_path",
        type=str,
        help="Path to save/load trained model"
    )
    
    parser.add_argument(
        "--batch_size",
        type=int,
        default=32,
        help="Batch size for processing"
    )
    
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Use GPU if available"
    )
    
    args = parser.parse_args()
    
    # Set batch size
    config.BATCH_SIZE = args.batch_size
    
    # Initialize components
    retriever = PubMedRetriever()
    preprocessor = TextPreprocessor()
    
    # Load or train model
    if args.model_path and Path(args.model_path).exists():
        logger.info(f"Loading model from {args.model_path}")
        model = MicrobeSigClassifier()
        model.load_state_dict(torch.load(args.model_path))
    else:
        logger.info("Training new model...")
        model = train_model(retriever, preprocessor, args.model_path)
    
    # Load PMIDs
    pmids = load_pmids(args.pmid_list)
    logger.info(f"Processing {len(pmids)} papers...")
    
    # Make predictions
    predictions = predict_papers(pmids, model, retriever, preprocessor)
    
    # Save results
    save_predictions(predictions, args.output)
    logger.info(f"Results saved to {args.output}")

if __name__ == "__main__":
    main()
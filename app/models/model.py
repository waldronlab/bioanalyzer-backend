import logging
from typing import Dict, List, Tuple, Optional
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from app.utils.utils import config, get_sequencing_types, get_body_sites

logger = logging.getLogger(__name__)

class PaperDataset(Dataset):
    """Dataset class for paper classification."""
    
    def __init__(
        self,
        embeddings: torch.Tensor,
        additional_features: List[Dict],
        labels: Optional[Dict[str, torch.Tensor]] = None
    ):
        """Initialize the dataset.
        
        Args:
            embeddings: Paper embeddings tensor
            additional_features: List of additional feature dictionaries
            labels: Optional dictionary of label tensors
        """
        self.embeddings = embeddings
        
        # Convert additional features to tensor
        feature_list = []
        for features in additional_features:
            feature_list.append([
                features["has_full_text"],
                features["publication_year"],
                features["is_research_article"]
            ])
        self.features = torch.tensor(feature_list, dtype=torch.float32)
        
        self.labels = labels
        
    def __len__(self) -> int:
        return len(self.embeddings)
        
    def __getitem__(self, idx: int) -> Tuple:
        item = {
            "embeddings": self.embeddings[idx],
            "features": self.features[idx]
        }
        
        if self.labels is not None:
            item.update({k: v[idx] for k, v in self.labels.items()})
            
        return item

class MicrobeSigClassifier(nn.Module):
    """Neural network for paper classification."""
    
    def __init__(
        self,
        embedding_dim: int = 768,
        hidden_dim: int = 256,
        num_features: int = 3
    ):
        """Initialize the classifier.
        
        Args:
            embedding_dim: Dimension of paper embeddings
            hidden_dim: Dimension of hidden layer
            num_features: Number of additional features
        """
        super().__init__()
        
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        
        # Main classification network
        self.classifier = nn.Sequential(
            nn.Linear(embedding_dim + num_features, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.2)
        )
        
        # Task-specific heads
        self.signature_head = nn.Linear(hidden_dim // 2, 1)
        self.sequencing_head = nn.Linear(hidden_dim // 2, len(get_sequencing_types()))
        self.body_site_head = nn.Linear(hidden_dim // 2, len(get_body_sites()))
        
    def forward(
        self,
        embeddings: torch.Tensor,
        features: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """Forward pass.
        
        Args:
            embeddings: Paper embeddings tensor
            features: Additional features tensor
            
        Returns:
            Dictionary of predictions
        """
        # Concatenate embeddings and features
        x = torch.cat([embeddings, features], dim=1)
        
        # Shared layers
        shared = self.classifier(x)
        
        # Task-specific predictions
        return {
            "signature": torch.sigmoid(self.signature_head(shared)),
            "sequencing": self.sequencing_head(shared),
            "body_site": self.body_site_head(shared)
        }

class ModelTrainer:
    """Class for training and evaluating the model."""
    
    def __init__(
        self,
        model: MicrobeSigClassifier,
        device: torch.device = None
    ):
        """Initialize the trainer.
        
        Args:
            model: Model to train
            device: Device to use for training
        """
        self.model = model
        self.device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(self.device)
        
        # Loss functions
        self.signature_criterion = nn.BCELoss()
        self.sequencing_criterion = nn.CrossEntropyLoss()
        self.body_site_criterion = nn.CrossEntropyLoss()
        
    def train_epoch(
        self,
        train_loader: DataLoader,
        optimizer: torch.optim.Optimizer
    ) -> Dict[str, float]:
        """Train for one epoch.
        
        Args:
            train_loader: Training data loader
            optimizer: Optimizer
            
        Returns:
            Dictionary of training metrics
        """
        self.model.train()
        total_loss = 0
        
        for batch in train_loader:
            # Move batch to device
            batch = {k: v.to(self.device) for k, v in batch.items()}
            
            # Forward pass
            outputs = self.model(batch["embeddings"], batch["features"])
            
            # Calculate losses
            signature_loss = self.signature_criterion(
                outputs["signature"].squeeze(),
                batch["signature_label"]
            )
            
            sequencing_loss = self.sequencing_criterion(
                outputs["sequencing"],
                batch["sequencing_label"]
            )
            
            body_site_loss = self.body_site_criterion(
                outputs["body_site"],
                batch["body_site_label"]
            )
            
            # Combined loss
            loss = signature_loss + sequencing_loss + body_site_loss
            
            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            
        return {"train_loss": total_loss / len(train_loader)}
        
    @torch.no_grad()
    def evaluate(self, val_loader: DataLoader) -> Dict[str, float]:
        """Evaluate the model.
        
        Args:
            val_loader: Validation data loader
            
        Returns:
            Dictionary of evaluation metrics
        """
        self.model.eval()
        
        all_signature_preds = []
        all_signature_labels = []
        all_sequencing_preds = []
        all_sequencing_labels = []
        all_body_site_preds = []
        all_body_site_labels = []
        
        for batch in val_loader:
            # Move batch to device
            batch = {k: v.to(self.device) for k, v in batch.items()}
            
            # Forward pass
            outputs = self.model(batch["embeddings"], batch["features"])
            
            # Collect predictions and labels
            all_signature_preds.extend(outputs["signature"].squeeze().cpu().numpy())
            all_signature_labels.extend(batch["signature_label"].cpu().numpy())
            
            all_sequencing_preds.extend(outputs["sequencing"].argmax(dim=1).cpu().numpy())
            all_sequencing_labels.extend(batch["sequencing_label"].cpu().numpy())
            
            all_body_site_preds.extend(outputs["body_site"].argmax(dim=1).cpu().numpy())
            all_body_site_labels.extend(batch["body_site_label"].cpu().numpy())
            
        # Calculate metrics
        signature_metrics = precision_recall_fscore_support(
            all_signature_labels,
            np.round(all_signature_preds),
            average="binary"
        )
        
        sequencing_metrics = precision_recall_fscore_support(
            all_sequencing_labels,
            all_sequencing_preds,
            average="weighted"
        )
        
        body_site_metrics = precision_recall_fscore_support(
            all_body_site_labels,
            all_body_site_preds,
            average="weighted"
        )
        
        return {
            "signature_precision": signature_metrics[0],
            "signature_recall": signature_metrics[1],
            "signature_f1": signature_metrics[2],
            "sequencing_f1": sequencing_metrics[2],
            "body_site_f1": body_site_metrics[2]
        }
        
    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        num_epochs: int = config.NUM_EPOCHS,
        learning_rate: float = config.LEARNING_RATE
    ) -> Dict[str, List[float]]:
        """Train the model.
        
        Args:
            train_loader: Training data loader
            val_loader: Validation data loader
            num_epochs: Number of epochs to train
            learning_rate: Learning rate
            
        Returns:
            Dictionary of training history
        """
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        history = {
            "train_loss": [],
            "signature_f1": [],
            "sequencing_f1": [],
            "body_site_f1": []
        }
        
        for epoch in range(num_epochs):
            # Train
            train_metrics = self.train_epoch(train_loader, optimizer)
            
            # Evaluate
            val_metrics = self.evaluate(val_loader)
            
            # Update history
            history["train_loss"].append(train_metrics["train_loss"])
            history["signature_f1"].append(val_metrics["signature_f1"])
            history["sequencing_f1"].append(val_metrics["sequencing_f1"])
            history["body_site_f1"].append(val_metrics["body_site_f1"])
            
            logger.info(
                f"Epoch {epoch + 1}/{num_epochs} - "
                f"Loss: {train_metrics['train_loss']:.4f} - "
                f"Signature F1: {val_metrics['signature_f1']:.4f} - "
                f"Sequencing F1: {val_metrics['sequencing_f1']:.4f} - "
                f"Body Site F1: {val_metrics['body_site_f1']:.4f}"
            )
            
        return history
        
    @torch.no_grad()
    def predict(
        self,
        embeddings: torch.Tensor,
        features: torch.Tensor
    ) -> Dict[str, np.ndarray]:
        """Make predictions for new papers.
        
        Args:
            embeddings: Paper embeddings tensor
            features: Additional features tensor
            
        Returns:
            Dictionary of predictions
        """
        self.model.eval()
        
        # Move inputs to device
        embeddings = embeddings.to(self.device)
        features = features.to(self.device)
        
        # Forward pass
        outputs = self.model(embeddings, features)
        
        # Convert outputs to numpy arrays
        predictions = {
            "signature": outputs["signature"].squeeze().cpu().numpy(),
            "sequencing": outputs["sequencing"].argmax(dim=1).cpu().numpy(),
            "body_site": outputs["body_site"].argmax(dim=1).cpu().numpy()
        }
        
        return predictions
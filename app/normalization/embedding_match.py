"""Nearest-neighbour matching of free-text Condition values against
BugSigDB's Condition vocabulary using a biomedical embedding model.

Reused from MetaHarmonizer (shbrief/MetaHarmonizer, `OntoMapEngine` stage 2):
when no exact label/synonym match exists, embed the query with SapBERT
(`cambridgeltl/SapBERT-from-PubMedBERT-fulltext`, the model MetaHarmonizer
uses for this stage) and take the closest term from a fixed corpus by cosine
similarity. As in MetaHarmonizer, this runs only after the deterministic
stages have failed, and it never invents a term - every answer is an
existing BugSigDB vocabulary entry with its real ontology ID.

What was not reused: FAISS (the corpus is ~930 labels, so a brute-force
dot product is exact and fast) and MetaHarmonizer's corpus/KnowledgeDb
machinery. `sentence-transformers` was already a BioAnalyzer dependency.

Measured on the 2026-11-12 benchmark (100 papers, held-out vocabulary):
accepting the nearest term at cosine >= 0.8 fixed 7 Condition labels and
broke none; at 0.7 it broke 1, and with no cutoff it broke 3 (e.g.
"refractory epilepsy" -> "treatment refractory schizophrenia" at 0.68). Hence
the 0.8 default for `CONDITION_EMBEDDING_THRESHOLD`.

Disabled with `CONDITION_EMBEDDING_MATCH=0`. If the model can't be loaded
(no network on first use, no sentence-transformers), matching is skipped and
normalization behaves as it did before this module existed.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import List, Optional, Tuple

from app.normalization.bugsigdb_vocabulary import BugSigDBVocabulary, get_vocabulary

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
DEFAULT_THRESHOLD = 0.8
# A snapped term is a guess, never a certainty: normalize_condition() caps
# mapping_confidence at this value, and tiering sends anything < 1.0 to "review".
MAX_SNAP_CONFIDENCE = 0.85

_lock = threading.Lock()
_model = None
_model_failed = False
_index: dict = {}  # id(vocabulary) -> (labels, curies, matrix)


def enabled() -> bool:
    return os.getenv("CONDITION_EMBEDDING_MATCH", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def threshold() -> float:
    try:
        return float(os.getenv("CONDITION_EMBEDDING_THRESHOLD", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD


def _get_model():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    with _lock:
        if _model is not None or _model_failed:
            return _model
        try:
            name = os.getenv("CONDITION_EMBEDDING_MODEL", DEFAULT_MODEL)
            _model = _load_model(name)
            logger.info("Loaded condition embedding model %s", name)
        except Exception as e:  # missing package, no network, bad model name
            _model_failed = True
            logger.warning(
                "Condition embedding matching disabled - model unavailable: %s",
                type(e).__name__,
            )
    return _model


def _load_model(name: str):
    """Build the SentenceTransformer for *name* (a hub id or a local dir).

    A plain Hugging Face BERT directory (no sentence-transformers config, as
    for SapBERT) would otherwise get *mean* pooling automatically, but SapBERT
    is trained with the [CLS] vector, so for such a directory the model is
    assembled explicitly with CLS pooling. Directories that already carry
    sentence-transformers metadata, and hub ids, load as-is."""
    from sentence_transformers import SentenceTransformer

    path = Path(name)
    if path.is_dir() and not (path / "modules.json").exists():
        from sentence_transformers import models

        transformer = models.Transformer(str(path), max_seq_length=64)
        pooling = models.Pooling(
            transformer.get_word_embedding_dimension(), pooling_mode="cls"
        )
        return SentenceTransformer(modules=[transformer, pooling], device="cpu")
    return SentenceTransformer(name, device="cpu")


def _get_index(vocab: BugSigDBVocabulary, model):
    key = id(vocab)
    if key not in _index:
        with _lock:
            if key not in _index:
                pairs = vocab.terms()
                labels = [label for label, _ in pairs]
                matrix = model.encode(
                    labels,
                    normalize_embeddings=True,
                    batch_size=64,
                    show_progress_bar=False,
                )
                _index[key] = (labels, [curie for _, curie in pairs], matrix)
    return _index[key]


def nearest(
    text: str, k: int = 5, vocab: Optional[BugSigDBVocabulary] = None
) -> List[Tuple[str, str, float]]:
    """Up to *k* ``(label, curie, cosine)`` BugSigDB terms closest to
    *text*, best first. Empty when disabled, the model is unavailable, the
    vocabulary is empty, or *text* is blank."""
    if not text or not text.strip() or not enabled():
        return []
    vocab = vocab if vocab is not None else get_vocabulary()
    if len(vocab) == 0:
        return []
    model = _get_model()
    if model is None:
        return []
    labels, curies, matrix = _get_index(vocab, model)
    query = model.encode(
        [text.strip()], normalize_embeddings=True, show_progress_bar=False
    )[0]
    scores = matrix @ query
    order = scores.argsort()[::-1][:k]
    return [(labels[i], curies[i], float(scores[i])) for i in order]

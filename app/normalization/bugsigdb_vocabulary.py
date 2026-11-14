"""BugSigDB's own Condition vocabulary: the label BugSigDB uses for each
ontology ID, built from its `full_dump.csv` export by
`scripts/build_bugsigdb_condition_vocabulary.py`.

Why Condition labels come from here rather than from the ontology
-----------------------------------------------------------------
BugSigDB records one fixed label per ontology ID, taken from an older EFO
release: MONDO:0005180 is "Parkinson's disease" across 410 curated rows, while
current MONDO and EFO both now say "Parkinson disease"; MONDO:0005148 is "Type
II diabetes mellitus", not MONDO's "type 2 diabetes mellitus". BioAnalyzer
used to emit the live ontology label, so a correct ID still disagreed with
BugSigDB's label and a curator had to retype it - 17 of 100 papers in the
2026-11-12 benchmark. Neither metacurator nor MetaHarmonizer can fix that:
both output the current ontology label too. The only source of BugSigDB's
wording is BugSigDB.

The ontology ID is never changed by a relabel - only the text shown beside
it - so this cannot introduce a wrong mapping.

`BUGSIGDB_CONDITION_VOCAB_PATH` points at a different vocabulary file. The
benchmark uses that to load a held-out copy built without the benchmark
papers' own rows.
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_VOCAB_PATH = (
    Path(__file__).parent / "data" / "bugsigdb_condition_vocabulary.json"
)


def _key(text: str) -> str:
    """Case/punctuation/whitespace-insensitive key for exact label equality
    ("Parkinson's disease" == "parkinsons disease" == "PARKINSON'S DISEASE").
    Apostrophes are dropped rather than turned into a space, so the
    possessive and non-possessive spellings meet."""
    text = re.sub(r"['’`]", "", text.casefold())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


class BugSigDBVocabulary:
    def __init__(self, terms: Dict[str, Dict]):
        self._label_by_curie: Dict[str, str] = {}
        self._curie_by_key: Dict[str, str] = {}
        for curie, entry in terms.items():
            label = entry["label"]
            self._label_by_curie[curie.upper()] = label
            self._curie_by_key.setdefault(_key(label), curie)
            # A minority label for the same ID still identifies the ID.
            for other in entry.get("other_labels", ()):
                self._curie_by_key.setdefault(_key(other), curie)

    def __len__(self) -> int:
        return len(self._label_by_curie)

    def label_for(self, curie: str) -> Optional[str]:
        """BugSigDB's label for *curie*, or None if BugSigDB never used it."""
        if not curie:
            return None
        return self._label_by_curie.get(curie.strip().upper())

    def contains(self, curie: str) -> bool:
        return self.label_for(curie) is not None

    def match_label(self, text: str) -> Optional[Tuple[str, str]]:
        """``(label, curie)`` when *text* is exactly one of BugSigDB's labels
        (ignoring case and punctuation), else None. Exact equality only -
        never a substring or similarity match."""
        if not text:
            return None
        curie = self._curie_by_key.get(_key(text))
        if curie is None:
            return None
        return self._label_by_curie[curie.upper()], curie

    def terms(self) -> List[Tuple[str, str]]:
        """Every ``(label, curie)`` pair, in a stable order."""
        return sorted(
            ((label, curie) for curie, label in self._label_by_curie.items()),
            key=lambda pair: pair[1],
        )


@lru_cache(maxsize=4)
def _load(path: str) -> BugSigDBVocabulary:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        vocab = BugSigDBVocabulary(data.get("terms", {}))
        logger.info(
            "Loaded BugSigDB condition vocabulary: %d terms from %s", len(vocab), path
        )
        return vocab
    except (OSError, ValueError, KeyError) as e:
        # Fail open to "no vocabulary": labels fall back to the ontology's own
        # label, exactly the pre-vocabulary behaviour.
        logger.warning(
            "BugSigDB condition vocabulary unavailable (%s): %s", path, type(e).__name__
        )
        return BugSigDBVocabulary({})


def get_vocabulary() -> BugSigDBVocabulary:
    path = os.getenv("BUGSIGDB_CONDITION_VOCAB_PATH", "").strip() or str(
        DEFAULT_VOCAB_PATH
    )
    return _load(path)

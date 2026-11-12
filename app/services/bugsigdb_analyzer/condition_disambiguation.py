"""LLM choice among already-grounded Condition candidates.

Reused from metacurator (seandavi/metacurator, `judge.disambiguate`, SPEC
100): when deterministic grounding leaves several plausible real terms, the
model may only *choose one of them, or none* - it cannot write a new label or
mint an ID. An answer outside the candidate set is rejected (metacurator
raises `JudgeContractError`; here the field is left as it was and the
violation is logged, since one paper's analysis shouldn't fail over it).

When it runs: the Condition field is not already a BugSigDB vocabulary term,
and `normalize_condition()` attached BugSigDB-vocabulary candidates - the
SapBERT neighbours that scored between the 0.6 candidate floor and the 0.8
auto-accept threshold (see app/normalization/embedding_match.py). The model
sees the paper's title and abstract, so it can tell "colorectal adenoma" from
"pituitary gland adenoma", which the embedding alone could not.

Anything chosen here is "review" tier - a curator still confirms it.
Disabled with `CONDITION_LLM_DISAMBIGUATION=0`. Costs one extra, short LLM
call, only for papers that reach this step.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from app.normalization.bugsigdb_vocabulary import get_vocabulary
from app.utils.credential_masking import mask_exception_message

from .field_extraction import _parse_json_object

logger = logging.getLogger(__name__)

_ABSTRACT_CHARS = 3000
_TIMEOUT_SECONDS = 60

DISAMBIGUATION_PROMPT = """\
You are helping curate BugSigDB, a database of microbiome studies. BugSigDB records
each study's "condition": the factor that distinguishes the groups being compared
(usually a disease; otherwise e.g. a diet, exposure, treatment or measurement).

An automatic reader extracted this condition from the paper: {value!r}
It is not one of BugSigDB's controlled terms. Choose the ONE candidate below that
names the same condition the paper's groups are compared by, or null if none does.
Prefer null to a candidate that is broader, narrower, or a different condition.

Title: {title}
Abstract: {abstract}

Candidates:
{listing}

Return ONLY a JSON object: {{"curie": "<one CURIE from the list above>"}} or {{"curie": null}}
"""


def enabled() -> bool:
    return os.getenv("CONDITION_LLM_DISAMBIGUATION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


async def disambiguate_condition(
    field: Dict[str, Any],
    *,
    title: str,
    abstract: str,
    unified_qa: Any,
    pmid: str = "",
) -> Dict[str, Any]:
    """Return *field* (the result["fields"]["condition"] dict), updated to
    the candidate the model chose, or unchanged."""
    if not enabled() or unified_qa is None or not field:
        return field
    if field.get("status") == "ABSENT" or not field.get("value"):
        return field
    vocab = get_vocabulary()
    if vocab.contains(field.get("ontology_id", "")):
        return field

    allowed: Dict[str, str] = {}
    for cand in field.get("mapping_candidates") or []:
        curie = (cand.get("ontology_id") or "").strip()
        label = vocab.label_for(curie)
        if label and curie.upper() not in allowed:
            allowed[curie.upper()] = label
    if not allowed:
        return field

    prompt = DISAMBIGUATION_PROMPT.format(
        value=field["value"],
        title=title or "",
        abstract=(abstract or "")[:_ABSTRACT_CHARS],
        listing="\n".join(f"- {curie} : {label}" for curie, label in allowed.items()),
    )
    try:
        call = unified_qa.chat(prompt)
        response = (
            await asyncio.wait_for(call, timeout=_TIMEOUT_SECONDS)
            if asyncio.iscoroutine(call)
            else call
        )
        choice: Optional[str] = _parse_json_object(
            (response or {}).get("text", "")
        ).get("curie")
    except Exception as e:
        logger.warning(
            "Condition disambiguation failed for PMID %s: %s",
            pmid,
            mask_exception_message(e),
        )
        return field

    if not choice:
        return field
    choice = str(choice).strip().upper()
    if choice not in allowed:
        logger.warning(
            "Condition disambiguation for PMID %s returned %r, not one of the %d candidates; ignored",
            pmid,
            choice,
            len(allowed),
        )
        return field

    logger.info(
        "Condition disambiguation for PMID %s: %r -> %s %r",
        pmid,
        field["value"],
        choice,
        allowed[choice],
    )
    updated = dict(field)
    updated.update(
        {
            "value": allowed[choice],
            "ontology_id": choice,
            "status": "PRESENT",
            "mapping_confidence": 0.8,
            "mapping_tier": "review",
            "raw": field.get("raw") or field["value"],
            "mapping_candidates": [
                c
                for c in field.get("mapping_candidates") or []
                if (c.get("ontology_id") or "").strip().upper() != choice
            ],
        }
    )
    return updated

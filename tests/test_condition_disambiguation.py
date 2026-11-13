"""metacurator-style constrained choice for the Condition field
(app/services/bugsigdb_analyzer/condition_disambiguation.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock

import pytest

from app.normalization import bugsigdb_vocabulary
from app.services.bugsigdb_analyzer.condition_disambiguation import (
    disambiguate_condition,
)

TERMS = {
    "EFO:0000000": {"label": "Unused"},
    "MONDO:0004972": {"label": "Colorectal adenoma"},
    "MONDO:0006373": {"label": "Pituitary gland adenoma"},
}


@pytest.fixture(autouse=True)
def vocab(tmp_path, monkeypatch):
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"terms": TERMS}))
    monkeypatch.setenv("BUGSIGDB_CONDITION_VOCAB_PATH", str(path))
    monkeypatch.setenv("CONDITION_LLM_DISAMBIGUATION", "1")
    bugsigdb_vocabulary._load.cache_clear()
    yield
    bugsigdb_vocabulary._load.cache_clear()


def _field(**overrides):
    field = {
        "value": "adenoma",
        "status": "PARTIALLY_PRESENT",
        "ontology_id": "",
        "mapping_tier": "none",
        "raw": "",
        "mapping_candidates": [
            {"label": "Pituitary gland adenoma", "ontology_id": "MONDO:0006373"},
            {"label": "Colorectal adenoma", "ontology_id": "MONDO:0004972"},
            {"label": "not in vocab", "ontology_id": "MONDO:9999999"},
        ],
    }
    field.update(overrides)
    return field


def _qa(reply):
    qa = Mock()
    qa.chat = AsyncMock(return_value={"text": reply})
    return qa


@pytest.mark.asyncio
async def test_choice_from_candidates_is_applied_at_review_tier():
    qa = _qa('{"curie": "MONDO:0004972"}')
    out = await disambiguate_condition(
        _field(),
        title="Gut microbiota in colorectal adenoma",
        abstract="",
        unified_qa=qa,
    )
    assert out["value"] == "Colorectal adenoma"
    assert out["ontology_id"] == "MONDO:0004972"
    assert out["mapping_tier"] == "review"
    assert out["raw"] == "adenoma"
    prompt = qa.chat.call_args.args[0]
    assert "MONDO:9999999" not in prompt  # only BugSigDB terms are offered


@pytest.mark.asyncio
async def test_choice_outside_candidate_set_is_rejected():
    field = _field()
    out = await disambiguate_condition(
        field, title="t", abstract="a", unified_qa=_qa('{"curie": "MONDO:0005575"}')
    )
    assert out == field


@pytest.mark.asyncio
async def test_null_choice_leaves_field_unchanged():
    field = _field()
    out = await disambiguate_condition(
        field, title="t", abstract="a", unified_qa=_qa('{"curie": null}')
    )
    assert out == field


@pytest.mark.asyncio
async def test_llm_failure_leaves_field_unchanged():
    qa = Mock()
    qa.chat = AsyncMock(side_effect=RuntimeError("boom"))
    field = _field()
    assert (
        await disambiguate_condition(field, title="t", abstract="a", unified_qa=qa)
        == field
    )


@pytest.mark.asyncio
async def test_no_call_when_condition_is_already_a_bugsigdb_term():
    qa = _qa('{"curie": "MONDO:0006373"}')
    field = _field(ontology_id="MONDO:0004972", value="Colorectal adenoma")
    assert (
        await disambiguate_condition(field, title="t", abstract="a", unified_qa=qa)
        == field
    )
    qa.chat.assert_not_called()


@pytest.mark.asyncio
async def test_no_call_without_vocabulary_candidates():
    qa = _qa('{"curie": "MONDO:9999999"}')
    field = _field(mapping_candidates=[{"label": "x", "ontology_id": "MONDO:9999999"}])
    assert (
        await disambiguate_condition(field, title="t", abstract="a", unified_qa=qa)
        == field
    )
    qa.chat.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("CONDITION_LLM_DISAMBIGUATION", "0")
    qa = _qa('{"curie": "MONDO:0004972"}')
    field = _field()
    assert (
        await disambiguate_condition(field, title="t", abstract="a", unified_qa=qa)
        == field
    )
    qa.chat.assert_not_called()


@pytest.mark.asyncio
async def test_context_excerpt_is_bounded_and_included_in_prompt():
    qa = _qa('{"curie": null, "reason": "none fit"}')
    await disambiguate_condition(
        _field(), title="T", abstract="A", unified_qa=qa, context="M" * 10000
    )
    prompt = qa.chat.call_args[0][0]
    assert "Methods" in prompt
    assert prompt.count("M") >= 4000
    assert "M" * 4001 not in prompt


@pytest.mark.asyncio
async def test_no_context_block_when_context_empty():
    qa = _qa('{"curie": null}')
    await disambiguate_condition(_field(), title="T", abstract="A", unified_qa=qa)
    assert "Paper text excerpt" not in qa.chat.call_args[0][0]


@pytest.mark.asyncio
async def test_new_reply_format_stores_reason_and_stays_review():
    qa = _qa(
        '{"curie": "MONDO:0004972", "reason": "colorectal study", "confidence": 0.99}'
    )
    out = await disambiguate_condition(_field(), title="T", abstract="A", unified_qa=qa)
    assert out["ontology_id"] == "MONDO:0004972"
    assert out["disambiguation_reason"] == "colorectal study"
    assert out["mapping_tier"] == "review"
    assert out["mapping_confidence"] == 0.85  # clamped, never reaches 1.0


@pytest.mark.asyncio
async def test_old_reply_format_still_parses_with_default_confidence():
    qa = _qa('{"curie": "MONDO:0004972"}')
    out = await disambiguate_condition(_field(), title="T", abstract="A", unified_qa=qa)
    assert out["ontology_id"] == "MONDO:0004972"
    assert out["mapping_confidence"] == 0.8
    assert out["disambiguation_reason"] == ""


@pytest.mark.asyncio
async def test_prompt_allows_broader_standard_entity_for_qualified_subtype():
    qa = _qa('{"curie": null}')
    await disambiguate_condition(_field(), title="T", abstract="A", unified_qa=qa)
    prompt = qa.chat.call_args[0][0]
    assert "qualified" in prompt and "IS acceptable" in prompt
    assert "Never pick a broader category" in prompt


@pytest.mark.asyncio
async def test_choice_outside_allowed_set_still_rejected():
    qa = _qa('{"curie": "MONDO:9999999", "reason": "x"}')
    out = await disambiguate_condition(_field(), title="T", abstract="A", unified_qa=qa)
    assert out["ontology_id"] == ""

"""LLM extraction retry + provenance for the v1/v2 pipelines.

Before: an empty or unparseable LLM answer fell straight through to the
regex heuristic, with nothing in the result saying so. Now the call is
retried once (JSON mode), and result["extraction_source"] reports "llm" or
"heuristic"."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("defusedxml")

from app.services.bugsigdb_analyzer import simple_analysis
from app.services.bugsigdb_analyzer.simple_analysis import (
    SOURCE_HEURISTIC,
    SOURCE_LLM,
    _extract_payload_with_retry,
    _heuristic_payload,
    analyze_paper_simple,
)
from app.services.bugsigdb_analyzer.rag_analysis import analyze_paper_with_rag

GOOD = '{"host_species_raw": "human", "condition_raw": "IBD"}'


def _retriever(abstract="Abstract about 30 human patients.", full_text=""):
    r = MagicMock()
    r.get_texts_for_analysis_async = AsyncMock(
        return_value={
            "title": "A Test Paper",
            "abstract": abstract,
            "full_text": full_text,
            "publication_date": "2023-05-01",
            "journal": "Test Journal",
            "authors": ["A. Author"],
        }
    )
    return r


def _cache():
    c = MagicMock()
    c.get_analysis_result.return_value = None
    c.is_cache_valid.return_value = False
    return c


def _qa(*texts):
    """UnifiedQA double whose chat() returns the given texts in order."""
    qa = MagicMock()
    qa.chat = AsyncMock(side_effect=[{"text": t} for t in texts])
    return qa


@pytest.fixture(autouse=True)
def _no_disambiguation(monkeypatch):
    monkeypatch.setenv("CONDITION_LLM_DISAMBIGUATION", "0")


# ---------------------------------------------------------------------------
# _extract_payload_with_retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExtractPayloadWithRetry:
    async def test_first_attempt_success_is_tagged_llm(self):
        qa = _qa(GOOD)
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=qa):
            payload = await _extract_payload_with_retry(
                context_text="ctx", title="t", journal="j", year=2020, pmid="1"
            )
        assert payload["_source"] == SOURCE_LLM
        assert payload["host_species_raw"] == "human"
        qa.chat.assert_awaited_once()
        assert qa.chat.call_args.kwargs["json_mode"] is True

    async def test_retries_once_after_unparseable_answer(self):
        qa = _qa("not json at all", GOOD)
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=qa):
            payload = await _extract_payload_with_retry(
                context_text="ctx", title="t", journal="j", year=2020, pmid="1"
            )
        assert payload["_source"] == SOURCE_LLM
        assert qa.chat.await_count == 2

    async def test_retries_once_after_empty_answer(self):
        qa = _qa("", GOOD)
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=qa):
            payload = await _extract_payload_with_retry(
                context_text="ctx", title="t", journal="j", year=2020, pmid="1"
            )
        assert payload["_source"] == SOURCE_LLM
        assert qa.chat.await_count == 2

    async def test_gives_up_after_two_failures(self):
        qa = _qa("garbage", "Error: provider exploded")
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=qa):
            payload = await _extract_payload_with_retry(
                context_text="ctx", title="t", journal="j", year=2020, pmid="1"
            )
        assert payload == {}
        assert qa.chat.await_count == 2

    async def test_exception_counts_as_failed_attempt_and_is_masked(self, caplog):
        # Built at runtime so no key-shaped literal sits in the source (it
        # would trip secret scanners); still matches the masking pattern.
        secret = "AIza" + "x" * 20
        qa = MagicMock()
        qa.chat = AsyncMock(side_effect=[RuntimeError(f"key {secret}"), {"text": GOOD}])
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=qa):
            with caplog.at_level("WARNING"):
                payload = await _extract_payload_with_retry(
                    context_text="ctx", title="t", journal="j", year=2020, pmid="1"
                )
        assert payload["_source"] == SOURCE_LLM
        assert secret not in caplog.text

    async def test_timeout_is_not_retried(self, monkeypatch):
        monkeypatch.setattr(simple_analysis, "ANALYSIS_TIMEOUT", 0.01)

        async def slow(prompt, **kwargs):
            await asyncio.sleep(1)
            return {"text": GOOD}

        qa = MagicMock()
        qa.chat = AsyncMock(side_effect=slow)
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=qa):
            payload = await _extract_payload_with_retry(
                context_text="ctx", title="t", journal="j", year=2020, pmid="1"
            )
        assert payload == {}
        assert qa.chat.await_count == 1

    async def test_no_qa_returns_empty(self):
        with patch("app.services.bugsigdb_analyzer.get_unified_qa", return_value=None):
            payload = await _extract_payload_with_retry(
                context_text="ctx", title="t", journal="j", year=2020, pmid="1"
            )
        assert payload == {}


def test_heuristic_payload_is_always_tagged():
    assert _heuristic_payload("")["_source"] == SOURCE_HEURISTIC
    assert _heuristic_payload("30 human patients")["_source"] == SOURCE_HEURISTIC


# ---------------------------------------------------------------------------
# Pipelines surface extraction_source and pass context to disambiguation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPipelinesProvenance:
    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_simple_reports_llm_after_retry(
        self, mock_cache, mock_retriever, mock_qa, _in_db
    ):
        mock_cache.return_value = _cache()
        mock_retriever.return_value = _retriever()
        qa = _qa("broken", GOOD)
        mock_qa.return_value = qa

        result = await analyze_paper_simple("12345678")

        assert result["extraction_source"] == SOURCE_LLM
        assert qa.chat.await_count == 2

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_simple_reports_heuristic_after_two_failures(
        self, mock_cache, mock_retriever, mock_qa, _in_db
    ):
        mock_cache.return_value = _cache()
        mock_retriever.return_value = _retriever()
        mock_qa.return_value = _qa("broken", "still broken")

        result = await analyze_paper_simple("12345678")

        assert result["extraction_source"] == SOURCE_HEURISTIC
        # Heuristic-sourced fields can never be auto-accepted.
        assert result["fields"]["host_species"]["mapping_tier"] == "review"

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_rag_reports_source(
        self, mock_cache, mock_retriever, mock_qa, _in_db
    ):
        mock_cache.return_value = _cache()
        mock_retriever.return_value = _retriever(full_text="short")
        mock_qa.return_value = _qa(GOOD)

        result = await analyze_paper_with_rag("12345678", use_rag=True)

        assert result["extraction_source"] == SOURCE_LLM

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_rag_reports_heuristic(
        self, mock_cache, mock_retriever, mock_qa, _in_db
    ):
        mock_cache.return_value = _cache()
        mock_retriever.return_value = _retriever(full_text="short")
        mock_qa.return_value = _qa("nope", "nope")

        result = await analyze_paper_with_rag("12345678", use_rag=True)

        assert result["extraction_source"] == SOURCE_HEURISTIC

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_disambiguation_receives_prepared_context(
        self, mock_cache, mock_retriever, mock_qa, _in_db
    ):
        mock_cache.return_value = _cache()
        mock_retriever.return_value = _retriever()
        mock_qa.return_value = _qa(GOOD)

        seen = {}

        async def fake_disambiguate(field, **kwargs):
            seen.update(kwargs)
            return field

        with patch.object(simple_analysis, "disambiguate_condition", fake_disambiguate):
            await analyze_paper_simple("12345678")

        assert "context" in seen
        assert seen["context"].startswith("ABSTRACT:")
        assert "30 human patients" in seen["context"]

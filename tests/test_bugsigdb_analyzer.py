import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# defusedxml may not be installed in lightweight test environments
pytest.importorskip("defusedxml")

from app.services.bugsigdb_analyzer import (
    _parse_pmc_sections,
    prepare_analysis_context,
    _classify_section_title,
    _local_tag,
    _truncate,
    _build_field_result,
    _build_field_result_from_term,
    _is_low_quality_cached_result,
    _parse_json_object,
    _heuristic_payload_from_text,
    _build_curation_summary,
    _postprocess_field_results,
    _field_results_from_unified_payload,
    _avg_confidence,
    _resolve_diff_abundance,
    extract_year,
    create_empty_field_result,
    detect_differential_abundance,
    analyze_paper_simple,
    analyze_paper_with_rag,
)


def test_parse_pmc_sections_with_namespaced_title():
    xml = """<article xmlns="http://example.com">
      <body>
        <sec>
          <title>Methods</title>
          <p>Experimental details here.</p>
        </sec>
      </body>
    </article>"""

    sections = _parse_pmc_sections(xml)

    assert sections.get("METHODS") == "Experimental details here."


def test_prepare_analysis_context_respects_char_limit():
    abstract = "Abstract text " + "A" * 30
    full_text = (
        "<article><body><sec><title>Methods</title>"
        f"<p>{'B' * 100}</p></sec></body></article>"
    )

    context = prepare_analysis_context(abstract, full_text, char_limit=80)

    assert len(context) <= 80
    assert context.startswith("ABSTRACT:")


class TestClassifySectionTitle:
    def test_known_titles_map_to_canonical_sections(self):
        assert _classify_section_title("Methods") == "METHODS"
        assert _classify_section_title("Materials and Methods") == "METHODS"
        assert _classify_section_title("Results") == "RESULTS"
        assert _classify_section_title("Introduction") == "INTRODUCTION"
        assert _classify_section_title("Discussion") == "DISCUSSION"
        assert _classify_section_title("Abstract") == "ABSTRACT"

    def test_unknown_or_empty_title_is_other(self):
        assert _classify_section_title("Acknowledgements") == "OTHER"
        assert _classify_section_title("") == "OTHER"
        assert _classify_section_title(None) == "OTHER"


class TestLocalTag:
    def test_strips_namespace_prefix(self):
        assert _local_tag("{http://example.com}sec") == "sec"

    def test_passes_through_unnamespaced_tag(self):
        assert _local_tag("sec") == "sec"


class TestTruncate:
    def test_returns_unchanged_when_within_limit(self):
        assert _truncate("short text", 100) == "short text"

    def test_cuts_at_sentence_boundary_when_possible(self):
        text = "First sentence. Second sentence. " + "Filler " * 20
        result = _truncate(text, 40)
        assert result.endswith("[truncated]")
        assert len(result) <= 40

    def test_hard_cuts_when_limit_smaller_than_suffix(self):
        result = _truncate("some long text here", 5)
        assert result == "some "
        assert len(result) == 5


class TestBuildFieldResult:
    def test_present_gets_default_confidence(self):
        result = _build_field_result("Homo sapiens", "PRESENT")
        assert result["value"] == "Homo sapiens"
        assert result["status"] == "PRESENT"
        assert result["confidence"] == 0.85
        assert result["reason_if_missing"] == ""

    def test_absent_forces_empty_value_and_reason(self):
        result = _build_field_result("ignored", "ABSENT")
        assert result["value"] == ""
        assert result["confidence"] == 0.0
        assert result["reason_if_missing"] == "Information not found in the paper"

    def test_partially_present_default_confidence(self):
        result = _build_field_result("some value", "PARTIALLY_PRESENT")
        assert result["confidence"] == 0.65

    def test_explicit_confidence_overrides_default(self):
        result = _build_field_result("x", "PRESENT", confidence=0.42)
        assert result["confidence"] == 0.42

    def test_mapping_confidence_defaults_to_confidence(self):
        result = _build_field_result("x", "PRESENT", confidence=0.42)
        assert result["mapping_confidence"] == 0.42

    def test_explicit_mapping_confidence_is_independent(self):
        result = _build_field_result(
            "x", "PRESENT", confidence=0.42, mapping_confidence=0.9
        )
        assert result["mapping_confidence"] == 0.9

    def test_none_value_on_non_absent_status_is_empty_string(self):
        result = _build_field_result(None, "PARTIALLY_PRESENT")
        assert result["value"] == ""


class TestBuildFieldResultFromTerm:
    def test_builds_from_normalized_term(self):
        from app.normalization.types import NormalizedTerm

        term = NormalizedTerm(
            label="Homo sapiens",
            ontology_id="NCBITaxon:9606",
            status="PRESENT",
            mapping_confidence=1.0,
        )
        result = _build_field_result_from_term(term)
        assert result["value"] == "Homo sapiens"
        assert result["ontology_id"] == "NCBITaxon:9606"
        assert result["confidence"] == 0.85
        # Full-confidence dict match -> auto tier, no candidates needed.
        assert result["mapping_tier"] == "auto"
        assert result["mapping_candidates"] == []

    def test_review_tier_surfaces_candidates(self):
        from app.normalization.types import NormalizedTerm

        term = NormalizedTerm(
            label="Mus musculus",
            ontology_id="NCBITaxon:10090",
            status="PARTIALLY_PRESENT",
            mapping_confidence=0.9,
            candidates=(("Rattus norvegicus", "NCBITaxon:10116"),),
        )
        result = _build_field_result_from_term(term)
        assert result["mapping_tier"] == "review"
        assert result["mapping_candidates"] == [
            {"label": "Rattus norvegicus", "ontology_id": "NCBITaxon:10116"}
        ]

    def test_rejects_non_normalized_term(self):
        with pytest.raises(TypeError):
            _build_field_result_from_term({"label": "fake"})


class TestIsLowQualityCachedResult:
    def test_true_when_all_essential_fields_absent(self):
        analysis_data = {
            "fields": {
                "host_species": {"status": "ABSENT"},
                "body_site": {"status": "ABSENT"},
                "condition": {"status": "ABSENT"},
                "sequencing_type": {"status": "ABSENT"},
                "sample_size": {"status": "ABSENT"},
            }
        }
        assert _is_low_quality_cached_result(analysis_data) is True

    def test_false_when_one_field_present(self):
        analysis_data = {
            "fields": {
                "host_species": {"status": "PRESENT"},
                "body_site": {"status": "ABSENT"},
                "condition": {"status": "ABSENT"},
                "sequencing_type": {"status": "ABSENT"},
                "sample_size": {"status": "ABSENT"},
            }
        }
        assert _is_low_quality_cached_result(analysis_data) is False

    def test_true_when_fields_missing_entirely(self):
        assert _is_low_quality_cached_result({}) is True
        assert _is_low_quality_cached_result({"fields": {}}) is True
        assert _is_low_quality_cached_result("not a dict") is True

    def test_false_when_a_tracked_field_is_missing_from_dict(self):
        # Missing key (not present at all) is treated as "can't confirm
        # ABSENT" rather than counted as ABSENT.
        analysis_data = {"fields": {"host_species": {"status": "ABSENT"}}}
        assert _is_low_quality_cached_result(analysis_data) is False


class TestParseJsonObject:
    def test_parses_clean_json(self):
        assert _parse_json_object('{"a": 1}') == {"a": 1}

    def test_extracts_json_embedded_in_prose(self):
        text = 'Here is the result: {"a": 1, "b": "two"} - hope that helps!'
        assert _parse_json_object(text) == {"a": 1, "b": "two"}

    def test_extracts_json_from_fenced_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert _parse_json_object(text) == {"a": 1}

    def test_returns_empty_dict_for_empty_input(self):
        assert _parse_json_object("") == {}
        assert _parse_json_object(None) == {}

    def test_returns_empty_dict_when_unparseable(self):
        assert _parse_json_object("not json at all") == {}


class TestHeuristicPayloadFromText:
    def test_empty_text_returns_empty_dict(self):
        assert _heuristic_payload_from_text("") == {}
        assert _heuristic_payload_from_text("   ") == {}

    def test_detects_human_host(self):
        payload = _heuristic_payload_from_text("We recruited 30 patients with IBD.")
        assert payload["host_species_raw"] == "human"

    def test_detects_mouse_host(self):
        payload = _heuristic_payload_from_text("Mice were fed a high-fat diet.")
        assert payload["host_species_raw"] == "mouse"

    def test_mouse_host_wins_over_generic_controls_wording(self):
        """Regression test: "controls" is species-ambiguous (animal studies
        use it too, e.g. "wild-type controls") and must not outrank an
        explicit mouse/rat mention in the same text."""
        payload = _heuristic_payload_from_text(
            "Mice were compared to wild-type controls fed a high-fat diet."
        )
        assert payload["host_species_raw"] == "mouse"

    def test_detects_fecal_body_site(self):
        payload = _heuristic_payload_from_text("Stool samples were collected.")
        assert payload["body_site_raw"] == "fecal samples"

    def test_detects_disease_phrase(self):
        payload = _heuristic_payload_from_text(
            "We studied patients with chronic kidney disease over one year."
        )
        assert "disease" in (payload["condition_raw"] or "")

    def test_detects_named_condition_keyword(self):
        payload = _heuristic_payload_from_text("Subjects had type 2 diabetes.")
        assert payload["condition_raw"] == "diabetes"

    def test_detects_16s_sequencing(self):
        payload = _heuristic_payload_from_text("16S rRNA gene sequencing was used.")
        assert payload["sequencing_type_raw"] == "16S rRNA gene sequencing"

    def test_detects_shotgun_sequencing(self):
        payload = _heuristic_payload_from_text("Shotgun metagenomic sequencing.")
        assert payload["sequencing_type_raw"] == "shotgun metagenomics"

    def test_extracts_sample_size_from_n_equals(self):
        payload = _heuristic_payload_from_text("A total of n=42 were enrolled.")
        assert payload["sample_size_raw"] == 42

    def test_extracts_sample_size_from_mention(self):
        payload = _heuristic_payload_from_text("We enrolled 25 patients in total.")
        assert payload["sample_size_raw"] == 25

    def test_marks_source_as_heuristic(self):
        payload = _heuristic_payload_from_text("Some text about humans.")
        assert payload["_source"] == "heuristic"

    def test_detects_differential_abundance_signal(self):
        payload = _heuristic_payload_from_text(
            "Bacteroides was significantly enriched in cases vs controls."
        )
        assert payload["has_differential_abundance"] is True
        assert payload["differential_abundance_confidence"] > 0


class TestBuildCurationSummary:
    def test_includes_present_fields_only(self):
        field_results = {
            "condition": {"status": "PRESENT", "value": "IBD"},
            "host_species": {"status": "PRESENT", "value": "Homo sapiens"},
            "body_site": {"status": "ABSENT", "value": ""},
        }
        summary = _build_curation_summary(field_results)
        assert "Condition: IBD." in summary
        assert "Host: Homo sapiens." in summary
        assert "Body site" not in summary

    def test_empty_field_results_returns_empty_string(self):
        assert _build_curation_summary({}) == ""


class TestPostprocessFieldResults:
    def test_patches_absent_host_species_when_text_mentions_humans(self):
        field_results = {
            "host_species": {
                "value": "",
                "status": "ABSENT",
                "confidence": 0.0,
            }
        }
        result = _postprocess_field_results(
            field_results, "30 patients were enrolled in this study."
        )
        assert result["host_species"]["status"] == "PRESENT"
        assert result["host_species"]["value"] == "Homo sapiens"
        assert result["host_species"]["ontology_id"] == "NCBITaxon:9606"

    def test_leaves_present_host_species_untouched(self):
        field_results = {
            "host_species": {
                "value": "Mus musculus",
                "status": "PRESENT",
                "confidence": 0.9,
                "ontology_id": "NCBITaxon:10090",
            }
        }
        result = _postprocess_field_results(field_results, "patients with disease")
        assert result["host_species"]["value"] == "Mus musculus"

    def test_no_change_when_no_human_mention(self):
        field_results = {
            "host_species": {"value": "", "status": "ABSENT", "confidence": 0.0}
        }
        result = _postprocess_field_results(field_results, "bacterial culture media")
        assert result["host_species"]["status"] == "ABSENT"

    def test_does_not_force_human_when_text_mentions_mouse(self):
        """Regression test: an ABSENT host_species must not get force-patched
        to "Homo sapiens" just because the text says "controls" - mouse/rat
        studies use that word too, and an explicit animal mention in the same
        text should block the human-assumption patch."""
        field_results = {
            "host_species": {"value": "", "status": "ABSENT", "confidence": 0.0}
        }
        result = _postprocess_field_results(
            field_results,
            "Mice were compared to wild-type controls fed a high-fat diet.",
        )
        assert result["host_species"]["status"] == "ABSENT"

    def test_handles_missing_field_keys_gracefully(self):
        result = _postprocess_field_results({}, "patients with disease")
        assert isinstance(result, dict)


class TestFieldResultsFromUnifiedPayload:
    def test_maps_all_five_fields(self):
        payload = {
            "host_species_raw": "human",
            "body_site_raw": "fecal samples",
            "condition_raw": "diabetes",
            "sequencing_type_raw": "16S rRNA gene sequencing",
            "sample_size_raw": 42,
        }
        results = _field_results_from_unified_payload(payload)
        assert set(results.keys()) == {
            "host_species",
            "body_site",
            "condition",
            "sequencing_type",
            "sample_size",
        }
        assert results["host_species"]["status"] == "PRESENT"

    def test_heuristic_source_caps_confidence(self):
        payload = {
            "host_species_raw": "human",
            "_source": "heuristic",
        }
        results = _field_results_from_unified_payload(payload)
        if results["host_species"]["status"] == "PRESENT":
            assert results["host_species"]["confidence"] <= 0.75
        elif results["host_species"]["status"] == "PARTIALLY_PRESENT":
            assert results["host_species"]["confidence"] <= 0.60

    def test_empty_payload_yields_all_absent(self):
        results = _field_results_from_unified_payload({})
        for field in results.values():
            assert field["status"] == "ABSENT"


class TestAvgConfidence:
    def test_averages_confidence_values(self):
        field_results = {
            "a": {"confidence": 1.0},
            "b": {"confidence": 0.0},
        }
        assert _avg_confidence(field_results) == 0.5

    def test_empty_returns_zero(self):
        assert _avg_confidence({}) == 0.0


class TestResolveDiffAbundance:
    def test_uses_payload_values_when_present(self):
        payload = {
            "has_differential_abundance": True,
            "differential_abundance_confidence": 0.8,
        }
        has_da, conf = _resolve_diff_abundance(payload, "irrelevant fallback text")
        assert has_da is True
        assert conf == 0.8

    def test_falls_back_to_heuristic_on_bad_payload_types(self):
        payload = {
            "has_differential_abundance": True,
            "differential_abundance_confidence": "not-a-number",
        }
        has_da, conf = _resolve_diff_abundance(
            payload, "Species X was significantly enriched, p<0.01."
        )
        assert isinstance(has_da, bool)
        assert isinstance(conf, float)


class TestExtractYear:
    def test_extracts_four_digit_year(self):
        assert extract_year("2023 Jan 15") == 2023

    def test_extracts_year_from_1900s(self):
        assert extract_year("1998-05-01") == 1998

    def test_returns_none_when_no_year_found(self):
        assert extract_year("no date here") is None

    def test_handles_non_string_input(self):
        assert extract_year(2021) == 2021
        assert extract_year(None) is None


class TestCreateEmptyFieldResult:
    def test_returns_safe_absent_result(self):
        result = create_empty_field_result("host_species")
        assert result["status"] == "ABSENT"
        assert result["confidence"] == 0.0
        assert result["reason_if_missing"] == "Analysis failed or timed out"


class TestDetectDifferentialAbundance:
    def test_empty_text_returns_false(self):
        has_da, conf = detect_differential_abundance("")
        assert has_da is False
        assert conf == 0.0

    def test_strong_signal_detected(self):
        has_da, conf = detect_differential_abundance(
            "Bacteroides was significantly enriched and Firmicutes depleted, FDR < 0.05."
        )
        assert has_da is True
        assert conf >= 0.6

    def test_weak_signal_alone_not_classified_as_differential(self):
        has_da, conf = detect_differential_abundance(
            "We measured relative abundance and community structure."
        )
        assert has_da is False
        assert 0.0 < conf < 0.6

    def test_no_signal_returns_zero_confidence(self):
        has_da, conf = detect_differential_abundance("This text has no relevant terms.")
        assert has_da is False
        assert conf == 0.0

    def test_score_is_clamped_to_valid_range(self):
        has_da, conf = detect_differential_abundance(
            "significantly different, enriched, depleted, upregulated, downregulated, "
            "FDR, adjusted p-value, compared to, versus, increase, decrease, "
            "differential abundance " * 3
        )
        assert 0.0 <= conf <= 1.0


def _make_mock_retriever(
    title="A Test Paper", abstract="Abstract about 30 human patients.", full_text=""
):
    retriever = MagicMock()
    retriever.get_texts_for_analysis_async = AsyncMock(
        return_value={
            "title": title,
            "abstract": abstract,
            "full_text": full_text,
            "publication_date": "2023-05-01",
            "journal": "Test Journal",
            "authors": ["A. Author"],
        }
    )
    return retriever


def _make_mock_cache_manager(cached_result=None, cache_valid=False):
    cache_manager = MagicMock()
    cache_manager.get_analysis_result.return_value = cached_result
    cache_manager.is_cache_valid.return_value = cache_valid
    cache_manager.store_analysis_result.return_value = None
    return cache_manager


def _make_mock_unified_qa(json_text='{"host_species_raw": "human"}'):
    qa = MagicMock()
    qa.chat = AsyncMock(return_value={"text": json_text})
    return qa


@pytest.mark.asyncio
class TestAnalyzePaperSimple:
    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_full_pipeline_on_cache_miss(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager(cached_result=None)
        mock_get_retriever.return_value = _make_mock_retriever()
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_simple("12345678")

        assert result is not None
        assert result["pmid"] == "12345678"
        assert result["title"] == "A Test Paper"
        assert result["fields"]["host_species"]["status"] == "PRESENT"
        assert "curation_summary" in result
        assert result["model_used"]

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_valid_good_quality_cache_without_calling_llm(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        cached = {
            "timestamp": "2024-01-01T00:00:00",
            "analysis_data": {
                "pmid": "12345678",
                "fields": {"host_species": {"status": "PRESENT"}},
            },
        }
        mock_get_cache.return_value = _make_mock_cache_manager(
            cached_result=cached, cache_valid=True
        )
        mock_retriever = _make_mock_retriever()
        mock_get_retriever.return_value = mock_retriever
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_simple("12345678")

        assert result == cached["analysis_data"]
        mock_retriever.get_texts_for_analysis_async.assert_not_called()

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_recomputes_when_cache_is_low_quality(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        cached = {
            "timestamp": "2024-01-01T00:00:00",
            "analysis_data": {
                "pmid": "12345678",
                "fields": {
                    key: {"status": "ABSENT"}
                    for key in (
                        "host_species",
                        "body_site",
                        "condition",
                        "sequencing_type",
                        "sample_size",
                    )
                },
            },
        }
        mock_get_cache.return_value = _make_mock_cache_manager(
            cached_result=cached, cache_valid=True
        )
        mock_retriever = _make_mock_retriever()
        mock_get_retriever.return_value = mock_retriever
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_simple("12345678")

        mock_retriever.get_texts_for_analysis_async.assert_called_once()
        assert result["fields"]["host_species"]["status"] == "PRESENT"

    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever", return_value=None)
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_none_when_retriever_unavailable(
        self, mock_get_cache, mock_get_retriever
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        result = await analyze_paper_simple("12345678")
        assert result is None

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_none_when_no_title_or_abstract(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        mock_get_retriever.return_value = _make_mock_retriever(title="", abstract="")
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_simple("12345678")

        assert result is None

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_falls_back_to_heuristic_on_empty_llm_payload(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        mock_get_retriever.return_value = _make_mock_retriever(
            abstract="A study of 50 patients with diabetes using 16S rRNA sequencing."
        )
        mock_get_qa.return_value = _make_mock_unified_qa(json_text="not valid json")

        result = await analyze_paper_simple("12345678")

        assert result is not None
        assert result["fields"]["host_species"]["status"] == "PRESENT"

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_force_refresh_bypasses_valid_cache(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        cached = {
            "timestamp": "2024-01-01T00:00:00",
            "analysis_data": {"pmid": "12345678", "fields": {}},
        }
        mock_get_cache.return_value = _make_mock_cache_manager(
            cached_result=cached, cache_valid=True
        )
        mock_retriever = _make_mock_retriever()
        mock_get_retriever.return_value = mock_retriever
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_simple("12345678", force_refresh=True)

        mock_retriever.get_texts_for_analysis_async.assert_called_once()
        assert result["pmid"] == "12345678"

    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_none_on_unexpected_exception(self, mock_get_cache):
        mock_get_cache.side_effect = RuntimeError("boom")
        result = await analyze_paper_simple("12345678")
        assert result is None


@pytest.mark.asyncio
class TestAnalyzePaperWithRag:
    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_use_rag_false_still_produces_result(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        mock_get_retriever.return_value = _make_mock_retriever()
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_with_rag("12345678", use_rag=False)

        assert result is not None
        assert result["pmid"] == "12345678"
        assert result["rag_enabled"] is False

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_short_full_text_skips_chunking_but_still_succeeds(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        mock_get_retriever.return_value = _make_mock_retriever(full_text="short")
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_with_rag("12345678", use_rag=True)

        assert result is not None
        assert result["rag_enabled"] is True

    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever", return_value=None)
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_none_when_retriever_unavailable(
        self, mock_get_cache, mock_get_retriever
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        result = await analyze_paper_with_rag("12345678")
        assert result is None

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_none_when_no_content(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        mock_get_retriever.return_value = _make_mock_retriever(title="", abstract="")
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_with_rag("12345678")

        assert result is None

    @patch("app.services.bugsigdb_analyzer.is_in_bugsigdb", return_value=False)
    @patch("app.services.bugsigdb_analyzer.get_unified_qa")
    @patch("app.services.bugsigdb_analyzer.get_pubmed_retriever")
    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_rag_config_as_plain_dict(
        self, mock_get_cache, mock_get_retriever, mock_get_qa, mock_in_bugsigdb
    ):
        mock_get_cache.return_value = _make_mock_cache_manager()
        mock_get_retriever.return_value = _make_mock_retriever()
        mock_get_qa.return_value = _make_mock_unified_qa()

        result = await analyze_paper_with_rag(
            "12345678", rag_config={"enabled": True, "rerank_method": "keyword"}
        )

        assert result is not None
        assert result["rag_config_used"]["rerank_method"] == "keyword"

    @patch("app.services.bugsigdb_analyzer.get_cache_manager")
    async def test_returns_none_on_unexpected_exception(self, mock_get_cache):
        mock_get_cache.side_effect = RuntimeError("boom")
        result = await analyze_paper_with_rag("12345678")
        assert result is None

"""
Tests for the third (URL-based) analysis pipeline's AgentOrchestrator.

Covers the pure parsing/aggregation helpers directly (no network/LLM calls
needed) plus analyze_study() with paperqa's agent_query() mocked out, since
real agent_query() calls require a live LLM API key and network access.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.extraction_schemas import (
    ExperimentFields,
    ExtractedExperiment,
    FieldResult,
    MicrobialSignature,
)
from app.services.agent_orchestrator import (
    PAPERQA_AGENT_API_AVAILABLE,
    AgentOrchestrator,
    _avg_confidence,
    _check_missing_fields,
    _field_result_from_raw,
)

_SKIP_REASON = (
    "requires paper-qa>=5.0 (Settings-based agent API), which needs Python>=3.11"
)


# ---------------------------------------------------------------------------
# _field_result_from_raw
# ---------------------------------------------------------------------------


def test_field_result_from_raw_empty_value_is_absent():
    result = _field_result_from_raw(None)
    assert result.status == "ABSENT"
    assert result.value == ""

    result = _field_result_from_raw("   ")
    assert result.status == "ABSENT"


def test_field_result_from_raw_without_normalizer_is_heuristic_present():
    result = _field_result_from_raw("human")
    assert result.status == "PRESENT"
    assert result.value == "human"
    assert result.confidence == 0.70


def test_field_result_from_raw_normalizer_present():
    def fake_normalizer(value):
        return SimpleNamespace(
            label="Homo sapiens",
            status="PRESENT",
            ontology_id="NCBITaxon:9606",
            mapping_confidence=0.9,
        )

    result = _field_result_from_raw("human", fake_normalizer)
    assert result.status == "PRESENT"
    assert result.value == "Homo sapiens"
    assert result.ontology_id == "NCBITaxon:9606"
    assert result.mapping_confidence == 0.9


def test_field_result_from_raw_normalizer_absent():
    def fake_normalizer(value):
        return SimpleNamespace(
            label="", status="ABSENT", ontology_id="", mapping_confidence=0.0
        )

    result = _field_result_from_raw("nonsense", fake_normalizer)
    assert result.status == "ABSENT"
    assert result.value == ""
    assert result.reason_if_missing == "Not found"


def test_field_result_from_raw_normalizer_exception_falls_back_to_heuristic():
    def broken_normalizer(value):
        raise RuntimeError("normalizer exploded")

    result = _field_result_from_raw("gut", broken_normalizer)
    assert result.status == "PRESENT"
    assert result.value == "gut"
    assert result.confidence == 0.70


# ---------------------------------------------------------------------------
# _avg_confidence / _check_missing_fields
# ---------------------------------------------------------------------------


def _present_field(value="x", confidence=0.8):
    return FieldResult(value=value, status="PRESENT", confidence=confidence)


def test_avg_confidence_averages_all_six_fields():
    fields = ExperimentFields(
        host_species=_present_field(confidence=1.0),
        body_site=_present_field(confidence=0.5),
        condition=_present_field(confidence=0.5),
        sequencing_type=_present_field(confidence=0.5),
        sample_size=_present_field(confidence=0.5),
        taxa_level=_present_field(confidence=0.5),
    )
    assert _avg_confidence(fields) == pytest.approx((1.0 + 0.5 * 5) / 6)


def test_check_missing_fields_no_experiments():
    assert _check_missing_fields([]) == ["No experiments extracted"]


def test_check_missing_fields_all_present():
    fields = ExperimentFields(
        host_species=_present_field(),
        body_site=_present_field(),
        condition=_present_field(),
        sequencing_type=_present_field(),
        sample_size=_present_field(),
        taxa_level=_present_field(),
    )
    exp = ExtractedExperiment(experiment_id="e1", title="Exp 1", fields=fields)
    assert _check_missing_fields([exp]) == []


def test_check_missing_fields_reports_absent_fields():
    fields = ExperimentFields(
        host_species=_present_field(),
        body_site=FieldResult.absent(),
        condition=_present_field(),
        sequencing_type=FieldResult.absent(),
        sample_size=_present_field(),
        taxa_level=_present_field(),
    )
    exp = ExtractedExperiment(experiment_id="e1", title="Exp 1", fields=fields)
    assert _check_missing_fields([exp]) == ["body_site", "sequencing_type"]


def test_check_missing_fields_present_in_any_experiment_is_not_missing():
    """A field absent in one experiment but present in another isn't 'missing'."""
    fields_missing_host = ExperimentFields(
        host_species=FieldResult.absent(),
        body_site=_present_field(),
        condition=_present_field(),
        sequencing_type=_present_field(),
        sample_size=_present_field(),
        taxa_level=_present_field(),
    )
    fields_all_present = ExperimentFields(
        host_species=_present_field(),
        body_site=_present_field(),
        condition=_present_field(),
        sequencing_type=_present_field(),
        sample_size=_present_field(),
        taxa_level=_present_field(),
    )
    exp1 = ExtractedExperiment(
        experiment_id="e1", title="Exp 1", fields=fields_missing_host
    )
    exp2 = ExtractedExperiment(
        experiment_id="e2", title="Exp 2", fields=fields_all_present
    )
    assert _check_missing_fields([exp1, exp2]) == ["host_species"]


# ---------------------------------------------------------------------------
# AgentOrchestrator._parse_experiments_from_response
# ---------------------------------------------------------------------------


def test_parse_experiments_single_block(orchestrator):
    answer = (
        "Experiment 1: Gut microbiome in IBD patients\n"
        "Host: human\n"
        "Sample site: gut\n"
        "Disease: inflammatory bowel disease\n"
        "Sequencing method: 16S rRNA gene sequencing\n"
        "Taxonomic level: genus\n"
        "N: 42\n"
    )
    experiments = orchestrator._parse_experiments_from_response(
        answer=answer, contexts=[], pmid="123"
    )
    assert len(experiments) == 1
    exp = experiments[0]
    # host_species/body_site go through the real normalizers (ontology labels)
    assert exp.fields.host_species.value == "Homo sapiens"
    assert exp.fields.body_site.value == "feces"
    assert exp.fields.condition.value == "inflammatory bowel disease"
    assert exp.fields.sequencing_type.value == "16S"
    assert exp.fields.taxa_level.value == "genus"
    assert exp.fields.sample_size.value == "42"


def test_parse_experiments_multiple_blocks(orchestrator):
    answer = (
        "Study 1: Healthy cohort\n"
        "Host: mouse\n"
        "Sample site: skin\n"
        "\n"
        "Study 2: Diseased cohort\n"
        "Host: human\n"
        "Sample site: oral cavity\n"
    )
    experiments = orchestrator._parse_experiments_from_response(
        answer=answer, contexts=[], pmid="999"
    )
    assert len(experiments) == 2
    assert experiments[0].fields.host_species.value == "Mus musculus"
    assert experiments[0].fields.body_site.value == "skin"
    assert experiments[1].fields.host_species.value == "Homo sapiens"
    assert experiments[1].fields.body_site.value == "saliva"


def test_parse_experiments_empty_answer_produces_no_experiments(orchestrator):
    experiments = orchestrator._parse_experiments_from_response(
        answer="", contexts=[], pmid="1"
    )
    assert experiments == []


def test_parse_experiments_unstructured_answer_still_yields_one_experiment(
    orchestrator,
):
    """No key:value lines, but a non-empty answer -> single fallback experiment."""
    answer = "This paper discusses microbiome composition without clear structure."
    experiments = orchestrator._parse_experiments_from_response(
        answer=answer, contexts=[], pmid="1"
    )
    assert len(experiments) == 1
    assert experiments[0].fields.host_species.status == "ABSENT"


def test_parse_experiments_evidence_chunks_capped_at_three(orchestrator):
    contexts = [SimpleNamespace(context=f"ctx{i}") for i in range(5)]
    answer = "Experiment 1: Test\nHost: human\n"
    experiments = orchestrator._parse_experiments_from_response(
        answer=answer, contexts=contexts, pmid="1"
    )
    assert experiments[0].evidence_chunks == ["ctx0", "ctx1", "ctx2"]


# ---------------------------------------------------------------------------
# AgentOrchestrator._parse_signatures_from_response
# ---------------------------------------------------------------------------


def test_parse_signatures_increased_and_decreased():
    answer = (
        "Bacteroides was significantly increased in the disease group (p<0.01).\n"
        "Firmicutes was decreased compared to controls (p=0.03).\n"
        "This line has no direction keyword and should be skipped.\n"
    )
    signatures = AgentOrchestrator._parse_signatures_from_response(answer, [])
    assert len(signatures) == 2
    assert signatures[0].abundance_change == "increased"
    assert signatures[0].statistical_significance is not None
    assert signatures[1].abundance_change == "decreased"


def test_parse_signatures_empty_answer():
    assert AgentOrchestrator._parse_signatures_from_response("", []) == []


def test_parse_signatures_no_pvalue_still_extracted_with_lower_confidence():
    answer = "Prevotella levels were elevated in the treatment group."
    signatures = AgentOrchestrator._parse_signatures_from_response(answer, [])
    assert len(signatures) == 1
    assert signatures[0].statistical_significance is None
    assert signatures[0].confidence == 0.50


# ---------------------------------------------------------------------------
# AgentOrchestrator._aggregate_diff_abundance
# ---------------------------------------------------------------------------


def test_aggregate_diff_abundance_no_experiments():
    has_da, conf = AgentOrchestrator._aggregate_diff_abundance([])
    assert has_da is False
    assert conf == 0.0


def test_aggregate_diff_abundance_takes_max_confidence():
    fields = ExperimentFields()
    exp1 = ExtractedExperiment(
        experiment_id="e1",
        title="Exp 1",
        fields=fields,
        has_differential_abundance=True,
        differential_abundance_confidence=0.6,
    )
    exp2 = ExtractedExperiment(
        experiment_id="e2",
        title="Exp 2",
        fields=fields,
        has_differential_abundance=False,
        differential_abundance_confidence=0.0,
    )
    exp3 = ExtractedExperiment(
        experiment_id="e3",
        title="Exp 3",
        fields=fields,
        has_differential_abundance=True,
        differential_abundance_confidence=0.9,
    )
    has_da, conf = AgentOrchestrator._aggregate_diff_abundance([exp1, exp2, exp3])
    assert has_da is True
    assert conf == 0.9


# ---------------------------------------------------------------------------
# AgentOrchestrator.analyze_study (agent_query mocked out)
# ---------------------------------------------------------------------------


@pytest.fixture
def orchestrator():
    if not PAPERQA_AGENT_API_AVAILABLE:
        pytest.skip(_SKIP_REASON)
    return AgentOrchestrator(
        llm_model="gemini/gemini-2.0-flash",
        embedding_model="gemini/text-embedding-004",
    )


@pytest.fixture
def sample_chunks():
    if not PAPERQA_AGENT_API_AVAILABLE:
        pytest.skip(_SKIP_REASON)
    from paperqa.types import Doc, Text

    doc = Doc(docname="study_1", dockey="key_1", citation="Citation")
    return [
        Text(text="Sample text chunk about the gut microbiome.", name="t1", doc=doc),
    ]


@pytest.mark.asyncio
async def test_analyze_study_happy_path(monkeypatch, orchestrator, sample_chunks):
    experiment_response = SimpleNamespace(
        session=SimpleNamespace(
            answer=(
                "Experiment 1: Gut study\n"
                "Host: human\n"
                "Sample site: gut\n"
                "Disease: IBD\n"
                "Sequencing method: 16S rRNA gene sequencing\n"
                "Taxonomic level: genus\n"
                "N: 30\n"
            ),
            contexts=[],
        )
    )
    signature_response = SimpleNamespace(
        session=SimpleNamespace(
            answer="Bacteroides was increased in cases (p<0.05).",
            contexts=[],
        )
    )

    mock_agent_query = AsyncMock(side_effect=[experiment_response, signature_response])
    monkeypatch.setattr("app.services.agent_orchestrator.agent_query", mock_agent_query)

    result = await orchestrator.analyze_study(
        chunks=sample_chunks,
        study_id="study_1",
        source_url="https://example.org/paper",
        pmid="123456",
    )

    assert result.pmid == "123456"
    assert len(result.experiments) == 1
    assert result.total_signatures == 1
    assert result.curation_ready is True
    assert result.missing_fields == []
    assert result.has_differential_abundance is True
    assert mock_agent_query.await_count == 2


@pytest.mark.asyncio
async def test_analyze_study_agent_query_failure_yields_no_experiments(
    monkeypatch, orchestrator, sample_chunks
):
    mock_agent_query = AsyncMock(side_effect=RuntimeError("LLM call failed"))
    monkeypatch.setattr("app.services.agent_orchestrator.agent_query", mock_agent_query)

    result = await orchestrator.analyze_study(
        chunks=sample_chunks,
        study_id="study_2",
        source_url="https://example.org/paper2",
    )

    assert result.experiments == []
    assert result.total_signatures == 0
    assert result.curation_ready is False
    assert result.missing_fields == ["No experiments extracted"]


# ---------------------------------------------------------------------------
# AgentOrchestrator._load_docs
# ---------------------------------------------------------------------------


def test_load_docs_builds_docs_from_chunks(sample_chunks):
    docs = AgentOrchestrator._load_docs(sample_chunks)
    assert len(docs.texts) == 1
    assert "key_1" in docs.docs
    assert "study_1" in docs.docnames

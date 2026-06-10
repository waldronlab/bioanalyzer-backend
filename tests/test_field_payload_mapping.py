from app.models.extraction_schemas import (
    ExperimentFields,
    ExtractedExperiment,
    MicrobialSignature,
    StudyAnalysisResult,
)


def test_orchestrator_signature_da_flags():
    experiment = ExtractedExperiment(
        experiment_id="exp_1",
        title="Test",
        fields=ExperimentFields(),
    )
    signatures = [
        MicrobialSignature(
            taxon_name="Bacteroides",
            abundance_change="increased",
            statistical_significance="p < 0.05",
            evidence_text="Bacteroides increased in cases",
            confidence=0.7,
        )
    ]

    experiment.apply_signature_da_flags(signatures)

    assert experiment.has_differential_abundance is True
    assert experiment.differential_abundance_confidence > 0.7


def test_study_result_to_analyzer_uses_study_level_da():
    study = StudyAnalysisResult(
        pmid="1",
        study_id="1",
        source_url="http://example.com",
        has_differential_abundance=True,
        differential_abundance_confidence=0.88,
        experiments=[
            ExtractedExperiment(
                experiment_id="exp_1",
                title="Test",
                fields=ExperimentFields(),
                has_differential_abundance=False,
                differential_abundance_confidence=0.0,
            )
        ],
    )

    flat = study.to_analyzer_result()

    assert flat["has_differential_abundance"] is True
    assert flat["differential_abundance_confidence"] == 0.88

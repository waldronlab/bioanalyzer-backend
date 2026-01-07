"""Agent orchestrator using Paper-QA's agent_query system."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from paperqa import Docs, Settings
from paperqa.settings import AgentSettings
from paperqa.agents import agent_query
from paperqa.types import Text, Doc

from app.models.extraction_schemas import (
    ExtractedExperiment,
    MicrobialSignature,
    ExperimentMetadata,
    StudyAnalysisResult,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates extraction workflow using Paper-QA's agent system."""

    def __init__(
        self,
        llm_model: str = "gemini/gemini-2.0-flash",
        embedding_model: str = "gemini/text-embedding-004",
    ):
        """Initialize agent orchestrator."""
        self.llm_model = llm_model
        self.embedding_model = embedding_model

        # Create a writable paper directory (Paper-QA needs this for caching)
        # Use a temp directory or a directory in the current working directory
        # Make sure to use absolute path to avoid issues
        paper_dir = Path(tempfile.gettempdir()) / "bioanalyzer_paperqa"
        try:
            paper_dir = paper_dir.resolve()  # Get absolute path
            paper_dir.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = paper_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not use temp directory {paper_dir}: {e}")
            # Fall back to a directory in the current working directory
            paper_dir = Path("cache") / "paperqa"
            try:
                paper_dir = paper_dir.resolve()  # Get absolute path
                paper_dir.mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e2:
                logger.error(f"Could not create paper directory {paper_dir}: {e2}")
                # Last resort: use /tmp which should always be writable
                paper_dir = Path("/tmp") / "bioanalyzer_paperqa"
                paper_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Using Paper-QA directory: {paper_dir.absolute()}")

        self.settings = Settings(
            llm=llm_model,
            summary_llm=llm_model,
            embedding=embedding_model,
            agent=AgentSettings(
                agent_llm=llm_model,
                agent_type="simple",
            ),
            paper_directory=str(paper_dir.absolute()),
        )

        logger.info(f"Initialized agent orchestrator with {llm_model}")

    async def analyze_study(
        self, chunks: List[Text], study_id: str, source_url: str
    ) -> StudyAnalysisResult:
        """Analyze study using agent workflow."""
        logger.info(f"Starting study analysis: {study_id}")

        docs = Docs(settings=self.settings)
        for chunk in chunks:
            docs.texts.append(chunk)
            if chunk.doc.dockey not in docs.docs:
                docs.docs[chunk.doc.dockey] = chunk.doc
                docs.docnames.add(chunk.doc.docname)

        logger.info(f"Added {len(chunks)} chunks to Docs")

        # Extract experiments
        experiments = await self._extract_experiments(docs)

        # Extract signatures for each experiment
        for experiment in experiments:
            signatures = await self._extract_signatures(docs, experiment)
            experiment.signatures = signatures

        # Calculate totals and readiness
        total_signatures = sum(len(exp.signatures) for exp in experiments)
        missing_fields = self._check_missing_fields(experiments)
        curation_ready = len(missing_fields) == 0 and total_signatures > 0

        # Calculate confidence
        if experiments:
            avg_confidence = sum(
                sum(sig.confidence for sig in exp.signatures)
                / max(len(exp.signatures), 1)
                for exp in experiments
            ) / len(experiments)
        else:
            avg_confidence = 0.0

        result = StudyAnalysisResult(
            study_id=study_id,
            source_url=source_url,
            experiments=experiments,
            total_signatures=total_signatures,
            curation_ready=curation_ready,
            missing_fields=missing_fields,
            confidence_score=avg_confidence,
            analysis_timestamp=datetime.now(),
        )

        logger.info(
            f"Analysis complete: {len(experiments)} experiments, "
            f"{total_signatures} signatures, ready={curation_ready}"
        )

        return result

    async def _extract_experiments(self, docs: Docs) -> List[ExtractedExperiment]:
        """Extract experiments from the study."""
        logger.info("Extracting experiments...")

        query = """
        Identify all distinct experiments or studies described in this paper.
        For each experiment, extract:
        1. A brief title or description
        2. Host species studied
        3. Body site sampled
        4. Condition or treatment
        5. Sequencing method used
        6. Taxonomic level analyzed
        7. Sample size

        List each experiment separately.
        """

        try:
            response = await agent_query(query=query, settings=self.settings, docs=docs)

            # Parse response to extract structured data
            experiments = self._parse_experiments_from_response(
                response.session.answer, response.session.contexts
            )

            logger.info(f"Extracted {len(experiments)} experiments")
            return experiments

        except Exception as e:
            logger.error(f"Error extracting experiments: {e}")
            return []

    async def _extract_signatures(
        self, docs: Docs, experiment: ExtractedExperiment
    ) -> List[MicrobialSignature]:
        """Extract microbial signatures for an experiment."""
        logger.info(f"Extracting signatures for: {experiment.title}")

        query = f"""
        For the experiment "{experiment.title}", identify all microbial taxa
        that showed significant changes. For each taxon, extract:
        1. Taxon name
        2. Direction of change (increased/decreased)
        3. Statistical significance (p-value)
        4. Comparison groups
        5. Supporting evidence text

        Focus on statistically significant findings.
        """

        try:
            response = await agent_query(query=query, settings=self.settings, docs=docs)

            # Parse signatures from response
            signatures = self._parse_signatures_from_response(
                response.session.answer, response.session.contexts
            )

            logger.info(f"Extracted {len(signatures)} signatures")
            return signatures

        except Exception as e:
            logger.error(f"Error extracting signatures: {e}")
            return []

    def _parse_experiments_from_response(
        self, answer: str, contexts: list
    ) -> List[ExtractedExperiment]:
        """Parse experiments from agent response."""
        # Simple parsing - in production, use more sophisticated NLP
        experiments = []

        # Split by experiment markers
        lines = answer.split("\n")
        current_exp = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for experiment indicators
            if any(
                marker in line.lower() for marker in ["experiment", "study", "cohort"]
            ):
                if current_exp:
                    experiments.append(current_exp)

                current_exp = ExtractedExperiment(
                    experiment_id=f"exp_{len(experiments) + 1}",
                    title=line,
                    metadata=ExperimentMetadata(),
                    evidence_chunks=[ctx.context for ctx in contexts[:3]],
                )

            # Extract metadata fields
            elif current_exp:
                line_lower = line.lower()
                if "host" in line_lower or "species" in line_lower:
                    current_exp.metadata.host_species = line.split(":")[-1].strip()
                elif "body site" in line_lower or "sample site" in line_lower:
                    current_exp.metadata.body_site = line.split(":")[-1].strip()
                elif "condition" in line_lower or "disease" in line_lower:
                    current_exp.metadata.condition = line.split(":")[-1].strip()
                elif "sequencing" in line_lower or "method" in line_lower:
                    current_exp.metadata.sequencing_type = line.split(":")[-1].strip()
                elif "taxa" in line_lower or "taxonomic" in line_lower:
                    current_exp.metadata.taxa_level = line.split(":")[-1].strip()
                elif "sample size" in line_lower or "participants" in line_lower:
                    try:
                        size_str = line.split(":")[-1].strip()
                        current_exp.metadata.sample_size = int(
                            "".join(filter(str.isdigit, size_str))
                        )
                    except:
                        pass

        if current_exp:
            experiments.append(current_exp)

        return experiments

    def _parse_signatures_from_response(
        self, answer: str, contexts: list
    ) -> List[MicrobialSignature]:
        """Parse microbial signatures from agent response."""
        signatures = []

        lines = answer.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Look for taxon mentions with change indicators
            if any(
                word in line.lower()
                for word in ["increased", "decreased", "enriched", "depleted"]
            ):
                # Extract taxon name (simple heuristic)
                words = line.split()
                taxon_name = None
                abundance_change = None

                for i, word in enumerate(words):
                    if word.lower() in ["increased", "enriched", "higher"]:
                        abundance_change = "increased"
                        if i > 0:
                            taxon_name = words[i - 1]
                    elif word.lower() in ["decreased", "depleted", "lower", "reduced"]:
                        abundance_change = "decreased"
                        if i > 0:
                            taxon_name = words[i - 1]

                if taxon_name and abundance_change:
                    signatures.append(
                        MicrobialSignature(
                            taxon_name=taxon_name,
                            abundance_change=abundance_change,
                            evidence_text=line,
                            confidence=0.7,  # Default confidence
                        )
                    )

        return signatures

    def _check_missing_fields(
        self, experiments: List[ExtractedExperiment]
    ) -> List[str]:
        """Check for missing required fields."""
        if not experiments:
            return ["No experiments extracted"]

        missing = set()
        required_fields = [
            "host_species",
            "body_site",
            "condition",
            "sequencing_type",
            "taxa_level",
            "sample_size",
        ]

        for exp in experiments:
            for field in required_fields:
                if getattr(exp.metadata, field) is None:
                    missing.add(field)

        return list(missing)

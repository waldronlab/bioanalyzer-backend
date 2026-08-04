"""
Agent Orchestrator — BioAnalyzer
=================================
Orchestrates extraction using Paper-QA's agent_query system.

Output contract
---------------
Every public method that returns analysis data either returns a
StudyAnalysisResult or a plain dict produced by
StudyAnalysisResult.to_analyzer_result().

The plain dict is structurally identical to the dict returned by
bugsigdb_analyzer.analyze_paper_simple(), which means:
  - data.R / normalize_dataset() can consume it unchanged
  - the cache_manager can store it unchanged
  - the curator table will display the correct columns with correct names

Field name mapping (Python → curator-desk CSV column, see
docs/CURATOR_DESK_CSV_FORMAT.md)
  fields["host_species"]["value"]        → Host Species
  fields["host_species"]["ontology_id"]  → Host Species Ontology ID
  fields["body_site"]["value"]           → Body Site
  fields["body_site"]["ontology_id"]     → Body Site Ontology ID
  fields["condition"]["value"]           → Condition
  fields["condition"]["ontology_id"]     → Condition Ontology ID
  fields["sequencing_type"]["value"]     → Sequencing Type
  fields["sample_size"]["value"]         → Sample Size
  has_differential_abundance             → Differential Abundance
  in_bugsigdb                            → In bsgdb

Per-field status/mapping_confidence still feed `mapping_tier` (auto/review/
none, see app.normalization.grounding) but are not curator-desk CSV columns
themselves; they remain available via the separate `--format csv` export.
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz

from app.models.extraction_schemas import (
    ExperimentFields,
    ExperimentMetadata,
    ExtractedExperiment,
    FieldResult,
    MicrobialSignature,
    StudyAnalysisResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paper-QA directory bootstrap  (must happen before any paperqa import)
# ---------------------------------------------------------------------------

_pqa_temp_dir = Path(tempfile.gettempdir()) / "bioanalyzer_paperqa"
_pqa_temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
# mkdir's mode= only applies on creation; chmod explicitly so a
# pre-existing directory from an earlier run is restricted too.
os.chmod(_pqa_temp_dir, 0o700)
os.environ["PQA_DIRECTORY"] = str(_pqa_temp_dir.absolute())
# paperqa.utils.pqa_directory() (used for paperqa's own default index/
# config storage, e.g. Settings.index_directory) falls back to
# Path.home() / ".pqa" unless PQA_HOME is set, in which case it uses
# Path(PQA_HOME) / ".pqa" instead. Some deployment environments have a
# read-only or unset HOME, so paperqa needs pointing at a writable
# directory — but reassigning the process-wide os.environ["HOME"] (as
# this used to do) also silently changes what every OTHER part of the
# process resolves as the home directory. In particular,
# app.core.settings.SettingsManager.DEFAULT_SETTINGS_DIR is computed as
# Path.home() / ".bioanalyzer" at class-definition/import time, so a
# global HOME reassignment here (depending on which module happens to
# import first) could make user settings resolve to the wrong
# directory. Use paperqa's own PQA_HOME knob instead, which only
# affects paperqa's directory resolution.
os.environ["PQA_HOME"] = str(_pqa_temp_dir.parent.absolute())

_pqa_base_directory: List[Optional[str]] = [str(_pqa_temp_dir.absolute())]

try:
    import paperqa.utils

    _original_pqa_directory = paperqa.utils.pqa_directory

    def _patched_pqa_directory(subdir: str = "") -> Path:
        base = Path(_pqa_base_directory[0] or str(_pqa_temp_dir.absolute()))
        target = (base / subdir) if subdir else base
        target.mkdir(parents=True, exist_ok=True)
        return target

    paperqa.utils.pqa_directory = _patched_pqa_directory
except (ImportError, AttributeError):
    _pqa_base_directory = [None]


try:
    from paperqa import Docs, Settings  # noqa: E402
    from paperqa.settings import AgentSettings  # noqa: E402
    from paperqa.agents import agent_query  # noqa: E402
    from paperqa.types import Text  # noqa: E402

    PAPERQA_AGENT_API_AVAILABLE = True
except ImportError:
    # The Settings-based agent API was introduced in paper-qa>=5.0, which
    # requires Python>=3.11 (see pyproject.toml). On older paper-qa (e.g.
    # the last 4.x release, which a Python<3.11 interpreter is pinned to)
    # these names don't exist at all. Define placeholders so this module —
    # and its type hints, which Python evaluates eagerly without `from
    # __future__ import annotations` — still imports cleanly; the pure
    # helpers below (_field_result_from_raw, _check_missing_fields, etc.)
    # stay usable/testable even when the agent feature itself isn't.
    # AgentOrchestrator.__init__ raises a clear error instead of failing
    # at import time.
    Docs = Settings = AgentSettings = Text = object  # type: ignore

    async def agent_query(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError(
            "AgentOrchestrator requires paper-qa>=5.0 (Settings-based agent "
            "API), which requires Python>=3.11."
        )

    PAPERQA_AGENT_API_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_timestamp() -> str:
    return datetime.now(pytz.UTC).isoformat()


def _avg_confidence(fields: ExperimentFields) -> float:
    """Average confidence across all five BugSigDB fields."""
    values = [
        fields.host_species.confidence,
        fields.body_site.confidence,
        fields.condition.confidence,
        fields.sequencing_type.confidence,
        fields.sample_size.confidence,
    ]
    return sum(values) / len(values)


def _check_missing_fields(experiments: List[ExtractedExperiment]) -> List[str]:
    """
    Return the names of required fields that are ABSENT in every experiment.

    Uses the same field key names as bugsigdb_analyzer so that any downstream
    missing-field reporting is consistent.
    """
    if not experiments:
        return ["No experiments extracted"]

    required: List[str] = [
        "host_species",
        "body_site",
        "condition",
        "sequencing_type",
        "sample_size",
    ]
    missing: set = set()

    for exp in experiments:
        for key in required:
            field: FieldResult = getattr(exp.fields, key)
            if field.status == "ABSENT":
                missing.add(key)

    return sorted(missing)


def _field_result_from_raw(value: Optional[str], normalizer_fn=None) -> FieldResult:
    """
    Convert a raw extracted string to a FieldResult.
    Optionally applies a normalizer from app.normalization.*.
    """
    if not value or not str(value).strip():
        return FieldResult.absent()

    if normalizer_fn is not None:
        try:
            from app.normalization.grounding import TIER_AUTO, tier_for

            term = normalizer_fn(value)
            conf = (
                0.85
                if term.status == "PRESENT"
                else (0.65 if term.status == "PARTIALLY_PRESENT" else 0.0)
            )
            tier = tier_for(term)
            candidates = getattr(term, "candidates", ()) or ()
            return FieldResult(
                value=term.label if term.status != "ABSENT" else "",
                status=term.status,
                confidence=conf,
                ontology_id=term.ontology_id or "",
                mapping_confidence=float(term.mapping_confidence or conf),
                reason_if_missing="" if term.status != "ABSENT" else "Not found",
                raw=getattr(term, "raw", "") or "",
                mapping_tier=tier,
                mapping_candidates=(
                    [{"label": label, "ontology_id": oid} for label, oid in candidates]
                    if tier != TIER_AUTO
                    else []
                ),
            )
        except Exception as e:
            from app.utils.credential_masking import mask_exception_message

            logger.debug(
                "Normalizer %s failed for %r: %s",
                normalizer_fn,
                value,
                mask_exception_message(e),
            )
            # Fall through to heuristic

    # Heuristic: non-empty value → PRESENT with modest confidence
    return FieldResult(
        value=str(value).strip(),
        status="PRESENT",
        confidence=0.70,
        ontology_id="",
        mapping_confidence=0.70,
        reason_if_missing="",
    )


# ---------------------------------------------------------------------------
# AgentOrchestrator
# ---------------------------------------------------------------------------


class AgentOrchestrator:
    """Orchestrates extraction using Paper-QA's agent system.

    Outputs are structurally identical to bugsigdb_analyzer.analyze_paper_simple()
    so that data.R / normalize_dataset() and the curator table work unchanged.
    """

    def __init__(
        self,
        llm_model: str = "gemini/gemini-2.0-flash",
        embedding_model: str = "gemini/text-embedding-004",
    ) -> None:
        if not PAPERQA_AGENT_API_AVAILABLE:
            raise RuntimeError(
                "AgentOrchestrator requires paper-qa>=5.0 (Settings-based "
                "agent API), which requires Python>=3.11. The installed "
                "paper-qa version lacks this API — upgrade paper-qa or run "
                "under Python>=3.11 to use this feature."
            )
        self.llm_model = llm_model
        self.embedding_model = embedding_model

        # ── Writable paper directory ──────────────────────────────────────
        paper_dir = self._resolve_paper_dir()
        paper_dir_str = str(paper_dir.absolute())
        indexes_dir = paper_dir / "indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)

        # Keep the module-level pqa_directory() patch (see top of file) in
        # sync with this instance's chosen directory. This is enough on its
        # own — _patched_pqa_directory reads _pqa_base_directory[0] on every
        # call, so updating the shared list here is all that's needed;
        # re-patching paperqa.utils.pqa_directory again per-instance would
        # just install an equivalent function and serves no purpose beyond
        # what Settings(paper_directory=...) below and this line already do.
        _pqa_base_directory[0] = paper_dir_str

        # ── AgentSettings ─────────────────────────────────────────────────
        agent_settings = self._make_agent_settings(llm_model, indexes_dir)

        self.settings = Settings(
            llm=llm_model,
            summary_llm=llm_model,
            embedding=embedding_model,
            agent=agent_settings,
            paper_directory=paper_dir_str,
        )
        logger.info(
            "AgentOrchestrator ready — model=%s dir=%s", llm_model, paper_dir_str
        )

    # ── private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _resolve_paper_dir() -> Path:
        temp_candidate = Path(tempfile.gettempdir()) / "bioanalyzer_paperqa"
        candidates = [temp_candidate, Path("cache") / "paperqa"]
        for candidate in candidates:
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                if candidate == temp_candidate:
                    # Shared system temp dir is world-writable; restrict
                    # this subdirectory (mode= only applies on creation,
                    # so chmod explicitly to cover pre-existing dirs too).
                    os.chmod(candidate, 0o700)
                probe = candidate / ".write_test"
                probe.write_text("ok")
                probe.unlink()
                logger.info("Paper-QA directory: %s", candidate.absolute())
                return candidate
            except (OSError, PermissionError):
                continue
        # Last-resort
        fallback = Path(tempfile.gettempdir()) / "bioanalyzer_paperqa"
        fallback.mkdir(parents=True, exist_ok=True)
        os.chmod(fallback, 0o700)
        return fallback

    @staticmethod
    def _make_agent_settings(llm_model: str, indexes_dir: Path) -> AgentSettings:
        # Try with explicit indexes kwarg first (some PaperQA versions support it)
        for kwargs in [
            {
                "agent_llm": llm_model,
                "agent_type": "simple",
                "indexes": str(indexes_dir),
            },
            {"agent_llm": llm_model, "agent_type": "simple"},
        ]:
            try:
                s = AgentSettings(**kwargs)
                if "indexes" not in kwargs and hasattr(s, "indexes"):
                    s.indexes = str(indexes_dir)
                return s
            except (TypeError, ValueError):
                continue
        raise RuntimeError("Could not construct AgentSettings — check PaperQA version.")

    # ── Public API ────────────────────────────────────────────────────────

    async def analyze_study(
        self,
        chunks: List[Text],
        study_id: str,
        source_url: str,
        *,
        pmid: str = "",
        title: str = "",
        authors: Optional[List[str]] = None,
        journal: str = "",
        publication_date: str = "",
        year: Optional[int] = None,
        in_bugsigdb: bool = False,
        model_used: str = "",
    ) -> StudyAnalysisResult:
        """
        Analyse a study using the Paper-QA agent workflow.

        Parameters mirror the metadata fields produced by PubMedRetriever so
        callers can pass everything through in one call.  The returned
        StudyAnalysisResult can be converted to a curator-table-compatible
        dict via result.to_analyzer_result().
        """
        logger.info("Starting study analysis: %s (pmid=%s)", study_id, pmid)

        docs = self._load_docs(chunks)

        experiments = await self._extract_experiments(docs, pmid=pmid or study_id)

        for experiment in experiments:
            sigs = await self._extract_signatures(docs, experiment)
            experiment.signatures = sigs
            experiment.apply_signature_da_flags(sigs)
            experiment.sync_metadata()

        # Aggregate differential abundance from all experiments
        # (uses the same logic as bugsigdb_analyzer.detect_differential_abundance)
        has_da, da_conf = self._aggregate_diff_abundance(experiments)
        total_signatures = sum(len(e.signatures) for e in experiments)
        missing = _check_missing_fields(experiments)
        curation_ready = len(missing) == 0 and total_signatures > 0
        avg_conf = (
            sum(_avg_confidence(e.fields) for e in experiments) / len(experiments)
            if experiments
            else 0.0
        )

        return StudyAnalysisResult(
            pmid=pmid or study_id,
            study_id=study_id,
            source_url=source_url,
            title=title,
            authors=authors or [],
            journal=journal,
            publication_date=publication_date,
            year=year,
            has_differential_abundance=has_da,
            differential_abundance_confidence=da_conf,
            in_bugsigdb=in_bugsigdb,
            experiments=experiments,
            total_signatures=total_signatures,
            curation_ready=curation_ready,
            missing_fields=missing,
            confidence_score=avg_conf,
            analysis_timestamp=datetime.now(pytz.UTC),
            model_used=model_used or self.llm_model,
        )

    # ── Internal extraction steps ─────────────────────────────────────────

    @staticmethod
    def _load_docs(chunks: List[Text]) -> Docs:
        docs = Docs()
        for chunk in chunks:
            docs.texts.append(chunk)
            if chunk.doc.dockey not in docs.docs:
                docs.docs[chunk.doc.dockey] = chunk.doc
                docs.docnames.add(chunk.doc.docname)
        return docs

    async def _extract_experiments(
        self, docs: Docs, *, pmid: str
    ) -> List[ExtractedExperiment]:
        logger.info("Extracting experiments for pmid=%s", pmid)
        query = (
            "Identify all distinct experiments or studies described in this paper. "
            "For each experiment extract: host organism, body site sampled, "
            "disease or condition studied, sequencing method, and total sample "
            "size. List each experiment separately."
        )
        try:
            response = await agent_query(query=query, settings=self.settings, docs=docs)
            # Parsing calls the same normalizers as simple_analysis.py/
            # rag_analysis.py, which can make blocking network calls (NCBI/OLS
            # fallback lookups, and now also grounding.py's round-trip/branch/
            # obsolete checks on a cold cache) - run off the event loop for the
            # same reason those two call sites already do.
            experiments = await asyncio.to_thread(
                self._parse_experiments_from_response,
                answer=response.session.answer,
                contexts=response.session.contexts,
                pmid=pmid,
            )
            logger.info(
                "Extracted %d experiment(s) for pmid=%s", len(experiments), pmid
            )
            return experiments
        except Exception as exc:
            logger.error("Experiment extraction failed for pmid=%s: %s", pmid, exc)
            return []

    async def _extract_signatures(
        self, docs: Docs, experiment: ExtractedExperiment
    ) -> List[MicrobialSignature]:
        logger.info(
            "Extracting signatures for experiment: %s", experiment.experiment_id
        )
        query = (
            f'For the experiment "{experiment.title}", identify all microbial taxa '
            "that showed significant changes between groups. "
            "For each taxon provide: name, direction (increased/decreased), "
            "p-value or FDR, comparison groups, and the supporting sentence."
        )
        try:
            response = await agent_query(query=query, settings=self.settings, docs=docs)
            return self._parse_signatures_from_response(
                answer=response.session.answer,
                contexts=response.session.contexts,
            )
        except Exception as exc:
            logger.error(
                "Signature extraction failed for experiment %s: %s",
                experiment.experiment_id,
                exc,
            )
            return []

    # ── Response parsers ──────────────────────────────────────────────────

    def _parse_experiments_from_response(
        self,
        answer: str,
        contexts: list,
        *,
        pmid: str,
    ) -> List[ExtractedExperiment]:
        """
        Parse the LLM answer into ExtractedExperiment objects.

        Uses lazy imports for the normalizers so this module does not hard-require
        them at import time (keeps the test surface small).
        """
        try:
            from app.normalization.body_site import normalize_body_site
            from app.normalization.condition import normalize_condition
            from app.normalization.host_species import normalize_host_species
            from app.normalization.sample_size import normalize_sample_size
            from app.normalization.sequencing_type import normalize_sequencing_type
        except ImportError:
            normalize_host_species = normalize_body_site = normalize_condition = None
            normalize_sequencing_type = normalize_sample_size = None

        experiments: List[ExtractedExperiment] = []
        current_raw: Dict[str, Any] = {}
        current_title = ""

        def _flush() -> None:
            if not current_title and not current_raw:
                return
            exp_id = f"exp_{pmid}_{len(experiments) + 1}"
            fields = ExperimentFields(
                host_species=_field_result_from_raw(
                    current_raw.get("host_species"), normalize_host_species
                ),
                body_site=_field_result_from_raw(
                    current_raw.get("body_site"), normalize_body_site
                ),
                condition=_field_result_from_raw(
                    current_raw.get("condition"), normalize_condition
                ),
                sequencing_type=_field_result_from_raw(
                    current_raw.get("sequencing_type"), normalize_sequencing_type
                ),
                sample_size=_field_result_from_raw(
                    current_raw.get("sample_size"), normalize_sample_size
                ),
            )
            exp = ExtractedExperiment(
                experiment_id=exp_id,
                title=current_title or f"Experiment {len(experiments) + 1}",
                fields=fields,
                evidence_chunks=[ctx.context for ctx in (contexts or [])[:3]],
            )
            exp.sync_metadata()
            experiments.append(exp)

        for line in (answer or "").split("\n"):
            line = line.strip()
            if not line:
                continue

            lower = line.lower()

            # Detect a new experiment block
            if any(kw in lower for kw in ("experiment", "study", "cohort", "group")):
                _flush()
                current_raw = {}
                current_title = line

            # ── field extraction — key: value format ──────────────────────
            # These names map 1-to-1 onto ExperimentFields attribute names.
            elif ":" in line:
                key_raw, _, val = line.partition(":")
                key = key_raw.strip().lower().replace(" ", "_")
                val = val.strip()
                if not val:
                    continue

                # Normalise key aliases to canonical names
                _aliases: Dict[str, str] = {
                    "host": "host_species",
                    "host_organism": "host_species",
                    "species": "host_species",
                    "sample_site": "body_site",
                    "anatomical_site": "body_site",
                    "disease": "condition",
                    "treatment": "condition",
                    "sequencing_method": "sequencing_type",
                    "method": "sequencing_type",
                    "molecular_method": "sequencing_type",
                    "participants": "sample_size",
                    "n": "sample_size",
                    "total_samples": "sample_size",
                }
                canonical = _aliases.get(key, key)

                if canonical in {
                    "host_species",
                    "body_site",
                    "condition",
                    "sequencing_type",
                    "sample_size",
                }:
                    current_raw[canonical] = val

        _flush()

        # If the LLM produced no structured blocks, emit one experiment
        # from whatever we parsed — consistent with single-experiment papers.
        if not experiments and answer:
            fields = ExperimentFields()
            exp = ExtractedExperiment(
                experiment_id=f"exp_{pmid}_1",
                title="Extracted experiment",
                fields=fields,
                evidence_chunks=[ctx.context for ctx in (contexts or [])[:3]],
            )
            exp.sync_metadata()
            experiments.append(exp)

        return experiments

    @staticmethod
    def _parse_signatures_from_response(
        answer: str, contexts: list
    ) -> List[MicrobialSignature]:
        import re

        signatures: List[MicrobialSignature] = []
        for line in (answer or "").split("\n"):
            line = line.strip()
            if not line:
                continue
            lower = line.lower()
            change: Optional[str] = None
            if any(w in lower for w in ("increased", "enriched", "higher", "elevated")):
                change = "increased"
            elif any(w in lower for w in ("decreased", "depleted", "lower", "reduced")):
                change = "decreased"
            if change is None:
                continue

            # Try to pull a p-value
            pval_match = re.search(
                r"p\s*[<=>]\s*0?\.?\d+(?:e[+-]?\d+)?", line, re.IGNORECASE
            )
            stat_sig = pval_match.group(0) if pval_match else None

            # Heuristic taxon: capitalised word near the change indicator
            taxon_match = re.search(r"\b([A-Z][a-z]+(?:\s+[a-z]+)?)\b", line)
            taxon_name = taxon_match.group(1) if taxon_match else "Unknown taxon"

            signatures.append(
                MicrobialSignature(
                    taxon_name=taxon_name,
                    abundance_change=change,
                    statistical_significance=stat_sig,
                    evidence_text=line,
                    confidence=0.70 if stat_sig else 0.50,
                )
            )

        return signatures

    # ── Aggregation helpers ───────────────────────────────────────────────

    @staticmethod
    def _aggregate_diff_abundance(
        experiments: List[ExtractedExperiment],
    ) -> tuple:
        """
        Return (has_differential_abundance, confidence) for the whole study.

        Mirrors the scoring logic in bugsigdb_analyzer.detect_differential_abundance:
        - If any experiment has has_differential_abundance=True, the study has it.
        - Confidence is the max across experiments.
        """
        if not experiments:
            return False, 0.0
        has_da = any(e.has_differential_abundance for e in experiments)
        conf = max(
            (e.differential_abundance_confidence for e in experiments), default=0.0
        )
        return has_da, conf

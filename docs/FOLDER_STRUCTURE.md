# Folder Structure

A map of the repository for fast orientation. 

```
BioAnalyzer-Backend/
├── app/                          # The actual application
│   ├── api/
│   │   ├── app.py                # FastAPI app factory + global exception handler
│   │   ├── routers/
│   │   │   ├── bugsigdb_analysis.py      # v1: /api/v1/analyze/{pmid}
│   │   │   ├── bugsigdb_analysis_v2.py   # v2: /api/v2/analyze/{pmid} (RAG)
│   │   │   ├── study_analysis.py         # /api/v1/analyze-url (3rd pipeline)
│   │   │   └── system.py                 # health/status/metrics/settings endpoints
│   │   ├── models/api_models.py  # Pydantic request/response models for the API layer
│   │   ├── middleware/            # rate limiting, request-ID injection
│   │   └── utils/                 # router-local helpers (field formatting, constants)
│   │
│   ├── services/                  # Business logic - one concern per file
│   │   ├── bugsigdb_analyzer/     # Core field-extraction package (see below)
│   │   ├── data_retrieval.py, standalone_pubmed_retriever.py   # PubMed/PMC fetching
│   │   ├── cache_manager.py       # SQLite analysis-result cache
│   │   ├── agent_orchestrator.py, web_scraper.py, image_processor.py,
│   │   │   converter_service.py, vector_store_service.py        # URL-analysis pipeline steps
│   │   ├── advanced_rag.py, chunk_reranking.py,
│   │   │   contextual_summarization.py                          # v2 RAG pipeline
│   │   └── bugsigdb_check.py      # is_in_bugsigdb() lookup
│   │
│   ├── services/bugsigdb_analyzer/   # Field-extraction core (split into a package - see
│   │   │                              # "Extending the extraction pipeline" in DEVELOPER_GUIDE.md)
│   │   ├── __init__.py            # Re-exports; preserves the public import surface
│   │   ├── singletons.py          # get_unified_qa/get_pubmed_retriever/get_cache_manager
│   │   ├── constants.py           # FIELD_KEYS, STATUS_COLUMNS, EXTRACTION_PROMPT
│   │   ├── parsing.py             # PMC XML section parsing, text truncation/budgeting
│   │   ├── field_extraction.py    # FieldDict builders, JSON/heuristic parsers, postprocessing
│   │   ├── simple_analysis.py     # analyze_paper_simple (v1)
│   │   └── rag_analysis.py        # analyze_paper_with_rag (v2), analyze_single_field
│   │
│   ├── models/                    # LLM provider abstractions + API-shape schemas
│   │   ├── llm_provider.py        # LiteLLM-based multi-provider abstraction
│   │   ├── unified_qa.py          # Common QA interface used by the analyzer
│   │   ├── gemini_qa.py           # Gemini-specific QA implementation (API-calling only)
│   │   ├── gemini_response_parsing.py   # Pure text-parsing helpers used by gemini_qa.py
│   │   ├── paperqa_agent.py       # Paper-QA integration
│   │   └── extraction_schemas.py  # Pydantic models mirroring the URL-analysis output shape
│   │
│   ├── normalization/             # Free-text -> controlled-vocabulary mapping
│   │   ├── host_species.py        # -> NCBITaxon
│   │   ├── body_site.py           # -> UBERON
│   │   ├── condition.py           # -> EFO
│   │   ├── ols.py                 # Shared EBI OLS4 API client (used by body_site/condition)
│   │   ├── sequencing_type.py      # -> BugSigDB's own controlled vocab
│   │   ├── sample_size.py         # Numeric/word-to-number parsing
│   │   └── types.py               # NormalizedTerm + shared lookup-matching helpers
│   │
│   ├── core/settings.py           # Pydantic-based structured settings (see SETTINGS.md)
│   └── utils/                     # Cross-cutting helpers: config.py (flat env-var reads),
│                                   # credential_masking.py, chunking.py, text_processing.py,
│                                   # url_safety.py, field_validator.py, performance_logger.py
│
├── scripts/
│   ├── cli.py                     # BioAnalyzerCLI - argument parsing + dispatch
│   ├── cli_rendering.py           # Output renderers (table/csv/json/xml/curator_desk_csv)
│   ├── main.py                    # Entry point for `python -m scripts.main` / installed CLI
│   ├── curator_daily_pipeline.py, feedback_aggregate.py   # Scheduled/batch ops scripts
│   ├── eval/                      # Offline evaluation: confusion-matrix + ontology benchmarks
│   ├── ops/                       # Log cleanup/dashboard/performance-monitor utilities
│   └── dev/                       # Local dev-only helper scripts
│
├── tests/                         # pytest suite - one test file per source module, generally
│                                   # mocking external calls (PubMed, LLM providers); see TESTING.md
│
├── curator_table/                 # Streamlit curator-review dashboard (`BioAnalyzer run table`)
├── curator_table_r/                # Separate git repo (R/Quarto) - the production curator desk;
│                                   # nested here for local development convenience only
│
├── docs/                          # All documentation (this file's folder) - see docs/README.md
├── config/requirements.txt        # The actual pinned dependency list (setup.py reads from here)
├── pyproject.toml, setup.py        # Packaging metadata
├── Dockerfile, docker-compose.yml,
│   docker-compose.prod.yml         # Container build/run definitions
├── install.sh, docker-cli.sh, docker-setup.sh   # The `BioAnalyzer` global CLI wrapper + setup
├── run_tests.sh                   # Runs pytest inside the prebuilt Docker image
├── conftest.py, tests/conftest.py  # Force `app` onto sys.path for both host and Docker test runs
├── main.py                        # Direct uvicorn entry point (`python main.py`)
├── cli.py                         # Backward-compat shim importing scripts.cli.main
└── CLAUDE.md, README.md, LICENSE  # Top-level project docs
```

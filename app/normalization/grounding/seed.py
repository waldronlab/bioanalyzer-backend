"""Populates a LocalOntologyBackend store.

Two independent data sources, deliberately not conflated:

1. `build_seed_store()` - loads BioAnalyzer's own already-verified static
   lookup dicts (SPECIES_LOOKUP/BODY_SITE_LOOKUP/CONDITION_LOOKUP - the same
   ~50 entries the 2026-07 audit hand-checked against live OLS) into a
   LocalOntologyBackend. Real, offline-buildable with no network access and
   no new data-fabrication risk, since it's the exact same (label, curie)
   pairs the live system already trusts at "auto" tier - just re-homed into
   queryable storage instead of Python source. Each seeded term gets one
   direct `is_a` edge to its ontology's declared root rather than a full
   multi-hop ontology graph - a deliberate simplification, not a complete
   ontology import; `LocalOntologyBackend.mark_complete()` is intentionally
   never called for seed-only data (see that method's docstring for why
   that distinction matters for correctness, not just bookkeeping).

2. `ensure_ontology()` - fetches and projects a full ontology from
   semantic-sql's public `.db.gz` dumps (the same source metacurator's
   `LocalDuckDBBackend.ensure()` uses) for real, complete coverage beyond
   the ~50-entry seed. **Verified against real data in this pass** for DOID
   (23MB compressed, 14,638 terms, 26,373 edges - see
   `docs/GROUNDING_ARCHITECTURE.md` §4 for the exact projection queries and
   row counts). EFO/MONDO/UBERON/NCBITaxon/HP were confirmed live and
   reachable at this same URL convention (sizes measured, HTTP 200
   confirmed) but were **not downloaded** - at the ~100-200KB/s throughput
   this environment measured, EFO alone (241MB) is ~30-40 minutes and
   NCBITaxon (2.1GB) is multiple hours; not attempted here, queued for a
   real deployment/sync window instead (see `scripts/ontology_sync.py`).
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import sqlite3
import tempfile
import urllib.request
from typing import Dict, List, Tuple
from urllib.error import URLError

from app.normalization.body_site import BODY_SITE_LOOKUP
from app.normalization.condition import CONDITION_LOOKUP
from app.normalization.grounding.local_backend import LocalOntologyBackend
from app.normalization.grounding.roots import ROOTS
from app.normalization.host_species import SPECIES_LOOKUP
from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)

# semantic-sql publishes one gzipped SQLite-projectable file per ontology
# under a public bucket, named `<ontology>.db.gz` - the same source
# metacurator's LocalDuckDBBackend.ensure() fetches from (SPEC 070,
# "Backends" section). Confirmed live in this pass via a direct HEAD request
# (HTTP 200, `Content-Type: application/gzip`) for every ontology slug in
# ROOTS/EXTENDED_ONTOLOGY_ROOTS.
SEMANTIC_SQL_BASE_URL = "https://s3.amazonaws.com/bbop-sqlite"

# prefix -> the ontology's static lookup dict, keyed by the same prefixes
# app.normalization.grounding.roots.ROOTS declares. Ontologies with no
# static dict (e.g. DOID, which no BioAnalyzer normalizer currently emits)
# are simply absent here - build_seed_store() skips them, by design; they
# only ever get real data via ensure_ontology().
_SEED_SOURCES: Dict[str, Dict[str, Tuple[str, str]]] = {
    "EFO": CONDITION_LOOKUP,  # CONDITION_LOOKUP mixes EFO/MONDO ids by prefix
    "MONDO": CONDITION_LOOKUP,
    "UBERON": BODY_SITE_LOOKUP,
    "NCBITaxon": SPECIES_LOOKUP,
}


def _prefix(curie: str) -> str:
    return curie.split(":", 1)[0] if ":" in curie else ""


def build_seed_store(backend: LocalOntologyBackend) -> int:
    """Insert every (label, curie) pair from the static lookup dicts into
    *backend*, plus a direct edge to each entry's ontology root. Idempotent
    - safe to call repeatedly, e.g. once at process startup. Returns the
    number of distinct terms inserted."""
    seen_pairs: set = set()
    for prefix, (ols_slug, root_id) in ROOTS.items():
        lookup = _SEED_SOURCES.get(prefix)
        if not lookup:
            continue
        for _key, (label, curie) in lookup.items():
            if not curie or _prefix(curie) != prefix or curie in seen_pairs:
                continue
            seen_pairs.add(curie)
            backend.upsert_term(
                ols_slug, curie, label, version="bioanalyzer-static-2026-07-12"
            )
            if curie != root_id:
                backend.insert_edge(ols_slug, curie, "is_a", root_id)
        # The root term itself must exist too, or reachable_from()'s
        # curie == root short-circuit is the only way it's ever "found".
        backend.upsert_term(
            ols_slug, root_id, root_id, version="bioanalyzer-static-2026-07-12"
        )
    backend.commit()
    return len(seen_pairs)


def ensure_ontology(
    ontology_slug: str, curie_prefix: str, backend: LocalOntologyBackend
) -> bool:
    """Download and project semantic-sql's `<ontology_slug>.db.gz` into
    *backend* for full-ontology coverage beyond the static seed, then mark
    it `complete` (see `LocalOntologyBackend.mark_complete()`). *curie_prefix*
    (e.g. "DOID") filters the projection to terms this ontology actually
    defines - semantic-sql dumps bundle in stub terms from every ontology
    the source OWL file imports (confirmed empirically: DOID's own dump
    contains ~6,000 non-DOID CHEBI edges pulled in via import), so without
    this filter "the doid store" would silently include partial, unrelated
    data from whatever DOID happens to reference. Returns False (and logs,
    never raises) on any network/format failure, so a caller can always
    fall back to the seed-only store rather than crash.
    """
    url = f"{SEMANTIC_SQL_BASE_URL}/{ontology_slug}.db.gz"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            gz_path = os.path.join(tmp, f"{ontology_slug}.db.gz")
            db_path = os.path.join(tmp, f"{ontology_slug}.db")
            urllib.request.urlretrieve(url, gz_path)  # noqa: S310 - fixed https URL
            with gzip.open(gz_path, "rb") as src, open(db_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            # Clear any prior copy of this ontology only after the fetch has
            # fully succeeded - a failed download must never touch existing
            # good data (see clear_ontology()'s docstring for the duplicate-
            # row bug this closes when re-syncing an already-synced
            # ontology).
            backend.clear_ontology(ontology_slug)
            version = _project_semantic_sql(
                db_path, ontology_slug, curie_prefix, backend
            )
        backend.mark_complete(ontology_slug, source=url, version=version)
        return True
    except (URLError, OSError, ValueError) as e:
        logger.warning(
            "ensure_ontology(%s) failed - falling back to seed-only local store: %s",
            ontology_slug,
            mask_exception_message(e),
        )
        return False


# oio:has{Exact,Broad,Narrow,Related}Synonym -> this backend's scope names.
_SYNONYM_VIEWS = {
    "has_exact_synonym_statement": "exact",
    "has_broad_synonym_statement": "broad",
    "has_narrow_synonym_statement": "narrow",
    "has_related_synonym_statement": "related",
}


def _project_semantic_sql(
    sqlite_db_path: str,
    ontology_slug: str,
    curie_prefix: str,
    backend: LocalOntologyBackend,
) -> str:
    """Project a downloaded semantic-sql SQLite file into *backend*'s
    terms/synonyms/edges tables, filtered to *curie_prefix*. Uses
    semantic-sql's own pre-built per-predicate views
    (`rdfs_label_statement`, `has_exact_synonym_statement`, etc., `edge`,
    `deprecated_node`) rather than pattern-matching the raw `statements`
    table by predicate string - confirmed these views exist with exactly
    this shape against a real downloaded file (DOID, 2026-08); see
    `docs/GROUNDING_ARCHITECTURE.md` §4 for the verification queries and
    row counts. Returns the ontology's own `owl:versionInfo` value, or "".
    """
    like_pattern = f"{curie_prefix}:%"
    src = sqlite3.connect(sqlite_db_path)
    try:
        deprecated = {
            row[0]
            for row in src.execute(
                "SELECT id FROM deprecated_node WHERE id LIKE ?", (like_pattern,)
            )
        }
        replaced_by: Dict[str, str] = {}
        for curie, replacement in src.execute(
            "SELECT subject, object FROM statements "
            "WHERE predicate = 'IAO:0100001' AND subject LIKE ?",
            (like_pattern,),
        ):
            replaced_by[curie] = replacement

        term_rows: List[Tuple[str, str, bool, str, str]] = [
            (curie, label, curie in deprecated, replaced_by.get(curie, ""), "")
            for curie, label in src.execute(
                "SELECT subject, value FROM rdfs_label_statement WHERE subject LIKE ?",
                (like_pattern,),
            )
        ]
        backend.bulk_upsert_terms(ontology_slug, term_rows)

        for view, scope in _SYNONYM_VIEWS.items():
            syn_rows = [
                (curie, synonym, scope)
                for curie, synonym in src.execute(
                    f"SELECT subject, value FROM {view} WHERE subject LIKE ?",
                    (like_pattern,),
                )
                if synonym
            ]
            if syn_rows:
                backend.bulk_insert_synonyms(ontology_slug, syn_rows)

        edge_rows = [
            (subject, predicate, obj)
            for subject, predicate, obj in src.execute(
                "SELECT subject, predicate, object FROM edge WHERE subject LIKE ?",
                (like_pattern,),
            )
        ]
        backend.bulk_insert_edges(ontology_slug, edge_rows)

        # oio:hasDbXref - cross-references to other databases/ontologies,
        # confirmed real via `has_dbxref_statement` against real downloaded
        # data (2026-08-09 pass). Used as a corroborating ranking signal
        # (backend.rank_candidates_explained()) when a candidate's xref
        # points into another ontology this store also holds.
        xref_rows = [
            (curie, xref)
            for curie, xref in src.execute(
                "SELECT subject, value FROM has_dbxref_statement WHERE subject LIKE ?",
                (like_pattern,),
            )
            if xref
        ]
        if xref_rows:
            backend.bulk_insert_xrefs(ontology_slug, xref_rows)

        backend.commit()

        version_rows = src.execute(
            "SELECT value FROM statements WHERE predicate = 'owl:versionInfo' LIMIT 1"
        ).fetchall()
        return version_rows[0][0] if version_rows else ""
    finally:
        src.close()

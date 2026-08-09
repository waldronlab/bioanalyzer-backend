"""Schema-declared branch root per ontology.

Keyed by the CURIE prefix found on `NormalizedTerm.ontology_id` (see
condition.py/body_site.py/host_species.py's lookup dicts for which prefixes
are in play). metacurator's spec calls this "the schema's declared root for
that field" (SPEC 060) - configured per-schema/per-deployment rather than
hardcoded. BioAnalyzer has exactly one deployment shape (5 fixed curation
fields), so a module-level dict is the right amount of configurability for
what actually varies today; if that ever needs to be per-request/per-tenant,
this is the one place to make it so.

Two dicts, deliberately not one, and this split is itself a correctness
rule, not organization:

`ROOTS` - the 4 ontologies BioAnalyzer's 3 curation fields
(host_species/body_site/condition) actually bind to today, plus DOID (see
below). Every root here has been round-tripped against a live source at
least once - EFO/MONDO/UBERON/NCBITaxon during the original 2026-07 audit
against live OLS, DOID against a real downloaded semantic-sql dump in this
pass (`DOID:4` / "disease", confirmed: 14,638 real terms, 26,373 edges,
`rdfs_label_statement` reports the label "disease" for it directly - see
`docs/GROUNDING_ARCHITECTURE.md`).

`EXTENDED_ONTOLOGY_ROOTS` - reserved for a real, verified, *meaningful*
single root that isn't yet promoted into `ROOTS`. Empty as of 2026-08-09:
CHEBI's root (`CHEBI:24431`, "chemical entity") was verified the same way
- the term exists, has no parent (a true root, not a guess), and a real
compound (`CHEBI:17234` "glucose") is confirmed reachable from it via 18
real ancestor hops (ChEBI is officially a 3-branch ontology - `chemical
entity`, `role`, `subatomic particle`, each independently rootless -
`chemical entity` is the branch that matters for grounding actual chemical
substances, the same kind of deliberate subtree choice `NCBITaxon:2759`
"Eukaryota" already makes for host species) - but promoted straight into
`ROOTS` rather than parked here, matching the precedent HP's promotion set
earlier the same day: `_ground_static_match()` (`tiering.py`) only ever
reads `ROOTS`, never this dict, so a verified-but-merely-"extended" root
is otherwise permanently inert for `ground()`/`tier_for()` even though
`rank_candidates_explained()`'s branch-validity signal (which does read
both dicts) would use it. Once a root clears the same verification bar
DOID/HP/CHEBI did, there is no remaining reason to leave it here instead
of `ROOTS` - no BioAnalyzer field emitting that ontology's CURIEs is what
makes the promotion inert in practice, not a reason to withhold it.

`NO_SINGLE_ROOT` - ontologies with real, complete, fully synced local data
(lookup/round-trip/obsolete-check all work normally) but **no meaningful
single root to branch-check against** - a structural fact about the real
downloaded data, not a shortcut. Verified per-ontology, 2026-08-09:

- **ENVO**: its real top-level terms (e.g. `ENVO:00010483` "environmental
  material", `ENVO:01000813` "astronomical body part") have zero parents
  *within the ENVO: namespace* but real parents in foreign upper
  ontologies this store doesn't independently hold data for (`BFO:0000040`
  "material entity", `RO:0002577` "system") - there is no single ENVO-
  internal root to check reachability against.
- **NCIT**: 116 distinct top-level NCIT concepts (`Organism`, `Gene`,
  `Drug, Food, Chemical or Biomedical Material`, ...) each parent directly
  to generic `owl:Thing` and nothing else - technically single-rooted, but
  at a point so generic ("is this concept an OWL class") that branch-
  checking against it would almost never actually reject anything,
  providing none of the real discriminative value DOID's/EFO's "disease"
  or NCBITaxon's "Eukaryota" roots provide (confirmed E. coli correctly
  fails NCBITaxon's branch check - `owl:Thing` would let it, and
  everything else, through).
- **MeSH**: real descriptor-level `rdfs:subClassOf` edges exist (verified:
  `MESH:D003920` "Diabetes Mellitus" -> `MESH:D004700` "Endocrine System
  Diseases" and `MESH:D009750` "Nutritional and Metabolic Diseases" -
  genuinely two independent parents, both themselves rootless) - MeSH's
  real hierarchy is a forest of ~16 independent top-level category trees
  (its own official design: Anatomy, Organisms, Diseases, Chemicals and
  Drugs, ...), not a single DAG.

Each of these is a real technical finding from tracing the actual
downloaded `edge` table to its ancestors, not an assumption - see
docs/GROUNDING_ARCHITECTURE.md's 2026-08-09 pass for the exact queries.
Registering any single one of their top-level categories as "the" root
would misrepresent the ontology's real structure and would either reject
valid terms from the other legitimate branches (false negatives) or -
worse, for NCIT's `owl:Thing` case - provide no real signal at all while
looking like it does. `scripts/ontology_sync.py` still syncs these (full
real data, `mark_complete()`'d) - they're just never in `ROOTS`, so
`tiering.py`'s branch-check step correctly stays unavailable (fails open)
for any term in these ontologies, the same fail-open behavior an
unmapped-prefix `ontology_id` already gets today.
"""

from __future__ import annotations

# prefix -> (semantic-sql/OLS ontology slug, root ontology_id)
ROOTS: dict[str, tuple[str, str]] = {
    "EFO": ("efo", "EFO:0000408"),  # "disease"
    "MONDO": ("mondo", "MONDO:0000001"),  # "disease or disorder"
    "UBERON": ("uberon", "UBERON:0001062"),  # "anatomical entity"
    "NCBITaxon": ("ncbitaxon", "NCBITaxon:2759"),  # "Eukaryota"
    "DOID": ("doid", "DOID:4"),  # "disease" - verified against real downloaded data
    "HP": ("hp", "HP:0000001"),  # "All" - verified 2026-08-09: real term exists,
    # not obsolete, and a real descendant (HP:0001250 "Seizure") is confirmed
    # reachable from it via LocalOntologyBackend.reachable_from() against the
    # actual synced HP data (19,944 terms). Promoted from EXTENDED_ONTOLOGY_ROOTS
    # now that it's round-tripped the same way DOID was - no BioAnalyzer field
    # emits an HP: ontology_id today, so this has no behavioral effect on
    # tiering.py's field-verification gate; it exists so any future caller of
    # LocalOntologyBackend.lookup()/reachable_from() against real HP data (or
    # the ranking signal in backend.py that reads this dict) gets a verified
    # root instead of none at all.
    "CHEBI": ("chebi", "CHEBI:24431"),  # "chemical entity" - verified 2026-08-09:
    # real term, no parent (true root), CHEBI:17234 "glucose" confirmed
    # reachable via 18 real ancestor hops against the actual synced CHEBI
    # data (205,304 terms). See module docstring for why the "chemical
    # entity" branch specifically, not ChEBI's other two independent roots
    # ("role", "subatomic particle").
}

# Real, verified, meaningful single roots not yet promoted into ROOTS -
# see module docstring. Empty as of 2026-08-09.
EXTENDED_ONTOLOGY_ROOTS: dict[str, tuple[str, str]] = {}

# Ontologies with real, fully synced local data but no meaningful single
# root to branch-check against - see module docstring for the per-ontology
# technical evidence. ols_slug -> curie_prefix (not (slug, root_id) - there
# is deliberately no root_id field here).
NO_SINGLE_ROOT: dict[str, str] = {
    "envo": "ENVO",
    "ncit": "NCIT",
    "mesh": "MESH",
}

def prefix_of(ontology_id: str) -> str:
    return ontology_id.split(":", 1)[0] if ":" in ontology_id else ""

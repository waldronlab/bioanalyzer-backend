# metacurator & MetaHarmonizer: what they do, how accurate they really are, and what to bring into BioAnalyzer

Date: 2026-07-16. Scope: both tools were built and their offline test suites run
locally (`metacurator-main/`, `MetaHarmonizer-main/`, pasted into this repo's
root); their source, specs, ADRs, and example scripts were read in full. This
is not a superficial README skim — every claim below is traced to specific
code or a specific documented/verified run, including a live run of
metacurator's real grounding mechanism against the real MONDO ontology
(59,054 terms, downloaded fresh from the same public semantic-sql source
metacurator uses in production — see "Live cross-check" below).

## Executive summary

Neither tool solves the problem BioAnalyzer is actually hardest at: reading
messy scientific-paper prose and figuring out *what the value is in the first
place*. Both tools' genuine sophistication is entirely in the step *after*
that — given an already-clean value (a spreadsheet cell, a curator's typed
string), map or ground it correctly to an ontology. metacurator's "near-100%"
reputation is real but narrower than it sounds: it's a verified 110/110 on
grounding *already-curated, clean* disease labels for one study, not
end-to-end accuracy on raw papers. MetaHarmonizer is a more mature, published
system for exactly that same downstream problem (ontology/schema mapping),
with real published-preprint findings that are directly useful here — most
importantly, their own finding that naive LLM-only matching is *inflated* by
benchmark contamination, which is the same lesson this repo's benchmark
already taught us the hard way (see `docs/ONTOLOGY_AUDIT.md`,
`docs/BUGSIGDB_ACCURACY_BENCHMARK.md`).

**Bottom line: don't merge or vendor either codebase. Port four specific
techniques into BioAnalyzer's existing `app/normalization/` layer** — detailed
below, roughly ordered by effort-to-value ratio.

## What each tool actually is

### metacurator (Sean Davis, `seandavi/metacurator`)

A **spec-first framework**, explicitly labeled `alpha`, for turning a
published paper + its supplementary files into curated, ontology-grounded,
per-sample metadata. Its core architectural idea (ADR-0004, "determinism
gradient") is the one worth internalizing regardless of what code gets
copied:

> Mechanical work (lookups, table loading, ontology grounding, diffing) must
> be deterministic, tested code — an LLM here only adds cost and
> hallucination risk. Judgment work (which table is the patient table? which
> ontology candidate is right?) needs a model, but constrained to emit typed
> objects that deterministic code validates.

Concretely, `judge.py` is the *only* module allowed to call an LLM, and it
makes exactly three kinds of calls, none of which let the model freely emit a
final value:
- `classify_tables` — picks an *index* into a list of already-loaded tables, not data.
- `propose_mapping` — returns a *column → schema field* mapping description, validated against the real schema; an unknown target field raises loudly.
- `disambiguate` — picks *one CURIE from a pre-vetted candidate list* the deterministic grounding step already produced from a real ontology; returning anything outside that set raises `JudgeContractError`.

The grounding step itself (`ground.py`, SPEC 070) is the piece with the most
direct lesson for BioAnalyzer. It enforces a four-step discipline before a
CURIE is trusted:

1. **Lookup** — search the local ontology store.
2. **Round-trip** — re-fetch the candidate CURIE from the store and confirm it genuinely exists in the claimed ontology (not just that search returned it).
3. **Branch check** — confirm the term is reachable from a schema-declared root (e.g. a "condition" must actually be under the disease branch, not some unrelated branch).
4. **Obsolete check** — reject deprecated terms outright, surfacing `replaced_by` instead of silently keeping a dead ID.

Ambiguity is never silently resolved: multiple equally-good candidates all
get pushed to a `review` tier rather than one being guessed.

**I built and ran it.** `uv sync` + codegen (`gen-pydantic`/`gen-json-schema`
from the LinkML schema) succeeded, and the offline test suite is real:
**110 passed, 3 skipped** (the skipped ones need live network access). This
confirms the deterministic spine is genuinely implemented to spec, not
vaporware.

### The "100% accuracy" claim, traced to its source

`examples/reproduce_vogtmann.py` is the concrete result behind the
reputation. Quoting its own header comment:

> metacurator's NCIT grounding matched the curator's `disease_ontology_term_id`
> on **110/110 rows** ("Colorectal Carcinoma" → NCIT:C2955, ... "Healthy" →
> NCIT:C115935)

This is real and I don't doubt it. But read what's actually being tested:

- It's **one study** (Vogtmann et al. 2016, a colorectal-cancer microbiome
  paper), with exactly **two distinct disease values** ("Colorectal
  Carcinoma" and "Healthy") repeated across 110 sample rows. It's not 110
  different diseases correctly identified — it's 2 diseases, correctly
  grounded, applied consistently.
- The "source table" fed into metacurator is the **already hand-curated**
  `curatedMetagenomicDataCuration` TSV — i.e. a human already typed the clean
  string "Colorectal Carcinoma" into a spreadsheet cell. The script's own
  comment says this explicitly: *"the value-level diff is expected to be
  exact; the substantive, independent check is the grounding."*
- There's a companion script, `examples/grounding_audit.py`, built for a
  *broader* breadth check (every distinct curated disease label across the
  whole corpus, categorized AGREE/DISAGREE/REVIEW/NO-MATCH/CROSS-ONTO), which
  is exactly the kind of test that would validate accuracy across many
  diseases — but it requires the external `curatedMetagenomicDataCuration`
  repo as a sibling directory, which isn't present in this environment, so I
  could not run it. No broader number is published in this repo.

**What this means:** metacurator's grounding step, given a clean value, is
excellent — by construction it cannot hallucinate an ID, and its verified
demo shows it lands on the right one. But it has not been shown to solve —
and doesn't attempt to solve — the problem BioAnalyzer actually has:
extracting the *right specific value* from unstructured paper prose in the
first place. That's a different, harder problem, and it's the one dragging
down BioAnalyzer's condition field (33.7%) far more than grounding is
(condition ontology ID: 61.3%, already the stronger half).

### MetaHarmonizer (`shbrief/MetaHarmonizer`)

A more mature, published (preprint), general-purpose **ontology and schema
mapping engine** — again, downstream of extraction, not an extraction tool
itself. Its `OntoMapEngine` runs a genuinely well-designed cascade
(`ontology_mapping_engine.py::run()`, read in full):

1. **Stage 1 — exact match** against the ontology corpus (free, perfect when it hits).
2. **Query normalization** before anything else: underscore→space, **British→American spelling** (a small hardcoded list — `leukaemia→leukemia`, `tumour→tumor`, `diarrhoea→diarrhea`, etc.), and corpus-aware plural stripping.
3. **Stage 2 — embedding similarity** using domain-tuned biomedical models (SapBERT / PubMedBERT), not a generic sentence embedder.
4. **Stage 2.5 — synonym verification**, boosting low-confidence Stage-2 matches using each candidate's real ontology synonyms, not just its primary label.
5. **Stage 3 (optional) — RAG** re-matching with retrieved context.
6. **Stage 4 (optional, last resort) — LLM** query rewriting, applied only to what's still low-confidence after everything else.

The LLM is never the primary matcher. It's a narrow, late-stage tool applied
to the smallest, hardest remaining subset — the same philosophy as
metacurator's `judge.py`, arrived at independently.

**On accuracy**: I couldn't fetch the preprint directly (biorxiv returned
403), but a search of it turned up the paper's actual headline finding, which
matters more than a single number: **OntologyMapper outperforms LLM-only
inference, and under contamination-controlled evaluation, the symbolic
pipeline matches LLM-only performance without the API cost** — because raw
LLM performance on public ontology benchmarks is partly **inflated by
training-data memorization**, not genuine matching capability. No hardcoded
accuracy percentage is checked into this repo copy (the evaluation datasets
are described in the README as encrypted specifically to prevent this kind
of contamination, and require authorization this environment doesn't have).
So I can't hand you a number, but the finding itself is the more important
takeaway — it's independent confirmation of exactly what this repo's own
benchmark just demonstrated: a broken/naive LLM path silently produces
low-quality results (see the earlier condition-extraction and model-prefix
bugs), and a disciplined, mostly-deterministic pipeline is what actually gets
you reliability.

### Live cross-check: metacurator's real grounding vs. BioAnalyzer's fixed condition.py

Rather than take the Vogtmann example's word for it, I downloaded the real
MONDO ontology (59,054 terms, same public semantic-sql source metacurator
uses in production) and ran metacurator's actual `ground()` function against
the same handful of terms `condition.py` was fixed for earlier this session
— an independent, live re-verification, not a second read of the same code:

| Term | metacurator (live MONDO) | BioAnalyzer's `condition.py` (fixed) | Agree? |
| --- | --- | --- | --- |
| COVID-19 | `MONDO:0100096` (auto) | `MONDO:0100096` | ✓ exact match |
| colorectal cancer | `MONDO:0005575` (auto) | `MONDO:0005575` | ✓ exact match |
| Parkinson disease | `MONDO:0005180` (auto) | `MONDO:0005180` | ✓ exact match |
| irritable bowel syndrome | `MONDO:0005052` (auto) | *(none — see below)* | gap found |
| antibiotic exposure | *(no grounding)* | *(none, by design)* | ✓ confirms the fix |
| healthy | *(no grounding)* | *(none, by design)* | ✓ confirms the fix |

Two things this confirms, independently of anything argued earlier:

1. **The earlier condition.py fix was correct** — metacurator's grounding
   against real, live MONDO data agrees exactly on every ID I hand-verified
   against OLS, and — more interestingly — it *also* found nothing for
   "antibiotic exposure" and "healthy", the two terms I deliberately left
   with no ontology ID rather than fabricate one. A completely independent
   tool, querying a different local copy of the same public ontology data,
   reached the identical conclusion that these aren't real MONDO concepts.
2. **A real gap, found live**: querying the bare term "irritable bowel
   syndrome" resolves cleanly, but during the earlier benchmark BioAnalyzer's
   LLM extracted the fuller phrase "diarrhea-predominant irritable bowel
   syndrome" for PMID 22339879, and that got **no ontology ID** — `condition.py`'s
   live OLS/MONDO fallback doesn't handle the longer, modifier-heavy phrasing
   as well as it handles the bare term. Worth a follow-up: either strip
   qualifying modifiers before the live-search query, or fall back to a
   second, shorter-query attempt when the full phrase returns nothing.

## What's directly portable into BioAnalyzer

Ordered by effort-to-value ratio. None of these require adopting either
framework wholesale — BioAnalyzer's `app/normalization/` layer already has
the right shape (static lookup → live fallback → cache) to extend.

### 1. British/American spelling normalization (near-zero effort)

This is a direct, immediate fix for a real gap the benchmark found —
BioAnalyzer predicted "faecal" for a paper's body site and scored a
disagreement against ground truth "feces" purely because the British
spelling isn't in `body_site.py`'s lookup dict. MetaHarmonizer's
`_BRITISH_TO_AMERICAN` list (`ontology_mapping_engine.py`) is a ready-made,
small regex list solving exactly this. Add the same kind of normalization
pass before matching in `app/normalization/body_site.py` and `condition.py`.

### 2. Round-trip + branch + obsolete verification on grounding (medium effort, high value)

metacurator's `ground.py` discipline would have caught essentially every bug
found and manually fixed earlier this session (26 of 27 wrong/obsolete EFO
IDs in `condition.py`, the wrong UBERON IDs for rectum/vagina) *automatically*,
without a human having to hand-verify each ID against the live OLS API. The
adoptable pattern, applied to `app/normalization/ols.py::ols_search()` and
the static lookup dicts:

- After a static-dict or live-search hit, do a second confirmation lookup
  against the same ontology to verify the CURIE round-trips (OLS's
  `/api/terms?iri=...` endpoint, which is what I used manually to find the
  bugs, is exactly this check).
- Reject obsolete terms outright rather than trusting a hardcoded value that
  might have drifted since it was written.
- Optionally: a small CI/test-time script that round-trips every static
  dict entry against OLS periodically, so a future obsolete-term drift gets
  caught automatically instead of waiting for another manual audit like this
  session's.

This is the single highest-value idea to borrow — it turns "an engineer
manually re-verified 44 IDs by hand" into "the system verifies itself."

### 3. Never let the LLM freely emit the final value for ontology-mapped fields (higher effort, addresses the real weak point)

This is the structural idea behind both tools' accuracy, and it's the one
most directly aimed at BioAnalyzer's actual weakest number (condition label:
33.7%). Right now, BioAnalyzer's LLM freely generates `condition_raw` as
open text, which then gets normalized — so "cancer" vs "colorectal cancer"
is entirely down to how the LLM happened to phrase its free-text output.
Both metacurator (`disambiguate`, choosing only from real grounded
candidates) and MetaHarmonizer (deterministic stages first, LLM only
rewriting what's left) avoid ever asking a model to freely generate the
final answer.

Applied to BioAnalyzer, this would look like: generate a *candidate set* of
plausible conditions deterministically (dictionary/keyword hits + a live
ontology search over n-grams from the abstract), then ask the LLM only to
**pick among those real, already-grounded candidates** — never to write the
condition name from scratch. This is a genuinely bigger change than the
other three items and would need its own scoping pass; flagging it here as
the direction, not proposing to build it now.

### 4. Synonym-boosted confidence, not just primary-label matching (medium effort)

BioAnalyzer's static dicts (`CONDITION_LOOKUP`, `BODY_SITE_LOOKUP`) match on
a hand-picked keyword list per concept. MetaHarmonizer's synonym-verification
stage instead checks a candidate's *real* ontology synonyms (not just what
someone thought to hardcode). Since `app/normalization/ontology_cache.py`
already persists resolved terms, a natural extension is caching each term's
synonym list alongside its label/CURIE the first time it's grounded, so
future free-text matches can check against real synonyms instead of only the
canonical label.

## What's explicitly not worth adopting

- **metacurator's table classification/column mapping** (`classify_tables`,
  `propose_mapping`) — this solves a problem BioAnalyzer doesn't have: mining
  structured supplementary spreadsheets attached to a paper. BioAnalyzer only
  reads title/abstract/full-text prose today. Could become relevant if
  supplement-table mining is ever added as a new capability, but that's new
  scope, not an accuracy fix.
- **Vendoring either framework wholesale** — metacurator needs LinkML
  codegen + DuckDB + a schema-declared branch root per field (real
  infrastructure investment for a framework still in alpha with an
  "illustrative" schema); MetaHarmonizer needs FAISS, sentence-transformer
  model downloads, and its own KnowledgeDb/corpus-building machinery. Both
  are heavier than what BioAnalyzer's actual problem currently justifies.
  The techniques generalize; the frameworks themselves don't need to.
- **MetaHarmonizer's numeric-field classification** (`numeric_match_utils.py`,
  dose/age/time detection from column headers) — this is a *schema mapping*
  tool for structured column headers, not free-text sample-size extraction
  from prose. Doesn't transfer to BioAnalyzer's `sample_size.py` problem.

## Correcting the framing for Levi

Worth relaying back: metacurator's near-100% number is real, verified, and a
genuinely good demonstration of its grounding step — but it's grounding
*already-clean, human-curated* values for one study's two disease labels, not
end-to-end accuracy on reading raw papers across many conditions. It isn't
apples-to-apples with what BioAnalyzer's benchmark measures. The useful
takeaway isn't "adopt metacurator and get to 100%" — it's "adopt
metacurator's discipline for the half of the pipeline (grounding) it's
genuinely excellent at, and keep investing in extraction (which is
BioAnalyzer's actual hard problem and isn't solved by either tool)."

## Suggested next step

Item 1 (spelling normalization) and item 2 (round-trip/obsolete verification)
are both small enough to implement and benchmark in a single follow-up pass —
happy to do that next and re-run `scripts/eval/bugsigdb_ground_truth_benchmark.py`
to measure the real effect, the same way the condition-prompt fix was
validated earlier.

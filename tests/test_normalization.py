import time

import pytest
import requests

from app.normalization import body_site as body_site_module
from app.normalization import condition as condition_module
from app.normalization import host_species as host_species_module
from app.normalization import ols as ols_module
from app.normalization import sample_size as sample_size_module
from app.normalization.body_site import normalize_body_site
from app.normalization.condition import normalize_condition, _extract_clean_disease_name
from app.normalization.host_species import normalize_host_species
from app.normalization.ols import format_ontology_id, ols_search
from app.normalization.sample_size import normalize_sample_size, _simple_word_to_num
from app.normalization.sequencing_type import normalize_sequencing_type


@pytest.fixture(autouse=True)
def _no_ontology_cache(monkeypatch):
    """These tests exercise the live-lookup fallback paths directly, but
    host_species.py/ols.py persist resolved terms to a real on-disk SQLite
    cache (app.normalization.ontology_cache). Different tests below reuse
    the same example terms (e.g. "domestic cat") across host_species and
    OLS lookups, so without this, a cache entry written by an earlier test
    makes a later test's mocked HTTP response never get reached."""
    monkeypatch.setattr(host_species_module, "get_cached_term", lambda *a: None)
    monkeypatch.setattr(host_species_module, "store_cached_term", lambda *a: None)
    monkeypatch.setattr(ols_module, "get_cached_term", lambda *a: None)
    monkeypatch.setattr(ols_module, "store_cached_term", lambda *a: None)


class _DummyResponse:
    """Minimal stand-in for requests.Response used by the fakes below."""

    def __init__(self, json_data=None, status_code=200, raise_json_error=False):
        self._json_data = json_data
        self.status_code = status_code
        self._raise_json_error = raise_json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._raise_json_error:
            raise ValueError("malformed JSON")
        return self._json_data


def test_format_ontology_id():
    assert format_ontology_id("EFO_0002508", "EFO") == "EFO:0002508"
    assert format_ontology_id("UBERON_0001988", "UBERON") == "UBERON:0001988"
    assert format_ontology_id("EFO:0002508", "EFO") == "EFO:0002508"


def test_host_species_normalization_variants():
    t = normalize_host_species("humans")
    assert t.label == "Homo sapiens"
    assert t.ontology_id == "NCBITaxon:9606"
    assert t.status == "PRESENT"
    assert t.mapping_confidence == 1.0

    t = normalize_host_species("mice model")
    assert t.label == "Mus musculus"
    assert t.ontology_id == "NCBITaxon:10090"

    t = normalize_host_species("rats")
    assert t.label == "Rattus norvegicus"
    assert t.ontology_id == "NCBITaxon:10116"

    t = normalize_host_species("dogs")
    assert t.label == "Canis lupus familiaris"
    assert t.ontology_id == "NCBITaxon:9615"

    t = normalize_host_species("")
    assert t.status == "ABSENT"


def test_host_species_animal_wins_over_life_stage_descriptor():
    """Regression test: "adult"/"infant"/"neonate" are life-stage words, not
    species cues - animal studies use them too ("adult mice", "infant rats",
    "neonate pigs"). The longest-match lookup must not let these generic,
    coincidentally-longer words outrank a short but explicit animal noun."""
    t = normalize_host_species("adult mice were studied")
    assert t.label == "Mus musculus"
    assert t.ontology_id == "NCBITaxon:10090"

    t = normalize_host_species("infant rats received treatment")
    assert t.label == "Rattus norvegicus"

    t = normalize_host_species("neonate pigs were sampled")
    assert t.label == "Sus scrofa"

    # Sanity check: pure-human phrasing with a genuine species cue still works.
    t = normalize_host_species("adult patients were recruited")
    assert t.label == "Homo sapiens"
    assert t.ontology_id == "NCBITaxon:9606"

    t = normalize_host_species("mice and rats")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.ontology_id != ""


def test_body_site_normalization_variants():
    t = normalize_body_site("stool samples")
    assert t.label == "feces"
    assert t.ontology_id == "UBERON:0001988"
    assert t.status == "PRESENT"

    t = normalize_body_site("gut microbiome")
    assert t.label == "feces"
    assert t.ontology_id == "UBERON:0001988"

    t = normalize_body_site("salivary swab")
    assert t.label == "saliva"
    assert t.ontology_id == "UBERON:0001836"

    t = normalize_body_site("nasal cavity swab")
    assert t.label == "nasal cavity"

    t = normalize_body_site("blood plasma")
    assert t.label == "blood"
    assert t.ontology_id == "UBERON:0000178"

    t = normalize_body_site("")
    assert t.status == "ABSENT"


def test_condition_normalization_variants():
    t = normalize_condition("Parkinson's disease patients")
    assert t.label == "Parkinson disease"
    assert t.ontology_id == "MONDO:0005180"
    assert t.status == "PRESENT"

    t = normalize_condition("type 2 diabetes cohort")
    assert t.label == "type 2 diabetes mellitus"
    assert t.ontology_id == "MONDO:0005148"

    t = normalize_condition("obese adults")
    assert t.label == "obesity disorder"
    assert t.ontology_id == "MONDO:0011122"

    t = normalize_condition("healthy controls")
    assert t.label == "healthy"
    assert t.status == "PRESENT"
    # "healthy" isn't a disease - no fabricated ontology ID (see
    # condition.py's CONDITION_LOOKUP docstring).
    assert t.ontology_id == ""

    t = normalize_condition("COVID-19 cases")
    assert t.label == "COVID-19"
    assert t.ontology_id == "MONDO:0100096"

    t = normalize_condition("")
    assert t.status == "ABSENT"


def test_condition_disease_wins_over_comparator_arm_wording():
    """Regression test: "control(s)" describes the comparator arm of a
    case-control study, not a diagnosis - and it's longer than several real
    disease abbreviations (IBD, HIV, ASD, T2D). The disease actually being
    studied must win even when a "vs healthy/matched controls" phrase is
    also present in the same text."""
    t = normalize_condition("IBD patients vs healthy controls")
    assert t.label == "inflammatory bowel disease"

    t = normalize_condition("HIV patients compared to controls")
    assert t.label == "HIV infectious disease"

    t = normalize_condition("ASD children vs typically developing controls")
    assert t.label == "autism spectrum disorder"

    t = normalize_condition("patients with T2D and matched controls")
    assert t.label == "type 2 diabetes mellitus"

    # No disease mentioned at all - "healthy" must still be reachable.
    t = normalize_condition("healthy volunteers")
    assert t.label == "healthy"


def test_sequencing_type_normalization_variants():
    t = normalize_sequencing_type("16S rRNA gene sequencing")
    assert t.label == "16S"
    assert t.status == "PRESENT"
    assert t.ontology_id == ""

    t = normalize_sequencing_type("whole metagenome shotgun sequencing")
    assert t.label == "shotgun"

    t = normalize_sequencing_type("shotgun metagenomics study")
    assert t.label == "metagenomics"
    assert t.status == "PRESENT"

    t = normalize_sequencing_type("ITS1 sequencing")
    assert t.label == "ITS"

    t = normalize_sequencing_type("RNA-seq metatranscriptomics")
    assert t.label == "RNA-seq"

    t = normalize_sequencing_type("")
    assert t.status == "ABSENT"

    # Unmatched text falls back to the "other" vocab value (status PRESENT,
    # not PARTIALLY_PRESENT — it was found, just not classifiable), and the
    # original wording is preserved on .raw for the "Sequencing Type Raw"
    # side column.
    t = normalize_sequencing_type("new custom chemistry")
    assert t.label == "other"
    assert t.status == "PRESENT"
    assert t.raw == "new custom chemistry"

    # A matched phrase still preserves .raw, but callers should treat the
    # column as unnecessary when raw == normalized value.
    t = normalize_sequencing_type("16S rRNA gene sequencing")
    assert t.label == "16S"
    assert t.raw == "16S rRNA gene sequencing"


def test_sample_size_normalization_variants():
    t = normalize_sample_size(98)
    assert t.label == "98"
    assert t.status == "PRESENT"

    t = normalize_sample_size("1,200 participants")
    assert t.label == "1200"

    t = normalize_sample_size("ninety eight")
    assert t.label == "98"

    t = normalize_sample_size("about 65 volunteers")
    assert t.label == "65"

    t = normalize_sample_size(None)
    assert t.status == "ABSENT"

    t = normalize_sample_size("unknown sample count")
    assert t.status == "PARTIALLY_PRESENT"


def test_sample_size_ambiguous_multi_number_resolution():
    # Rule (see _resolve_ambiguous_count docstring): the first number
    # immediately followed by a sample-related noun wins, in reading order.
    t = normalize_sample_size("98 cases and 45 controls")
    assert t.label == "98"
    assert t.status == "PRESENT"

    # An explicit "total of N" overrides the per-cohort numbers.
    t = normalize_sample_size(
        "98 cases and 45 controls were included, for a total of 143 participants"
    )
    assert t.label == "143"

    # A leading year must not be mistaken for the sample size.
    t = normalize_sample_size("In 2019, 65 volunteers were enrolled")
    assert t.label == "65"

    # A percentage mentioned alongside the real count must not be picked up.
    t = normalize_sample_size("A total of 120 participants (60% female) were recruited")
    assert t.label == "120"

    # No anchored noun and no "total of" — falls back to the first number,
    # but a bare year-shaped number is excluded as a likely false positive.
    t = normalize_sample_size("Collected in 2020")
    assert t.status == "PARTIALLY_PRESENT"


# ---------------------------------------------------------------------------
# host_species.py: NCBI Taxonomy API fallback (only reached when the local
# SPECIES_LOOKUP dict misses). Untested before this milestone, and exactly
# the code path whose exception handling was narrowed from a bare
# `except Exception` to (RequestException, ValueError, KeyError).
# ---------------------------------------------------------------------------


def test_host_species_ncbi_fallback_success(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def fake_get(url, params=None, timeout=None):
        if url == host_species_module.NCBI_TAX_SEARCH_URL:
            return _DummyResponse({"esearchresult": {"idlist": ["9685"]}})
        if url == host_species_module.NCBI_TAX_SUMMARY_URL:
            return _DummyResponse(
                {"result": {"9685": {"scientificname": "Felis catus", "taxid": "9685"}}}
            )
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(requests, "get", fake_get)
    t = normalize_host_species("domestic cat")
    assert t.label == "Felis catus"
    assert t.ontology_id == "NCBITaxon:9685"
    assert t.status == "PRESENT"
    assert t.mapping_confidence == 0.9


def test_host_species_ncbi_fallback_no_results(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)

    def fake_get(url, params=None, timeout=None):
        return _DummyResponse({"esearchresult": {"idlist": []}})

    monkeypatch.setattr(requests, "get", fake_get)
    t = normalize_host_species("some unrecognized organism")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.ontology_id == ""
    assert t.mapping_confidence == 0.5


@pytest.mark.parametrize(
    "fake_get",
    [
        pytest.param(
            lambda url, params=None, timeout=None: (_ for _ in ()).throw(
                requests.exceptions.ConnectionError("network down")
            ),
            id="connection-error",
        ),
        pytest.param(
            lambda url, params=None, timeout=None: _DummyResponse(
                raise_json_error=True
            ),
            id="malformed-json",
        ),
        pytest.param(
            lambda url, params=None, timeout=None: (
                _DummyResponse({"esearchresult": {"idlist": ["9685"]}})
                if url == host_species_module.NCBI_TAX_SEARCH_URL
                else _DummyResponse({"result": {}})
            ),  # missing the id key -> KeyError
            id="missing-result-key",
        ),
    ],
)
def test_host_species_ncbi_fallback_handles_narrowed_exceptions(monkeypatch, fake_get):
    """The exception narrowing in host_species.py (RequestException, ValueError,
    KeyError) must still gracefully fall back rather than raise."""
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(requests, "get", fake_get)
    t = normalize_host_species("some unrecognized organism")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.ontology_id == ""
    assert t.mapping_confidence == 0.5


# ---------------------------------------------------------------------------
# ols.py: ols_search() (shared fallback used by condition.py and body_site.py
# when their local lookup dicts miss). Also untested before this milestone,
# and also where exception handling was narrowed to
# (RequestException, ValueError).
# ---------------------------------------------------------------------------


def test_ols_search_success(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert url == ols_module.OLS_SEARCH_URL
        return _DummyResponse(
            {
                "response": {
                    "docs": [{"label": "felis catus", "obo_id": "NCBITaxon_9685"}]
                }
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = ols_search("domestic cat", "ncbitaxon", "NCBITaxon")
    assert result == ("felis catus", "NCBITaxon:9685", 0.9)


def test_ols_search_no_docs(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _DummyResponse({"response": {"docs": []}})
    )
    assert ols_search("nonexistent term", "efo", "EFO") is None


def test_ols_search_handles_request_exception(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)
    assert ols_search("some term", "efo", "EFO") is None


def test_ols_search_handles_malformed_json(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _DummyResponse(raise_json_error=True)
    )
    assert ols_search("some term", "efo", "EFO") is None


# ---------------------------------------------------------------------------
# ols.py: fetch_term() / is_in_branch() - the round-trip, obsolete-detection,
# and branch-check steps of the four-step grounding discipline consumed by
# app.normalization.grounding. See that module's docstring for how these
# combine to gate the "auto" mapping tier.
# ---------------------------------------------------------------------------


def test_obo_iri_builds_purl_from_curie():
    assert (
        ols_module._obo_iri("EFO:0000400")
        == "http://purl.obolibrary.org/obo/EFO_0000400"
    )
    assert ols_module._obo_iri("NCBITaxon:9606") == (
        "http://purl.obolibrary.org/obo/NCBITaxon_9606"
    )


def test_obo_iri_returns_none_for_malformed_id():
    assert ols_module._obo_iri("not-a-curie") is None
    assert ols_module._obo_iri("") is None


def test_fetch_term_round_trip_success(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert url == ols_module.OLS_TERMS_URL
        assert params == {"iri": "http://purl.obolibrary.org/obo/MONDO_0005180"}
        return _DummyResponse(
            {
                "_embedded": {
                    "terms": [
                        {
                            "label": "Parkinson disease",
                            "obo_id": "MONDO:0005180",
                            "is_obsolete": False,
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)
    result = ols_module.fetch_term("MONDO:0005180")
    assert result.exists is True
    assert result.label == "Parkinson disease"
    assert result.is_obsolete is False
    assert result.replaced_by == ""


def test_fetch_term_reports_missing_term(monkeypatch):
    """The strongest possible signal of a fabricated/deleted static
    entry - the IRI resolves to nothing at all."""
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _DummyResponse({"_embedded": {"terms": []}})
    )
    result = ols_module.fetch_term("EFO:0003601")
    assert result.exists is False


def test_fetch_term_reports_obsolete_with_replacement(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _DummyResponse(
            {
                "_embedded": {
                    "terms": [
                        {
                            "label": "obsolete_Parkinson's disease",
                            "obo_id": "EFO:0002508",
                            "is_obsolete": True,
                            "term_replaced_by": "MONDO_0005180",
                        }
                    ]
                }
            }
        ),
    )
    result = ols_module.fetch_term("EFO:0002508")
    assert result.exists is True
    assert result.is_obsolete is True
    assert result.replaced_by == "MONDO:0005180"


def test_fetch_term_handles_request_exception(monkeypatch):
    def fake_get(*a, **k):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)
    assert ols_module.fetch_term("MONDO:0005180") is None


def test_fetch_term_returns_none_for_malformed_id():
    assert ols_module.fetch_term("not-a-curie") is None


def test_is_in_branch_true_when_root_in_ancestors(monkeypatch):
    def fake_get(url, timeout=None):
        return _DummyResponse(
            {"_embedded": {"terms": [{"label": "disease", "obo_id": "MONDO:0000001"}]}}
        )

    monkeypatch.setattr(requests, "get", fake_get)
    assert ols_module.is_in_branch("MONDO:0005180", "mondo", "MONDO:0000001") is True


def test_is_in_branch_false_when_root_missing(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _DummyResponse(
            {"_embedded": {"terms": [{"label": "somite", "obo_id": "UBERON:0002329"}]}}
        ),
    )
    assert ols_module.is_in_branch("EFO:0003601", "efo", "EFO:0000408") is False


def test_is_in_branch_true_when_term_is_the_root():
    # Short-circuits before any network call.
    assert ols_module.is_in_branch("MONDO:0000001", "mondo", "MONDO:0000001") is True


def test_is_in_branch_returns_none_on_request_exception(monkeypatch):
    def fake_get(*a, **k):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr(requests, "get", fake_get)
    assert ols_module.is_in_branch("MONDO:0005180", "mondo", "MONDO:0000001") is None


def test_is_in_branch_returns_false_on_404(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _DummyResponse(status_code=404)
    )
    assert ols_module.is_in_branch("MONDO:0005180", "mondo", "MONDO:0000001") is False


# ---------------------------------------------------------------------------
# body_site.py: multiple-keyword match + OLS fallback (previously untested)
# ---------------------------------------------------------------------------


def test_body_site_multiple_matches_is_partially_present():
    t = normalize_body_site("fecal and salivary samples were both collected")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.mapping_confidence == 0.9
    # first match in dict iteration order wins - just confirm it's one of
    # the two genuinely-matched pairs, not a third unrelated one.
    assert t.label in ("feces", "saliva")
    # the runner-up match is surfaced as a candidate for curator review
    assert len(t.candidates) >= 1
    assert t.label not in (c[0] for c in t.candidates)


def test_condition_two_distinct_conditions_surfaces_candidate():
    t = normalize_condition("comorbid obesity and type 2 diabetes cohort")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.label in ("obesity disorder", "type 2 diabetes mellitus")
    assert len(t.candidates) >= 1
    assert t.label not in (c[0] for c in t.candidates)


def test_condition_overlapping_keys_for_same_disease_stay_unambiguous():
    # "diabetes" is a substring of "type 2 diabetes" - this is one mention
    # at two specificities, not two distinct conditions, so it must not be
    # flagged as ambiguous (this was a real regression risk when adding
    # candidate surfacing).
    t = normalize_condition("type 2 diabetes cohort")
    assert t.status == "PRESENT"
    assert t.label == "type 2 diabetes mellitus"
    assert t.candidates == ()


def test_host_species_multiple_matches_surfaces_candidates():
    t = normalize_host_species("mice and rats were studied")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.label in ("Mus musculus", "Rattus norvegicus")
    assert len(t.candidates) >= 1
    assert t.label not in (c[0] for c in t.candidates)


def test_body_site_ols_fallback_success(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert url == ols_module.OLS_SEARCH_URL
        return _DummyResponse(
            {"response": {"docs": [{"label": "duodenum", "obo_id": "UBERON_0002114"}]}}
        )

    monkeypatch.setattr(requests, "get", fake_get)
    t = normalize_body_site("duodenal biopsy")
    assert t.label == "duodenum"
    assert t.ontology_id == "UBERON:0002114"
    assert t.status == "PRESENT"
    assert t.mapping_confidence == 0.9


def test_body_site_ols_fallback_no_hit_returns_partially_present(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _DummyResponse({"response": {"docs": []}})
    )
    t = normalize_body_site("some unmapped anatomical site")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.ontology_id == ""
    assert t.mapping_confidence == 0.5
    assert t.label == "some unmapped anatomical site"


# ---------------------------------------------------------------------------
# condition.py: _extract_clean_disease_name + OLS fallback (previously
# untested)
# ---------------------------------------------------------------------------


def test_extract_clean_disease_name_strips_known_phrases():
    assert (
        _extract_clean_disease_name("Patients with a rare metabolic disorder")
        == "a rare metabolic disorder"
    )
    assert (
        _extract_clean_disease_name("Subjects with chronic kidney disease")
        == "chronic kidney disease"
    )


def test_extract_clean_disease_name_passes_through_when_no_phrase_matches():
    assert _extract_clean_disease_name("Some Disease") == "some disease"


def test_condition_ols_fallback_success(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert url == ols_module.OLS_SEARCH_URL
        return _DummyResponse(
            {
                "response": {
                    "docs": [{"label": "rare metabolic disorder", "obo_id": "EFO_9999"}]
                }
            }
        )

    monkeypatch.setattr(requests, "get", fake_get)
    t = normalize_condition("patients with a rare metabolic disorder")
    assert t.label == "rare metabolic disorder"
    assert t.ontology_id == "EFO:9999"
    assert t.status == "PRESENT"


def test_condition_ols_fallback_no_hit_returns_partially_present(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _DummyResponse({"response": {"docs": []}})
    )
    t = normalize_condition("some entirely unmapped condition")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.ontology_id == ""
    assert t.mapping_confidence == 0.5


# ---------------------------------------------------------------------------
# sample_size.py: _simple_word_to_num (the word2number-unavailable fallback,
# previously untested - word2number is installed in this environment, so
# the production code path through it is exercised directly here, and the
# normalize_sample_size() delegation to it is exercised by monkeypatching
# the module's `w2n` global to simulate word2number being absent).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ninety eight", 98),
        ("thirty", 30),
        ("one hundred", 100),
        ("two thousand", 2000),
        ("two thousand and fifty", 2050),
        ("twelve", 12),
        ("zero", 0),
    ],
)
def test_simple_word_to_num_parses_common_phrasings(text, expected):
    assert _simple_word_to_num(text) == expected


def test_simple_word_to_num_returns_none_for_unparseable_text():
    assert _simple_word_to_num("no numbers here") is None


def test_simple_word_to_num_returns_none_for_empty_text():
    assert _simple_word_to_num("") is None


def test_simple_word_to_num_stops_at_first_non_number_word():
    # "fifty dogs were studied" - consumes "fifty", stops at "dogs"
    assert _simple_word_to_num("fifty dogs were studied") == 50


def test_normalize_sample_size_uses_simple_fallback_when_word2number_absent(
    monkeypatch,
):
    monkeypatch.setattr(sample_size_module, "w2n", None)
    t = normalize_sample_size("forty two")
    assert t.label == "42"
    assert t.status == "PRESENT"
    assert t.mapping_confidence == 1.0


def test_normalize_sample_size_simple_fallback_miss_falls_through_to_regex(
    monkeypatch,
):
    monkeypatch.setattr(sample_size_module, "w2n", None)
    t = normalize_sample_size("approximately 42 mice")
    assert t.label == "42"
    assert t.mapping_confidence == 0.9

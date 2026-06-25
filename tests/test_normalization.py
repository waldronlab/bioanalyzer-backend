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
from app.normalization.taxa_level import normalize_taxa_level


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
    assert t.ontology_id == ""

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
    assert t.ontology_id == "EFO:0002508"
    assert t.status == "PRESENT"

    t = normalize_condition("type 2 diabetes cohort")
    assert t.label == "type 2 diabetes mellitus"
    assert t.ontology_id == "EFO:0001360"

    t = normalize_condition("obese adults")
    assert t.label == "obesity"
    assert t.ontology_id == "EFO:0001073"

    t = normalize_condition("healthy controls")
    assert t.label == "healthy"
    assert t.status == "PRESENT"

    t = normalize_condition("COVID-19 cases")
    assert t.label == "COVID-19"
    assert t.ontology_id == "EFO:0003601"

    t = normalize_condition("")
    assert t.status == "ABSENT"


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

    t = normalize_sequencing_type("new custom chemistry")
    assert t.status == "PARTIALLY_PRESENT"


def test_taxa_level_normalization_variants():
    t = normalize_taxa_level("genus level analysis")
    assert t.label == "genus"
    assert t.status == "PRESENT"
    assert t.ontology_id == ""

    t = normalize_taxa_level("operational taxonomic units")
    assert t.label == "OTU"
    assert t.status == "PRESENT"

    t = normalize_taxa_level("amplicon sequence variants")
    assert t.label == "ASV"

    t = normalize_taxa_level("species and genus")
    assert t.status == "PARTIALLY_PRESENT"

    t = normalize_taxa_level("")
    assert t.status == "ABSENT"


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
# body_site.py: multiple-keyword match + OLS fallback (previously untested)
# ---------------------------------------------------------------------------


def test_body_site_multiple_matches_is_partially_present():
    t = normalize_body_site("fecal and salivary samples were both collected")
    assert t.status == "PARTIALLY_PRESENT"
    assert t.mapping_confidence == 0.9
    # first match in dict iteration order wins - just confirm it's one of
    # the two genuinely-matched pairs, not a third unrelated one.
    assert t.label in ("feces", "saliva")


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

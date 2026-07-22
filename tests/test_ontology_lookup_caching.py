"""Tests that OLS / NCBI Taxonomy lookups are cached and never hit the
real network in CI — all HTTP calls here are mocked.
"""

from unittest.mock import MagicMock, patch

import app.normalization.host_species as host_species
import app.normalization.ols as ols


def _fake_ols_response(label: str, obo_id: str):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "response": {"docs": [{"label": label, "obo_id": obo_id}]}
    }
    return resp


class TestOlsSearchCaching:
    def test_cache_hit_skips_network_call(self, monkeypatch):
        monkeypatch.setattr(
            ols,
            "get_cached_term",
            lambda provider, term: ("Parkinson disease", "EFO:0002508", 1.0),
        )
        store_mock = MagicMock()
        monkeypatch.setattr(ols, "store_cached_term", store_mock)

        with patch("app.normalization.ols.requests.get") as mock_get:
            result = ols.ols_search("parkinson disease", "efo", "EFO")

        mock_get.assert_not_called()
        store_mock.assert_not_called()
        assert result == ("Parkinson disease", "EFO:0002508", 1.0)

    def test_cache_miss_calls_network_and_stores_result(self, monkeypatch):
        monkeypatch.setattr(ols, "get_cached_term", lambda provider, term: None)
        store_mock = MagicMock()
        monkeypatch.setattr(ols, "store_cached_term", store_mock)

        with patch("app.normalization.ols.requests.get") as mock_get:
            mock_get.return_value = _fake_ols_response(
                "Parkinson disease", "EFO_0002508"
            )
            result = ols.ols_search("parkinsons", "efo", "EFO", mapping_confidence=0.9)

        mock_get.assert_called_once()
        store_mock.assert_called_once_with(
            "efo", "parkinsons", "Parkinson disease", "EFO:0002508", 0.9
        )
        assert result == ("Parkinson disease", "EFO:0002508", 0.9)

    def test_no_match_does_not_store_anything(self, monkeypatch):
        monkeypatch.setattr(ols, "get_cached_term", lambda provider, term: None)
        store_mock = MagicMock()
        monkeypatch.setattr(ols, "store_cached_term", store_mock)

        with patch("app.normalization.ols.requests.get") as mock_get:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"response": {"docs": []}}
            mock_get.return_value = resp
            result = ols.ols_search("totally unknown term", "efo", "EFO")

        assert result is None
        store_mock.assert_not_called()


class TestHostSpeciesNcbiCaching:
    def _fake_search_response(self, taxid: str):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"esearchresult": {"idlist": [taxid]}}
        return resp

    def _fake_summary_response(self, taxid: str, sci_name: str):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "result": {taxid: {"scientificname": sci_name, "taxid": taxid}}
        }
        return resp

    def test_cache_hit_skips_network_call(self, monkeypatch):
        monkeypatch.setattr(
            host_species,
            "get_cached_term",
            lambda provider, term: ("Danio rerio", "NCBITaxon:7955", 0.9),
        )
        store_mock = MagicMock()
        monkeypatch.setattr(host_species, "store_cached_term", store_mock)

        with (
            patch("app.normalization.host_species.requests.get") as mock_get,
            patch("app.normalization.host_species.time.sleep"),
        ):
            result = host_species.normalize_host_species("Oryzias latipes")

        mock_get.assert_not_called()
        store_mock.assert_not_called()
        assert result.label == "Danio rerio"
        assert result.ontology_id == "NCBITaxon:7955"
        assert result.status == "PRESENT"

    def test_cache_miss_calls_network_and_stores_result(self, monkeypatch):
        monkeypatch.setattr(
            host_species, "get_cached_term", lambda provider, term: None
        )
        store_mock = MagicMock()
        monkeypatch.setattr(host_species, "store_cached_term", store_mock)

        with (
            patch("app.normalization.host_species.requests.get") as mock_get,
            patch("app.normalization.host_species.time.sleep"),
        ):
            mock_get.side_effect = [
                self._fake_search_response("8090"),
                self._fake_summary_response("8090", "Oryzias latipes"),
            ]
            result = host_species.normalize_host_species("Oryzias latipes")

        assert mock_get.call_count == 2
        store_mock.assert_called_once_with(
            "ncbitaxon", "Oryzias latipes", "Oryzias latipes", "NCBITaxon:8090", 0.9
        )
        assert result.label == "Oryzias latipes"
        assert result.ontology_id == "NCBITaxon:8090"

    def test_static_lookup_never_touches_cache_or_network(self, monkeypatch):
        """Known species (e.g. 'humans') resolve from the static table —
        no need to consult the cache or the network at all."""
        cache_mock = MagicMock(side_effect=AssertionError("should not be called"))
        monkeypatch.setattr(host_species, "get_cached_term", cache_mock)

        with patch("app.normalization.host_species.requests.get") as mock_get:
            result = host_species.normalize_host_species("humans")

        mock_get.assert_not_called()
        cache_mock.assert_not_called()
        assert result.label == "Homo sapiens"

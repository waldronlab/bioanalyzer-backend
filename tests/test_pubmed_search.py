from app.pubmed_queries import (
    HIGH_PRECISION_QUERY,
    RECOMMENDED_DISCOVERY_QUERY,
    SEARCH_PRESETS,
    ULTRA_BROAD_QUERY,
)


def test_search_presets_defined():
    assert SEARCH_PRESETS["discovery"] == RECOMMENDED_DISCOVERY_QUERY
    assert SEARCH_PRESETS["broad"] == ULTRA_BROAD_QUERY
    assert SEARCH_PRESETS["precision"] == HIGH_PRECISION_QUERY


def test_discovery_query_has_spec_components():
    q = RECOMMENDED_DISCOVERY_QUERY
    assert "Microbiota" in q
    assert "metagenomics" in q
    assert "abundance" in q
    assert "review[Publication Type]" in q

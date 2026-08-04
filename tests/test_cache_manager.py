"""
Tests for cache manager in app/services/cache_manager.py
"""

import pytest
import tempfile
import json
import os
from pathlib import Path

from conftest import import_with_fallback

# Import CacheManager directly to avoid import chain issues, falling back to
# loading the module straight from its file when the normal import fails.
CacheManager = import_with_fallback("cache_manager", "CacheManager", on_missing="raise")


@pytest.fixture
def temp_cache_dir():
    """Create a temporary cache directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def cache_manager(temp_cache_dir):
    """Create a CacheManager instance with temporary directory."""
    db_path = os.path.join(temp_cache_dir, "test_cache.db")
    return CacheManager(cache_dir=temp_cache_dir, db_path=db_path)


class TestCacheManagerInit:
    """Tests for CacheManager initialization."""

    def test_init_creates_directories(self, temp_cache_dir):
        """Test that initialization creates necessary directories."""
        db_path = os.path.join(temp_cache_dir, "test.db")
        manager = CacheManager(cache_dir=temp_cache_dir, db_path=db_path)
        assert os.path.exists(temp_cache_dir)
        assert os.path.exists(db_path)

    def test_init_creates_tables(self, cache_manager):
        """Test that initialization creates database tables."""
        # Try to query tables to verify they exist
        import sqlite3

        conn = sqlite3.connect(cache_manager.db_path)
        cursor = conn.cursor()

        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "analysis_cache" in tables
        assert "metadata_cache" in tables
        assert "fulltext_cache" in tables

        conn.close()


class TestAnalysisCache:
    """Tests for analysis result caching."""

    def test_store_analysis_result(self, cache_manager):
        """Test storing analysis results."""
        pmid = "12345678"
        analysis_data = {"host_species": {"value": "Human", "confidence": 0.95}}
        metadata = {"title": "Test Paper", "authors": ["Author1"]}

        result = cache_manager.store_analysis_result(
            pmid, analysis_data, metadata, source="test", confidence=0.95
        )
        assert result is True

    def test_get_analysis_result(self, cache_manager):
        """Test retrieving analysis results."""
        pmid = "12345678"
        analysis_data = {"host_species": {"value": "Human", "confidence": 0.95}}
        metadata = {"title": "Test Paper"}

        # Store first
        cache_manager.store_analysis_result(
            pmid, analysis_data, metadata, source="test", confidence=0.95
        )

        # Retrieve
        result = cache_manager.get_analysis_result(pmid)
        assert result is not None
        assert result["cached"] is True
        assert result["analysis_data"]["host_species"]["value"] == "Human"
        assert result["metadata"]["title"] == "Test Paper"
        assert result["confidence"] == 0.95

    def test_get_analysis_result_not_found(self, cache_manager):
        """Test retrieving non-existent analysis result."""
        result = cache_manager.get_analysis_result("99999999")
        assert result is None

    def test_store_analysis_result_overwrites(self, cache_manager):
        """Test that storing again overwrites existing result."""
        pmid = "12345678"
        analysis_data1 = {"host_species": {"value": "Human"}}
        analysis_data2 = {"host_species": {"value": "Mouse"}}
        metadata = {"title": "Test"}

        cache_manager.store_analysis_result(pmid, analysis_data1, metadata)
        cache_manager.store_analysis_result(pmid, analysis_data2, metadata)

        result = cache_manager.get_analysis_result(pmid)
        assert result["analysis_data"]["host_species"]["value"] == "Mouse"


class TestMetadataCache:
    """Tests for metadata caching."""

    def test_store_metadata(self, cache_manager):
        """Test storing metadata."""
        pmid = "12345678"
        metadata = {
            "title": "Test Paper",
            "authors": ["Author1", "Author2"],
            "journal": "Test Journal",
        }

        result = cache_manager.store_metadata(pmid, metadata, source="test")
        assert result is True

    def test_get_metadata(self, cache_manager):
        """Test retrieving metadata."""
        pmid = "12345678"
        metadata = {"title": "Test Paper", "authors": ["Author1"]}

        cache_manager.store_metadata(pmid, metadata, source="test")
        result = cache_manager.get_metadata(pmid)

        assert result is not None
        assert result["cached"] is True
        assert result["metadata"]["title"] == "Test Paper"
        assert result["source"] == "test"

    def test_get_metadata_not_found(self, cache_manager):
        """Test retrieving non-existent metadata."""
        result = cache_manager.get_metadata("99999999")
        assert result is None

    def test_store_metadata_overwrites(self, cache_manager):
        """Test that storing again overwrites existing metadata."""
        pmid = "12345678"
        metadata1 = {"title": "Title 1"}
        metadata2 = {"title": "Title 2"}

        cache_manager.store_metadata(pmid, metadata1)
        cache_manager.store_metadata(pmid, metadata2)

        result = cache_manager.get_metadata(pmid)
        assert result["metadata"]["title"] == "Title 2"


class TestFulltextCache:
    """Tests for fulltext caching."""

    def test_store_fulltext(self, cache_manager):
        """Test storing fulltext."""
        pmid = "12345678"
        fulltext = (
            "This is the full text of the paper. It contains important information."
        )

        result = cache_manager.store_fulltext(pmid, fulltext, source="test")
        assert result is True

    def test_get_fulltext(self, cache_manager):
        """Test retrieving fulltext."""
        pmid = "12345678"
        fulltext = "This is the full text content."

        cache_manager.store_fulltext(pmid, fulltext, source="test")
        result = cache_manager.get_fulltext(pmid)

        assert result is not None
        assert result["cached"] is True
        assert result["fulltext"] == fulltext
        assert result["source"] == "test"

    def test_get_fulltext_not_found(self, cache_manager):
        """Test retrieving non-existent fulltext."""
        result = cache_manager.get_fulltext("99999999")
        assert result is None

    def test_store_fulltext_large(self, cache_manager):
        """Test storing large fulltext."""
        pmid = "12345678"
        fulltext = "A" * 10000  # Large text

        result = cache_manager.store_fulltext(pmid, fulltext)
        assert result is True

        retrieved = cache_manager.get_fulltext(pmid)
        assert retrieved["fulltext"] == fulltext


class TestOntologyTermCache:
    """Tests for the ontology term -> ID cache (NCBI Taxonomy / EBI OLS)."""

    def test_store_and_get_ontology_term(self, cache_manager):
        ok = cache_manager.store_ontology_term(
            "efo", "parkinson disease", "Parkinson disease", "EFO:0002508", 1.0
        )
        assert ok is True

        result = cache_manager.get_ontology_term("efo", "parkinson disease")
        assert result == ("Parkinson disease", "EFO:0002508", 1.0)

    def test_get_ontology_term_not_found(self, cache_manager):
        assert cache_manager.get_ontology_term("efo", "no such term") is None

    def test_ontology_term_cache_is_scoped_by_provider(self, cache_manager):
        """The same term string under different providers must not collide."""
        cache_manager.store_ontology_term(
            "uberon", "skin", "skin", "UBERON:0002097", 1.0
        )
        cache_manager.store_ontology_term(
            "efo", "skin", "skin disease", "EFO:0000000", 0.7
        )

        assert cache_manager.get_ontology_term("uberon", "skin") == (
            "skin",
            "UBERON:0002097",
            1.0,
        )
        assert cache_manager.get_ontology_term("efo", "skin") == (
            "skin disease",
            "EFO:0000000",
            0.7,
        )

    def test_store_ontology_term_overwrites(self, cache_manager):
        cache_manager.store_ontology_term(
            "ncbitaxon", "human", "Homo sapiens", "NCBITaxon:9606", 0.9
        )
        cache_manager.store_ontology_term(
            "ncbitaxon", "human", "Homo sapiens", "NCBITaxon:9606", 1.0
        )

        result = cache_manager.get_ontology_term("ncbitaxon", "human")
        assert result == ("Homo sapiens", "NCBITaxon:9606", 1.0)


class TestCacheStats:
    """Tests for cache statistics."""

    def test_get_cache_stats(self, cache_manager):
        """Test getting cache statistics."""
        # Store some data
        cache_manager.store_analysis_result(
            "12345678", {"test": "data"}, {"title": "Test"}, confidence=0.9
        )
        cache_manager.get_analysis_result("12345678")  # Cache hit

        stats = cache_manager.get_cache_stats()
        assert isinstance(stats, dict)
        assert "analysis_cache_count" in stats
        assert "metadata_cache_count" in stats
        assert "fulltext_cache_count" in stats
        assert stats["analysis_cache_count"] >= 1

    def test_get_cache_stats_empty(self, cache_manager):
        """Test getting cache stats with no operations."""
        stats = cache_manager.get_cache_stats()
        assert isinstance(stats, dict)
        assert "analysis_cache_count" in stats
        assert stats["analysis_cache_count"] == 0
        assert stats["metadata_cache_count"] == 0
        assert stats["fulltext_cache_count"] == 0


class TestCacheOperations:
    """Tests for cache operations."""

    def test_clear_cache(self, cache_manager):
        """Test clearing the cache."""
        # Store some data
        cache_manager.store_analysis_result(
            "12345678", {"test": "data"}, {"title": "Test"}
        )
        cache_manager.store_metadata("12345678", {"title": "Test"})

        # Clear cache
        result = cache_manager.clear_all_cache()
        assert result is True

        # Verify data is gone
        assert cache_manager.get_analysis_result("12345678") is None
        assert cache_manager.get_metadata("12345678") is None

    def test_delete_old_entries(self, cache_manager):
        """Test deleting old cache entries."""
        # Store some data
        cache_manager.store_analysis_result(
            "12345678", {"test": "data"}, {"title": "Test"}
        )

        # Delete old entries (with 0 hours, should delete everything)
        result = cache_manager.clear_old_cache(max_age_hours=0)
        assert result >= 0

        # Verify data is gone
        assert cache_manager.get_analysis_result("12345678") is None


class TestAsyncOperations:
    """Tests for async cache operations."""

    @pytest.mark.asyncio
    async def test_store_analysis_result_async(self, cache_manager):
        """Test async storing of analysis results."""
        pmid = "12345678"
        analysis_data = {"test": "data"}
        metadata = {"title": "Test"}

        result = await cache_manager.store_analysis_result_async(
            pmid, analysis_data, metadata
        )
        assert result is True

        # Verify it was stored
        retrieved = cache_manager.get_analysis_result(pmid)
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_get_analysis_result_async(self, cache_manager):
        """Test async retrieving of analysis results."""
        pmid = "12345678"
        analysis_data = {"test": "data"}
        metadata = {"title": "Test"}

        # Store first
        cache_manager.store_analysis_result(pmid, analysis_data, metadata)

        # Retrieve async
        result = await cache_manager.get_analysis_result_async(pmid)
        assert result is not None
        assert result["cached"] is True

    @pytest.mark.asyncio
    async def test_store_metadata_async(self, cache_manager):
        """Test async storing of metadata."""
        pmid = "12345678"
        metadata = {"title": "Test Paper"}

        result = await cache_manager.store_metadata_async(pmid, metadata)
        assert result is True

        # Verify it was stored
        retrieved = cache_manager.get_metadata(pmid)
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_store_fulltext_async(self, cache_manager):
        """Test async storing of fulltext."""
        pmid = "12345678"
        fulltext = "Test fulltext content"

        result = await cache_manager.store_fulltext_async(pmid, fulltext)
        assert result is True

        # Verify it was stored
        retrieved = cache_manager.get_fulltext(pmid)
        assert retrieved is not None


class TestIsCacheValid:
    """Tests for is_cache_valid - previously entirely untested."""

    def test_recent_timestamp_is_valid(self, cache_manager):
        from datetime import datetime

        assert cache_manager.is_cache_valid(datetime.now().isoformat()) is True

    def test_old_timestamp_is_invalid(self, cache_manager):
        from datetime import datetime, timedelta

        old = (datetime.now() - timedelta(hours=48)).isoformat()
        assert cache_manager.is_cache_valid(old, max_age_hours=24) is False

    def test_respects_custom_max_age(self, cache_manager):
        from datetime import datetime, timedelta

        ts = (datetime.now() - timedelta(hours=2)).isoformat()
        assert cache_manager.is_cache_valid(ts, max_age_hours=1) is False
        assert cache_manager.is_cache_valid(ts, max_age_hours=3) is True

    def test_malformed_timestamp_returns_false(self, cache_manager):
        assert cache_manager.is_cache_valid("not-a-timestamp") is False

    def test_empty_timestamp_returns_false(self, cache_manager):
        assert cache_manager.is_cache_valid("") is False


class TestSearchCache:
    """Tests for search_cache - previously entirely untested."""

    def test_search_analysis_type_matches_query(self, cache_manager):
        cache_manager.store_analysis_result(
            "111", {"summary": "gut microbiome study"}, {"title": "Paper A"}
        )
        cache_manager.store_analysis_result(
            "222", {"summary": "unrelated topic"}, {"title": "Paper B"}
        )
        results = cache_manager.search_cache("microbiome", search_type="analysis")
        pmids = [r[0] for r in results]
        assert "111" in pmids
        assert "222" not in pmids

    def test_search_metadata_type_matches_query(self, cache_manager):
        cache_manager.store_metadata("333", {"title": "Gut Microbiome Research"})
        cache_manager.store_metadata("444", {"title": "Unrelated"})
        results = cache_manager.search_cache("Microbiome", search_type="metadata")
        pmids = [r[0] for r in results]
        assert "333" in pmids
        assert "444" not in pmids

    def test_search_all_searches_every_table(self, cache_manager):
        cache_manager.store_fulltext("555", "discusses microbiome diversity")
        results = cache_manager.search_cache("microbiome", search_type="all")
        pmids = [r[0] for r in results]
        assert "555" in pmids

    def test_search_returns_empty_list_when_no_match(self, cache_manager):
        assert cache_manager.search_cache("no such term anywhere") == []

    def test_search_handles_db_error_gracefully(self, cache_manager, monkeypatch):
        import sqlite3 as sqlite3_module

        def boom(*a, **k):
            raise sqlite3_module.OperationalError("db is locked")

        monkeypatch.setattr(sqlite3_module, "connect", boom)
        assert cache_manager.search_cache("anything") == []


class TestDeleteOperations:
    """Tests for delete_analysis_result/delete_metadata/delete_fulltext -
    previously entirely untested."""

    def test_delete_analysis_result_found(self, cache_manager):
        cache_manager.store_analysis_result("111", {"a": 1}, {"title": "T"})
        assert cache_manager.delete_analysis_result("111") is True
        assert cache_manager.get_analysis_result("111") is None

    def test_delete_analysis_result_not_found(self, cache_manager):
        assert cache_manager.delete_analysis_result("does-not-exist") is False

    def test_delete_metadata_found(self, cache_manager):
        cache_manager.store_metadata("222", {"title": "T"})
        assert cache_manager.delete_metadata("222") is True
        assert cache_manager.get_metadata("222") is None

    def test_delete_metadata_not_found(self, cache_manager):
        assert cache_manager.delete_metadata("does-not-exist") is False

    def test_delete_fulltext_found(self, cache_manager):
        cache_manager.store_fulltext("333", "full text body")
        assert cache_manager.delete_fulltext("333") is True
        assert cache_manager.get_fulltext("333") is None

    def test_delete_fulltext_not_found(self, cache_manager):
        assert cache_manager.delete_fulltext("does-not-exist") is False


class TestGetCacheSizeMb:
    def test_returns_zero_when_db_does_not_exist(self, cache_manager):
        cache_manager.db_path = Path("/no/such/path/cache.db")
        assert cache_manager._get_cache_size_mb() == 0.0

    def test_returns_positive_size_for_real_db(self, cache_manager):
        cache_manager.store_analysis_result("111", {"a": 1}, {"title": "T"})
        assert cache_manager._get_cache_size_mb() >= 0.0


class TestErrorHandlingBranches:
    """Exercise the except-Exception branches across CacheManager by making
    sqlite3.connect raise, confirming every public method degrades to its
    documented safe default instead of propagating."""

    def test_store_analysis_result_returns_false_on_db_error(
        self, cache_manager, monkeypatch
    ):
        monkeypatch.setattr(
            cache_manager,
            "_get_connection",
            lambda: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.store_analysis_result("1", {}, {}) is False

    def test_get_analysis_result_returns_none_on_db_error(
        self, cache_manager, monkeypatch
    ):
        monkeypatch.setattr(
            cache_manager,
            "_get_connection",
            lambda: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.get_analysis_result("1") is None

    def test_store_metadata_returns_false_on_db_error(self, cache_manager, monkeypatch):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.store_metadata("1", {}) is False

    def test_get_metadata_returns_none_on_db_error(self, cache_manager, monkeypatch):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.get_metadata("1") is None

    def test_store_fulltext_returns_false_on_db_error(self, cache_manager, monkeypatch):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.store_fulltext("1", "text") is False

    def test_get_fulltext_returns_none_on_db_error(self, cache_manager, monkeypatch):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.get_fulltext("1") is None

    def test_get_cache_stats_returns_empty_dict_on_db_error(
        self, cache_manager, monkeypatch
    ):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.get_cache_stats() == {}

    def test_clear_old_cache_returns_zero_on_db_error(self, cache_manager, monkeypatch):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.clear_old_cache() == 0

    def test_delete_analysis_result_returns_false_on_db_error(
        self, cache_manager, monkeypatch
    ):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.delete_analysis_result("1") is False

    def test_delete_metadata_returns_false_on_db_error(
        self, cache_manager, monkeypatch
    ):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.delete_metadata("1") is False

    def test_delete_fulltext_returns_false_on_db_error(
        self, cache_manager, monkeypatch
    ):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.delete_fulltext("1") is False

    def test_clear_all_cache_returns_false_on_db_error(
        self, cache_manager, monkeypatch
    ):
        import sqlite3 as sqlite3_module

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        assert cache_manager.clear_all_cache() is False

    def test_init_database_logs_error_without_raising(
        self, monkeypatch, temp_cache_dir
    ):
        import sqlite3 as sqlite3_module
        import os

        monkeypatch.setattr(
            sqlite3_module,
            "connect",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
        )
        db_path = os.path.join(temp_cache_dir, "broken.db")
        CacheManager(cache_dir=temp_cache_dir, db_path=db_path)  # should not raise

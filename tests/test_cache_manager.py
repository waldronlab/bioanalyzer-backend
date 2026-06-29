"""
Tests for cache manager in app/services/cache_manager.py
"""

import pytest
import tempfile
import json
import os
from pathlib import Path

# Import CacheManager directly to avoid import chain issues
try:
    # Try direct import first
    from app.services.cache_manager import CacheManager
except ImportError:
    # If that fails, try importing the module directly
    import sys
    from pathlib import Path

    cache_manager_path = (
        Path(__file__).parent.parent / "app" / "services" / "cache_manager.py"
    )
    if cache_manager_path.exists():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "cache_manager", cache_manager_path
        )
        cache_manager_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cache_manager_module)
        CacheManager = cache_manager_module.CacheManager
    else:
        raise


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
        cache_manager.store_ontology_term("ncbitaxon", "human", "Homo sapiens", "NCBITaxon:9606", 0.9)
        cache_manager.store_ontology_term("ncbitaxon", "human", "Homo sapiens", "NCBITaxon:9606", 1.0)

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

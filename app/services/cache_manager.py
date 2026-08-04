import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import asyncio
import time
from app.utils.credential_masking import mask_exception_message
from app.utils.performance_logger import perf_logger

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching of analysis results and metadata."""

    def __init__(
        self, cache_dir: str = "cache", db_path: str = "cache/analysis_cache.db"
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _get_connection(self):
        """Get a database connection. Always create a new one for thread safety."""
        # Use check_same_thread=False to allow cross-thread usage
        # This is safe when each operation uses its own connection
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _return_connection(self, conn):
        """Close the connection. No pooling for thread safety."""
        conn.close()

    def _init_database(self):
        """Initialize SQLite database for caching."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_cache (
                    pmid TEXT PRIMARY KEY,
                    analysis_data TEXT,
                    metadata TEXT,
                    timestamp TEXT,
                    source TEXT,
                    confidence REAL
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata_cache (
                    pmid TEXT PRIMARY KEY,
                    metadata TEXT,
                    timestamp TEXT,
                    source TEXT
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fulltext_cache (
                    pmid TEXT PRIMARY KEY,
                    fulltext TEXT,
                    timestamp TEXT,
                    source TEXT
                )
            """
            )

            # Ontology term -> ID lookups (NCBI Taxonomy, EBI OLS). Keyed by
            # (provider, term) rather than PMID, and has no TTL: a confirmed
            # mapping for a term doesn't go stale the way an LLM extraction
            # can, so unlike analysis_cache it's never treated as expired.
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ontology_term_cache (
                    provider TEXT NOT NULL,
                    term TEXT NOT NULL,
                    label TEXT,
                    ontology_id TEXT,
                    confidence REAL,
                    timestamp TEXT,
                    PRIMARY KEY (provider, term)
                )
            """
            )

            # Round-trip/obsolete/branch grounding checks for ontology_id's that
            # tier_for() would otherwise mark "auto" (see app.normalization.grounding).
            # Unlike ontology_term_cache, this DOES expire - a term's obsolete/branch
            # status can legitimately change as the upstream ontology evolves, which
            # is exactly the drift this cache exists to keep catching.
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS grounding_check_cache (
                    ontology_id TEXT PRIMARY KEY,
                    term_exists INTEGER,
                    label TEXT,
                    is_obsolete INTEGER,
                    replaced_by TEXT,
                    branch_ok INTEGER,
                    root_id TEXT,
                    timestamp TEXT
                )
            """
            )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_analysis_timestamp ON analysis_cache(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_metadata_timestamp ON metadata_cache(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fulltext_timestamp ON fulltext_cache(timestamp)"
            )

            conn.commit()
            logger.info("Cache database initialized successfully")

        except Exception as e:
            logger.error(
                f"Failed to initialize cache database: {mask_exception_message(e)}"
            )
        finally:
            if conn:
                conn.close()

    def store_analysis_result(
        self,
        pmid: str,
        analysis_data: Dict,
        metadata: Dict,
        source: str = "gemini",
        confidence: float = 0.0,
    ) -> bool:
        """Store analysis results in the cache database."""
        start_time = time.time()
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO analysis_cache
                (pmid, analysis_data, metadata, timestamp, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    pmid,
                    json.dumps(analysis_data, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    datetime.now().isoformat(),
                    source,
                    confidence,
                ),
            )

            conn.commit()
            duration = time.time() - start_time
            perf_logger.log_cache_operation("STORE", pmid, "analysis", duration, True)
            logger.info(f"Stored analysis result for PMID {pmid}")
            return True

        except Exception as e:
            duration = time.time() - start_time
            perf_logger.log_cache_operation("STORE", pmid, "analysis", duration, False)
            logger.error(
                f"Failed to store analysis result for PMID {pmid}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def get_analysis_result(self, pmid: str) -> Optional[Dict]:
        """Retrieve analysis results from cache."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT analysis_data, metadata, timestamp, source, confidence
                FROM analysis_cache
                WHERE pmid = ?
            """,
                (pmid,),
            )

            result = cursor.fetchone()

            if result:
                analysis_data, metadata, timestamp, source, confidence = result
                return {
                    "analysis_data": json.loads(analysis_data),
                    "metadata": json.loads(metadata),
                    "timestamp": timestamp,
                    "source": source,
                    "confidence": confidence,
                    "cached": True,
                }

            return None

        except Exception as e:
            logger.error(
                f"Failed to retrieve analysis result for PMID {pmid}: {mask_exception_message(e)}"
            )
            return None
        finally:
            if conn:
                self._return_connection(conn)

    async def get_analysis_result_async(self, pmid: str) -> Optional[Dict]:
        """Async version of get_analysis_result for better performance."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_analysis_result, pmid)

    async def store_analysis_result_async(
        self,
        pmid: str,
        analysis_data: Dict,
        metadata: Dict,
        source: str = "gemini",
        confidence: float = 0.0,
    ) -> bool:
        """Async version of store_analysis_result for better performance."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.store_analysis_result,
            pmid,
            analysis_data,
            metadata,
            source,
            confidence,
        )

    async def store_metadata_async(
        self, pmid: str, metadata: Dict, source: str = "pubmed"
    ) -> bool:
        """Async version of store_metadata for better performance."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.store_metadata, pmid, metadata, source
        )

    async def store_fulltext_async(
        self, pmid: str, fulltext: str, source: str = "pmc"
    ) -> bool:
        """Async version of store_fulltext for better performance."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.store_fulltext, pmid, fulltext, source
        )

    def store_metadata(self, pmid: str, metadata: Dict, source: str = "pubmed") -> bool:
        """Store paper metadata in cache."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO metadata_cache
                (pmid, metadata, timestamp, source)
                VALUES (?, ?, ?, ?)
            """,
                (
                    pmid,
                    json.dumps(metadata, ensure_ascii=False),
                    datetime.now().isoformat(),
                    source,
                ),
            )

            conn.commit()
            logger.info(f"Stored metadata for PMID {pmid}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to store metadata for PMID {pmid}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def get_metadata(self, pmid: str) -> Optional[Dict]:
        """Retrieve paper metadata from cache."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT metadata, timestamp, source
                FROM metadata_cache
                WHERE pmid = ?
            """,
                (pmid,),
            )

            result = cursor.fetchone()

            if result:
                metadata, timestamp, source = result
                return {
                    "metadata": json.loads(metadata),
                    "timestamp": timestamp,
                    "source": source,
                    "cached": True,
                }

            return None

        except Exception as e:
            logger.error(
                f"Failed to retrieve metadata for PMID {pmid}: {mask_exception_message(e)}"
            )
            return None
        finally:
            if conn:
                self._return_connection(conn)

    def store_fulltext(self, pmid: str, fulltext: str, source: str = "pmc") -> bool:
        """Store full text in cache."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO fulltext_cache
                (pmid, fulltext, timestamp, source)
                VALUES (?, ?, ?, ?)
            """,
                (pmid, fulltext, datetime.now().isoformat(), source),
            )

            conn.commit()
            logger.info(f"Stored fulltext for PMID {pmid}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to store fulltext for PMID {pmid}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def get_fulltext(self, pmid: str) -> Optional[Dict]:
        """Retrieve full text from cache."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT fulltext, timestamp, source
                FROM fulltext_cache
                WHERE pmid = ?
            """,
                (pmid,),
            )

            result = cursor.fetchone()

            if result:
                fulltext, timestamp, source = result
                return {
                    "fulltext": fulltext,
                    "timestamp": timestamp,
                    "source": source,
                    "cached": True,
                }

            return None

        except Exception as e:
            logger.error(
                f"Failed to retrieve fulltext for PMID {pmid}: {mask_exception_message(e)}"
            )
            return None
        finally:
            if conn:
                self._return_connection(conn)

    def get_ontology_term(self, provider: str, term: str) -> Optional[tuple]:
        """Return a cached (label, ontology_id, confidence) for *term*, or None.

        No TTL is applied — see ontology_term_cache table comment.
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT label, ontology_id, confidence
                FROM ontology_term_cache
                WHERE provider = ? AND term = ?
            """,
                (provider, term),
            )
            result = cursor.fetchone()
            return tuple(result) if result else None
        except Exception as e:
            logger.warning(
                f"Failed to read ontology cache for {provider}/{term}: {mask_exception_message(e)}"
            )
            return None
        finally:
            if conn:
                self._return_connection(conn)

    def store_ontology_term(
        self,
        provider: str,
        term: str,
        label: str,
        ontology_id: str,
        confidence: float,
    ) -> bool:
        """Persist a resolved (label, ontology_id, confidence) for *term*."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO ontology_term_cache
                (provider, term, label, ontology_id, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    provider,
                    term,
                    label,
                    ontology_id,
                    confidence,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning(
                f"Failed to store ontology cache for {provider}/{term}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def get_grounding_check(
        self, ontology_id: str, max_age_hours: int
    ) -> Optional[Dict[str, Any]]:
        """Return a cached grounding check for *ontology_id*, or None if absent/expired.

        See app.normalization.grounding for what a grounding check verifies
        (term round-trip existence, obsolete status, branch membership).
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT term_exists, label, is_obsolete, replaced_by, branch_ok,
                       root_id, timestamp
                FROM grounding_check_cache
                WHERE ontology_id = ?
            """,
                (ontology_id,),
            )
            result = cursor.fetchone()
            if not result:
                return None
            (
                term_exists,
                label,
                is_obsolete,
                replaced_by,
                branch_ok,
                root_id,
                timestamp,
            ) = result
            if not self.is_cache_valid(timestamp, max_age_hours):
                return None
            return {
                "term_exists": bool(term_exists),
                "label": label or "",
                "is_obsolete": bool(is_obsolete),
                "replaced_by": replaced_by or "",
                "branch_ok": None if branch_ok is None else bool(branch_ok),
                "root_id": root_id or "",
            }
        except Exception as e:
            logger.warning(
                f"Failed to read grounding cache for {ontology_id}: {mask_exception_message(e)}"
            )
            return None
        finally:
            if conn:
                self._return_connection(conn)

    def store_grounding_check(
        self,
        ontology_id: str,
        term_exists: bool,
        label: str,
        is_obsolete: bool,
        replaced_by: str,
        branch_ok: Optional[bool],
        root_id: str,
    ) -> bool:
        """Persist a resolved grounding check for *ontology_id*."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO grounding_check_cache
                (ontology_id, term_exists, label, is_obsolete, replaced_by,
                 branch_ok, root_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    ontology_id,
                    int(term_exists),
                    label,
                    int(is_obsolete),
                    replaced_by,
                    None if branch_ok is None else int(branch_ok),
                    root_id,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning(
                f"Failed to store grounding cache for {ontology_id}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def is_cache_valid(self, timestamp: str, max_age_hours: int = 24) -> bool:
        """Check if cached data is still valid based on age."""
        try:
            cache_time = datetime.fromisoformat(timestamp)
            current_time = datetime.now()
            age = current_time - cache_time

            return age < timedelta(hours=max_age_hours)

        except Exception as e:
            logger.warning(
                f"Failed to check cache validity: {mask_exception_message(e)}"
            )
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics and information."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get counts for each table
            cursor.execute("SELECT COUNT(*) FROM analysis_cache")
            analysis_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM metadata_cache")
            metadata_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM fulltext_cache")
            fulltext_count = cursor.fetchone()[0]

            # Get recent activity
            cursor.execute(
                """
                SELECT COUNT(*) FROM analysis_cache
                WHERE timestamp > datetime('now', '-24 hours')
            """
            )
            recent_analysis = cursor.fetchone()[0]

            # Get curation readiness stats
            # Note: curation_ready removed - all cached analyses are considered complete
            ready_count = 0
            not_ready_count = 0

            return {
                "analysis_cache_count": analysis_count,
                "metadata_cache_count": metadata_count,
                "fulltext_cache_count": fulltext_count,
                "recent_analysis_24h": recent_analysis,
                "analysis_complete_count": analysis_count,
                "curation_not_ready_count": not_ready_count,
                "total_curation_analyzed": ready_count + not_ready_count,
                "curation_readiness_rate": (
                    ready_count / (ready_count + not_ready_count)
                    if (ready_count + not_ready_count) > 0
                    else 0.0
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get cache stats: {mask_exception_message(e)}")
            return {}
        finally:
            if conn:
                self._return_connection(conn)

    def _get_cache_size_mb(self) -> float:
        """Get the size of the cache database in MB."""
        try:
            if self.db_path.exists():
                size_bytes = self.db_path.stat().st_size
                return round(size_bytes / (1024 * 1024), 2)
            return 0.0
        except Exception:
            return 0.0

    def clear_old_cache(self, max_age_hours: int = 168) -> int:
        """Clear cache entries older than specified age. Returns number of cleared entries."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cutoff_time = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()

            # Clear old entries
            cursor.execute(
                "DELETE FROM analysis_cache WHERE timestamp < ?", (cutoff_time,)
            )
            analysis_cleared = cursor.rowcount

            cursor.execute(
                "DELETE FROM metadata_cache WHERE timestamp < ?", (cutoff_time,)
            )
            metadata_cleared = cursor.rowcount

            cursor.execute(
                "DELETE FROM fulltext_cache WHERE timestamp < ?", (cutoff_time,)
            )
            fulltext_cleared = cursor.rowcount

            conn.commit()

            total_cleared = analysis_cleared + metadata_cleared + fulltext_cleared
            logger.info(f"Cleared {total_cleared} old cache entries")

            return total_cleared

        except Exception as e:
            logger.error(f"Failed to clear old cache: {mask_exception_message(e)}")
            return 0
        finally:
            if conn:
                self._return_connection(conn)

    def search_cache(self, query: str, search_type: str = "all") -> List[Dict]:
        """Search cache for papers matching the query."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if search_type == "analysis":
                cursor.execute(
                    """
                    SELECT pmid, analysis_data, metadata, timestamp, confidence
                    FROM analysis_cache
                    WHERE analysis_data LIKE ? OR metadata LIKE ?
                    ORDER BY timestamp DESC
                """,
                    (f"%{query}%", f"%{query}%"),
                )
            elif search_type == "metadata":
                cursor.execute(
                    """
                    SELECT pmid, metadata, timestamp
                    FROM metadata_cache
                    WHERE metadata LIKE ?
                    ORDER BY timestamp DESC
                """,
                    (f"%{query}%",),
                )
            else:
                # Search all tables
                cursor.execute(
                    """
                    SELECT DISTINCT pmid FROM (
                        SELECT pmid FROM analysis_cache WHERE analysis_data LIKE ? OR metadata LIKE ?
                        UNION
                        SELECT pmid FROM metadata_cache WHERE metadata LIKE ?
                        UNION
                        SELECT pmid FROM fulltext_cache WHERE fulltext LIKE ?
                    )
                """,
                    (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
                )

            results = cursor.fetchall()

            return results

        except Exception as e:
            logger.error(f"Failed to search cache: {mask_exception_message(e)}")
            return []
        finally:
            if conn:
                self._return_connection(conn)

    def delete_analysis_result(self, pmid: str) -> bool:
        """Delete cached analysis results for a specific PMID."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM analysis_cache WHERE pmid = ?", (pmid,))
            deleted = cursor.rowcount > 0

            conn.commit()

            if deleted:
                logger.info(f"Deleted analysis cache for PMID {pmid}")
            else:
                logger.info(f"No analysis cache found for PMID {pmid}")

            return deleted

        except Exception as e:
            logger.error(
                f"Failed to delete analysis cache for PMID {pmid}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def delete_metadata(self, pmid: str) -> bool:
        """Delete cached metadata for a specific PMID."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM metadata_cache WHERE pmid = ?", (pmid,))
            deleted = cursor.rowcount > 0

            conn.commit()

            if deleted:
                logger.info(f"Deleted metadata cache for PMID {pmid}")
            else:
                logger.info(f"No metadata cache found for PMID {pmid}")

            return deleted

        except Exception as e:
            logger.error(
                f"Failed to delete metadata cache for PMID {pmid}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def delete_fulltext(self, pmid: str) -> bool:
        """Delete cached full text for a specific PMID."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM fulltext_cache WHERE pmid = ?", (pmid,))
            deleted = cursor.rowcount > 0

            conn.commit()

            if deleted:
                logger.info(f"Deleted full text cache for PMID {pmid}")
            else:
                logger.info(f"No full text cache found for PMID {pmid}")

            return deleted

        except Exception as e:
            logger.error(
                f"Failed to delete full text cache for PMID {pmid}: {mask_exception_message(e)}"
            )
            return False
        finally:
            if conn:
                self._return_connection(conn)

    def clear_all_cache(self) -> bool:
        """Clear all cached data."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM analysis_cache")
            analysis_deleted = cursor.rowcount

            cursor.execute("DELETE FROM metadata_cache")
            metadata_deleted = cursor.rowcount

            cursor.execute("DELETE FROM fulltext_cache")
            fulltext_deleted = cursor.rowcount

            conn.commit()

            total_deleted = analysis_deleted + metadata_deleted + fulltext_deleted
            logger.info(f"Cleared all cache: {total_deleted} entries deleted")

            return True

        except Exception as e:
            logger.error(f"Failed to clear all cache: {mask_exception_message(e)}")
            return False
        finally:
            if conn:
                self._return_connection(conn)

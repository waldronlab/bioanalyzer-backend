"""BugSigDB PMID cross-reference helpers with in-process caching."""

from __future__ import annotations

import logging
import time
from io import StringIO
from typing import Optional, Set, Union

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BUGSIGDB_DUMP_URL = (
    "https://raw.githubusercontent.com/waldronlab/BugSigDBExports/devel/full_dump.csv"
)

_bugsigdb_pmids: Optional[Set[int]] = None
_cache_loaded_at: float = 0.0
CACHE_TTL_SECONDS = 3600


def get_bugsigdb_pmids(force_refresh: bool = False) -> Set[int]:
    """Download and cache PMIDs already present in BugSigDB."""
    global _bugsigdb_pmids, _cache_loaded_at
    now = time.time()
    if (
        not force_refresh
        and _bugsigdb_pmids is not None
        and (now - _cache_loaded_at) < CACHE_TTL_SECONDS
    ):
        return _bugsigdb_pmids

    try:
        resp = requests.get(BUGSIGDB_DUMP_URL, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text), usecols=["PMID"], dtype={"PMID": str})
        pmids: Set[int] = set()
        for value in df["PMID"].dropna():
            try:
                pmids.add(int(str(value).strip()))
            except ValueError:
                continue
        _bugsigdb_pmids = pmids
        _cache_loaded_at = now
        return _bugsigdb_pmids
    except Exception as exc:
        logger.warning(
            "Could not fetch BugSigDB dump: %s. Defaulting in_bugsigdb to False.", exc
        )
        return set()


def is_in_bugsigdb(pmid: Union[int, str]) -> bool:
    """Return True if PMID exists in BugSigDB export."""
    try:
        pmid_int = int(str(pmid).strip())
    except (ValueError, TypeError):
        return False
    return pmid_int in get_bugsigdb_pmids()


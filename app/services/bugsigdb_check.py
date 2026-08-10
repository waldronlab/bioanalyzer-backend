"""BugSigDB PMID cross-reference helpers with in-process caching.

Source of truth is the local `full_dump.csv` (repo root, path overridable via
BUGSIGDB_DUMP_PATH) when present - it's the same BugSigDB export the eval
scripts under scripts/eval/ already use, kept locally per .gitignore rather
than committed. When no local copy exists (e.g. a fresh checkout or a
container that hasn't fetched one), falls back to downloading the same
export over HTTP.
"""

from __future__ import annotations

import logging
import os
import re
import time
from io import StringIO
from pathlib import Path
from typing import Optional, Set, Union

import pandas as pd
import requests

from app.utils.credential_masking import mask_exception_message

logger = logging.getLogger(__name__)

BUGSIGDB_DUMP_URL = (
    "https://raw.githubusercontent.com/waldronlab/BugSigDBExports/devel/full_dump.csv"
)

_DEFAULT_LOCAL_DUMP_PATH = Path(__file__).resolve().parents[2] / "full_dump.csv"
LOCAL_DUMP_PATH = Path(os.getenv("BUGSIGDB_DUMP_PATH", str(_DEFAULT_LOCAL_DUMP_PATH)))

_PMID_RE = re.compile(r"^\d+$")

_bugsigdb_pmids: Optional[Set[int]] = None
_cache_loaded_at: float = 0.0
CACHE_TTL_SECONDS = 3600


def normalize_pmid(pmid: Union[int, str, None]) -> Optional[int]:
    """Normalize a raw PMID to int, or None if missing/empty/invalid.

    Tolerates surrounding whitespace and int-vs-str representation; rejects
    anything that isn't a bare non-negative integer (NaN, DOIs, accession
    numbers like "PMC11017998", etc.).
    """
    if pmid is None:
        return None
    text = str(pmid).strip()
    if not text or not _PMID_RE.match(text):
        return None
    return int(text)


def _pmids_from_dataframe(df: "pd.DataFrame") -> Set[int]:
    pmids: Set[int] = set()
    for value in df["PMID"].dropna():
        normalized = normalize_pmid(value)
        if normalized is not None:
            pmids.add(normalized)
    return pmids


def _read_dump_csv(source) -> "pd.DataFrame":
    # The dump's first line is a "# BugSigDB <date>, License: ..." comment,
    # not the real CSV header - comment="#" skips it (a plain usecols=
    # read otherwise raises "Usecols do not match columns" and, upstream,
    # gets silently swallowed into an empty result). Some free-text columns
    # (e.g. Description) contain embedded newlines/commas that the default C
    # parser misaligns on a handful of rows, shifting unrelated values into
    # the PMID column - engine="python" parses those rows correctly instead.
    return pd.read_csv(
        source,
        usecols=["PMID"],
        dtype={"PMID": str},
        comment="#",
        engine="python",
        on_bad_lines="skip",
    )


def _load_from_local_file() -> Optional[Set[int]]:
    if not LOCAL_DUMP_PATH.is_file():
        return None
    try:
        return _pmids_from_dataframe(_read_dump_csv(LOCAL_DUMP_PATH))
    except Exception as exc:
        logger.warning(
            "Could not parse local BugSigDB dump at %s: %s",
            LOCAL_DUMP_PATH,
            mask_exception_message(exc),
        )
        return None


def _load_from_remote() -> Set[int]:
    try:
        resp = requests.get(BUGSIGDB_DUMP_URL, timeout=30)
        resp.raise_for_status()
        return _pmids_from_dataframe(_read_dump_csv(StringIO(resp.text)))
    except Exception as exc:
        logger.warning(
            "Could not fetch BugSigDB dump: %s. Defaulting in_bugsigdb to False.",
            mask_exception_message(exc),
        )
        return set()


def get_bugsigdb_pmids(force_refresh: bool = False) -> Set[int]:
    """Return the cached set of PMIDs already present in BugSigDB.

    Prefers the local dump (LOCAL_DUMP_PATH) as the source of truth; falls
    back to downloading the same export when no local copy is available.
    Cached in-process for CACHE_TTL_SECONDS so a batch of papers analyzed
    together doesn't reload/redownload the dump once per paper.
    """
    global _bugsigdb_pmids, _cache_loaded_at
    now = time.time()
    if (
        not force_refresh
        and _bugsigdb_pmids is not None
        and (now - _cache_loaded_at) < CACHE_TTL_SECONDS
    ):
        return _bugsigdb_pmids

    pmids = _load_from_local_file()
    if pmids is None:
        pmids = _load_from_remote()

    _bugsigdb_pmids = pmids
    _cache_loaded_at = now
    return _bugsigdb_pmids


def is_in_bugsigdb(pmid: Union[int, str]) -> bool:
    """Return True if PMID exists in the BugSigDB export."""
    normalized = normalize_pmid(pmid)
    if normalized is None:
        return False
    return normalized in get_bugsigdb_pmids()

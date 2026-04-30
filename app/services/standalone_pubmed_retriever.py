"""
Standalone PubMed Retriever
===========================

Lightweight retrieval of PubMed metadata and PMC full-text XML.
No dependency on the full BioAnalyzer service stack.

Design notes
------------
* `full_text` in the returned dict is the **raw PMC XML string**.
  This lets `bugsigdb_analyzer._parse_pmc_sections()` extract section-labelled
  content (METHODS, RESULTS, …) without duplicating parsing logic here.
  Callers that need plain text can call:
      "".join(ElementTree.fromstring(full_text).itertext())

* Five methods from the previous version were collapsed:
    get_pmc_fulltext          → inlined into get_full_paper_data
    _extract_authors          → inlined into _parse_pubmed_xml
    _extract_publication_date → inlined into _parse_pubmed_xml
    _extract_body_text        → removed (body parsing done upstream)
    _parse_pmc_xml            → removed (raw XML returned instead)
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests
from defusedxml import ElementTree

logger = logging.getLogger(__name__)


class PubMedRetrieverError(Exception):
    """Raised for unrecoverable PubMed retrieval failures."""


class StandalonePubMedRetriever:
    """Retrieve PubMed metadata and PMC full-text without the full service stack."""

    BASE_URL         = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    DEFAULT_TIMEOUT  = 10
    RATE_LIMIT_DELAY = 0.34  # NCBI-recommended minimum inter-request delay (seconds)

    def __init__(
        self,
        api_key: Optional[str] = None,
        email: str = "bioanalyzer@example.com",
    ) -> None:
        self.api_key = api_key
        self.email   = email
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": f"BioAnalyzer/1.0 (contact: {email})"})

    # ------------------------------------------------------------------
    # Core HTTP layer
    # ------------------------------------------------------------------

    def _make_request(
        self, endpoint: str, params: Dict[str, Any], retries: int = 3
    ) -> Optional[str]:
        """GET an NCBI E-utilities endpoint with exponential-backoff retries.

        Returns the response body as a string, or None when all attempts fail.
        """
        url    = f"{self.BASE_URL}/{endpoint}"
        params = {
            **params,
            "email": self.email,
            "tool":  "BioAnalyzer",
            **({"api_key": self.api_key} if self.api_key else {}),
        }

        for attempt in range(retries):
            try:
                time.sleep(self.RATE_LIMIT_DELAY)
                response = self.session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"NCBI request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        logger.error(f"All {retries} attempts failed for {endpoint}")
        return None

    # ------------------------------------------------------------------
    # PubMed metadata
    # ------------------------------------------------------------------

    def fetch_paper_metadata(self, pmid: str) -> Dict[str, Any]:
        """Fetch and parse PubMed metadata for *pmid*.

        Returns a dict with: pmid, title, abstract, journal, authors,
        publication_date.  On failure returns {"error": "<message>"}.
        """
        xml_data = self._make_request(
            "efetch.fcgi", {"db": "pubmed", "id": pmid, "retmode": "xml"}
        )
        if not xml_data:
            return {"error": "PubMed unreachable or invalid response."}

        try:
            root    = ElementTree.fromstring(xml_data)
            article = root.find(".//PubmedArticle/MedlineCitation/Article")
        except ElementTree.ParseError as e:
            logger.error(f"XML parse error for PMID {pmid}: {e}")
            return {"error": f"XML parsing failed: {e}"}

        if article is None:
            return {"error": "No article metadata found."}

        # Authors: "Forename Lastname", skip entries with no last name
        authors = [
            f"{a.findtext('ForeName', '')} {a.findtext('LastName', '')}".strip()
            for a in article.findall(".//Author")
            if a.findtext("LastName")
        ]

        # Year: journal issue date preferred, article date as fallback
        pub_date = (
            article.findtext("Journal/JournalIssue/PubDate/Year")
            or article.findtext("ArticleDate/Year")
            or ""
        )

        return {
            "pmid":             pmid,
            "title":            article.findtext("ArticleTitle", "N/A"),
            "abstract":         " ".join(
                t.text for t in article.findall(".//AbstractText") if t.text
            ),
            "journal":          article.findtext("Journal/Title", "N/A"),
            "authors":          authors,
            "publication_date": pub_date,
        }

    # ------------------------------------------------------------------
    # PMC full-text
    # ------------------------------------------------------------------

    def _get_pmc_id_from_pmid(self, pmid: str) -> Optional[str]:
        """Resolve a PMID to its PMC ID via ELink, or return None."""
        xml_data = self._make_request(
            "elink.fcgi",
            {"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "xml"},
        )
        if not xml_data:
            return None

        try:
            root = ElementTree.fromstring(xml_data)
        except ElementTree.ParseError:
            return None

        for linksetdb in root.findall(".//LinkSetDb"):
            if (
                linksetdb.findtext("DbTo") == "pmc"
                and linksetdb.findtext("LinkName") == "pubmed_pmc"
            ):
                pmc_id = next(
                    (el.text for el in linksetdb.findall(".//Id") if el.text), None
                )
                if pmc_id:
                    return pmc_id if pmc_id.startswith("PMC") else f"PMC{pmc_id}"
        return None

    def _fetch_pmc_xml(self, pmc_id: str) -> str:
        """Download and return the raw PMC XML string for *pmc_id*.

        Returns an empty string when the content is unavailable.
        The raw XML is returned unchanged so that
        `bugsigdb_analyzer.prepare_analysis_context()` can extract
        section-labelled content without any duplication of parsing here.
        """
        clean_id = pmc_id[3:] if pmc_id.startswith("PMC") else pmc_id
        return (
            self._make_request(
                "efetch.fcgi", {"db": "pmc", "id": clean_id, "retmode": "xml"}
            )
            or ""
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_full_paper_data(self, pmid: str) -> Dict[str, Any]:
        """Retrieve complete paper data (metadata + PMC XML) for *pmid*.

        The `full_text` field contains the raw PMC XML string when available,
        preserving section structure for downstream analysis.

        Always returns a dict with all keys populated so callers can safely
        access any field regardless of retrieval outcome.
        """
        try:
            logger.info(f"Retrieving paper data for PMID {pmid}")

            metadata = self.fetch_paper_metadata(pmid)
            if "error" in metadata:
                return metadata

            pmc_id    = self._get_pmc_id_from_pmid(pmid)
            full_text = self._fetch_pmc_xml(pmc_id) if pmc_id else ""

            if not pmc_id:
                logger.info(f"No PMC ID for PMID {pmid} – abstract only")

            result = {
                **metadata,
                "full_text":           full_text,
                "has_full_text":       bool(full_text.strip()),
                "retrieval_timestamp": time.time(),
            }
            logger.info(f"Retrieved PMID {pmid} (full_text={'yes' if full_text else 'no'})")
            return result

        except Exception as e:
            logger.error(f"Error retrieving PMID {pmid}: {e}")
            return {
                "pmid": pmid, "error": f"Failed to retrieve paper data: {e}",
                "title": "", "abstract": "", "journal": "", "authors": [],
                "publication_date": "", "full_text": "", "has_full_text": False,
                "retrieval_timestamp": time.time(),
            }

    def search_papers(self, query: str, max_results: int = 10) -> List[str]:
        """Return a list of PMIDs matching *query* (up to *max_results*)."""
        xml_data = self._make_request(
            "esearch.fcgi",
            {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "xml"},
        )
        if not xml_data:
            logger.warning(f"Search for '{query}' returned no data.")
            return []

        try:
            root = ElementTree.fromstring(xml_data)
            return [el.text for el in root.findall(".//Id") if el.text]
        except ElementTree.ParseError as e:
            logger.error(f"Error parsing search results: {e}")
            return []
            
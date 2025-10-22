import requests
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional
from xml.etree import ElementTree
from app.utils.config import NCBI_RATE_LIMIT_DELAY, API_TIMEOUT, USE_FULLTEXT

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class PubMedRetriever:
    """
    Retrieves paper metadata and abstracts from PubMed using the NCBI E-Utilities API.
    Includes robust error handling and connectivity validation.
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, api_key: Optional[str] = None, email: str = "bioanalyzer@example.com"):
        self.api_key = api_key
        self.email = email
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"BioAnalyzer/1.0 (contact: {self.email})"
        })
        self._verify_connectivity()

    def _verify_connectivity(self, retries: int = 3) -> None:
        """
        Test NCBI E-utilities reachability on startup with retries.
        Logs actionable hints if not reachable.
        """
        test_url = f"{self.BASE_URL}/esearch.fcgi"
        params = {"db": "pubmed", "term": "cancer", "retmax": 1}
        for attempt in range(retries):
            try:
                # Use API_TIMEOUT from config (fallback to 10s if unset)
                timeout_val = API_TIMEOUT if API_TIMEOUT else 10
                resp = self.session.get(test_url, params=params, timeout=timeout_val)
                resp.raise_for_status()
                logger.info("✅ NCBI E-utilities reachable.")
                return  # Success, exit early
            except requests.exceptions.RequestException as e:
                logger.warning(f"NCBI connectivity check failed (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.warning(
                        "⚠️ Unable to reach NCBI E-utilities after retries. Check your internet, firewall, or API key.\n"
                        f"Details: {e}\n"
                        "The app will continue with limited functionality (e.g., cached data only)."
                    )

    def _get(self, endpoint: str, params: Dict[str, Any], retries: int = 3) -> Optional[str]:
        url = f"{self.BASE_URL}/{endpoint}"
        if self.api_key:
            params["api_key"] = self.api_key
        params["email"] = self.email
        params["tool"] = "BioAnalyzer"

        for attempt in range(retries):
            try:
                time.sleep(max(NCBI_RATE_LIMIT_DELAY, 0.0))
                per_request_timeout = min(API_TIMEOUT or 30, 8)
                response = self.session.get(url, params=params, timeout=(5, per_request_timeout))
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
                logger.warning(
                    f"NCBI request failed (attempt {attempt+1}/{retries}): {e} "
                    f"{'(rate limited)' if status == 429 else ''}"
                )
                if attempt < retries - 1:
                    backoff = (2 ** attempt) * (1.0 if status != 429 else 2.0)
                    time.sleep(backoff)
                    continue
                logger.error(f"❌ PubMed request failed after {retries} attempts: {e}")
                return None

    @staticmethod
    def validate_field(field: Any) -> bool:
        """Helper to check if a field is non-empty and valid."""
        return bool(field and str(field).strip())

    def fetch_paper_metadata(self, pmid: str) -> Dict[str, Any]:
        xml_data = self._get("efetch.fcgi", {"db": "pubmed", "id": pmid, "retmode": "xml"})

        if not xml_data:
            logger.error(f"❌ No data returned from PubMed for PMID {pmid}.")
            return {"error": "PubMed unreachable or invalid response."}

        try:
            root = ElementTree.fromstring(xml_data)
            article = root.find(".//PubmedArticle/MedlineCitation/Article")
            if article is None:
                logger.warning(f"⚠️ No article node found for PMID {pmid}.")
                return {"error": "No article metadata found."}

            title = article.findtext("ArticleTitle", default="N/A")
            abstract = " ".join([t.text for t in article.findall(".//AbstractText") if t.text])
            journal = article.findtext("Journal/Title", default="N/A")
            authors = [
                f"{a.findtext('ForeName', default='')} {a.findtext('LastName', default='')}".strip()
                for a in article.findall(".//Author")
                if a.findtext("LastName") is not None
            ]

            metadata = {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "authors": authors,
            }

            pub_date = article.findtext("Journal/JournalIssue/PubDate/Year") \
                       or article.findtext("ArticleDate/Year")
            if pub_date:
                metadata["publication_date"] = pub_date

            return metadata

        except ElementTree.ParseError as e:
            logger.error(f"XML parsing error for PMID {pmid}: {e}")

        # fallback to esummary
        try:
            xml_sum = self._get("esummary.fcgi", {"db": "pubmed", "id": pmid, "retmode": "xml"})
            if not xml_sum:
                return {"error": "Failed to retrieve esummary fallback."}
            root = ElementTree.fromstring(xml_sum)
            doc = root.find(".//DocSum")
            if doc is None:
                return {"error": "No summary record found."}
            fields = {"pmid": pmid}
            for item in doc.findall("Item"):
                name = item.get("Name") or ""
                if name == "Title":
                    fields["title"] = item.text or ""
                elif name == "FullJournalName":
                    fields["journal"] = item.text or ""
                elif name == "PubDate":
                    fields["publication_date"] = item.text or ""
                elif name == "AuthorList":
                    fields["authors"] = [a.text for a in item.findall("Item") if a.text]
            fields.setdefault("abstract", "")
            return fields
        except Exception as e:
            logger.error(f"Error parsing fallback esummary for PMID {pmid}: {e}")
            return {"error": "Fallback retrieval failed."}

    def search(self, query: str, max_results: int = 10) -> List[str]:
        xml_data = self._get("esearch.fcgi", {
            "db": "pubmed", "term": query, "retmax": max_results, "retmode": "xml"
        })
        if not xml_data:
            logger.warning(f"Search for '{query}' returned no results.")
            return []
        try:
            root = ElementTree.fromstring(xml_data)
            return [id_elem.text for id_elem in root.findall(".//Id")]
        except ElementTree.ParseError as e:
            logger.error(f"Error parsing search results: {e}")
            return []

    async def get_paper_metadata_async(self, pmid: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.fetch_paper_metadata, pmid)

    def get_pmc_fulltext(self, pmid: str) -> str:
        """
        Retrieve full text from PubMed Central (PMC) if available.
        This method attempts to find the PMC ID and retrieve the full text.
        """
        try:
            # First, try to get PMC ID from PubMed
            pmc_id = self._get_pmc_id_from_pmid(pmid)
            if not pmc_id:
                logger.info(f"No PMC ID found for PMID {pmid}")
                return ""
            
            # Retrieve full text from PMC
            return self._get_pmc_fulltext_by_id(pmc_id)
            
        except Exception as e:
            logger.warning(f"Error retrieving full text for PMID {pmid}: {e}")
            return ""

    def _get_pmc_id_from_pmid(self, pmid: str) -> Optional[str]:
        """Get PMC ID from PMID using ELink."""
        try:
            xml_data = self._get("elink.fcgi", {
                "dbfrom": "pubmed",
                "db": "pmc",
                "id": pmid,
                "retmode": "xml"
            })
            
            if not xml_data:
                return None
                
            root = ElementTree.fromstring(xml_data)
            # Look for LinkSetDb with PMC links
            for linksetdb in root.findall(".//LinkSetDb"):
                if linksetdb.get("DbTo") == "pmc":
                    for id_elem in linksetdb.findall(".//Id"):
                        pmc_id = id_elem.text
                        if pmc_id and pmc_id.startswith("PMC"):
                            return pmc_id
            return None
            
        except Exception as e:
            logger.warning(f"Error getting PMC ID for PMID {pmid}: {e}")
            return None

    def _get_pmc_fulltext_by_id(self, pmc_id: str) -> str:
        """Retrieve full text from PMC using PMC ID."""
        try:
            # Remove PMC prefix if present
            clean_id = pmc_id.replace("PMC", "") if pmc_id.startswith("PMC") else pmc_id
            
            xml_data = self._get("efetch.fcgi", {
                "db": "pmc",
                "id": clean_id,
                "retmode": "xml"
            })
            
            if not xml_data:
                return ""
                
            root = ElementTree.fromstring(xml_data)
            
            # Extract full text from PMC XML
            full_text_parts = []
            
            # Get article title
            title = root.findtext(".//article-title")
            if title:
                full_text_parts.append(f"Title: {title}")
            
            # Get abstract
            abstract = root.findtext(".//abstract")
            if abstract:
                full_text_parts.append(f"Abstract: {abstract}")
            
            # Get body text
            body = root.find(".//body")
            if body is not None:
                # Extract text from all paragraphs
                paragraphs = []
                for p in body.findall(".//p"):
                    if p.text:
                        paragraphs.append(p.text.strip())
                if paragraphs:
                    full_text_parts.append(f"Full Text: {' '.join(paragraphs)}")
            
            return "\n\n".join(full_text_parts)
            
        except Exception as e:
            logger.warning(f"Error retrieving PMC full text for {pmc_id}: {e}")
            return ""

    async def get_pmc_fulltext_async(self, pmid: str) -> str:
        """Async wrapper for PMC full text retrieval."""
        return await asyncio.to_thread(self.get_pmc_fulltext, pmid)

    def get_full_paper_data(self, pmid: str) -> Dict[str, Any]:
        """
        Retrieve complete paper data including metadata and full text.
        This is the main method for comprehensive paper retrieval.
        """
        try:
            logger.info(f"Retrieving full paper data for PMID: {pmid}")
            
            # Get metadata
            metadata = self.fetch_paper_metadata(pmid)
            if "error" in metadata:
                return metadata
            
            # Get full text
            full_text = self.get_pmc_fulltext(pmid)
            
            # Combine all data
            paper_data = {
                "pmid": pmid,
                "title": metadata.get("title", ""),
                "abstract": metadata.get("abstract", ""),
                "journal": metadata.get("journal", ""),
                "authors": metadata.get("authors", []),
                "publication_date": metadata.get("publication_date", ""),
                "full_text": full_text,
                "has_full_text": bool(full_text.strip()),
                "retrieval_timestamp": time.time()
            }
            
            logger.info(f"Successfully retrieved paper data for PMID: {pmid}")
            return paper_data
            
        except Exception as e:
            logger.error(f"Error retrieving full paper data for PMID {pmid}: {e}")
            return {
                "pmid": pmid,
                "error": f"Failed to retrieve paper data: {str(e)}",
                "title": "",
                "abstract": "",
                "journal": "",
                "authors": [],
                "publication_date": "",
                "full_text": "",
                "has_full_text": False,
                "retrieval_timestamp": time.time()
            }

    async def get_full_paper_data_async(self, pmid: str) -> Dict[str, Any]:
        """Async wrapper for full paper data retrieval."""
        return await asyncio.to_thread(self.get_full_paper_data, pmid)

    async def get_texts_for_analysis_async(self, pmid: str) -> Dict[str, str]:
        async def fetch_metadata():
            try:
                return await asyncio.wait_for(self.get_paper_metadata_async(pmid), timeout=6)
            except Exception as e:
                logger.error(f"Metadata fetch error for PMID {pmid}: {e}")
                return {}

        async def fetch_fulltext():
            try:
                return await asyncio.wait_for(self.get_pmc_fulltext_async(pmid), timeout=8)
            except Exception as e:
                logger.warning(f"Full text fetch error for PMID {pmid}: {e}")
                return ""

        if USE_FULLTEXT:
            metadata, full_text = await asyncio.gather(fetch_metadata(), fetch_fulltext())
        else:
            metadata = await fetch_metadata()
            full_text = ""

        return {
            "title": metadata.get("title", ""),
            "abstract": metadata.get("abstract", ""),
            "full_text": full_text or "",
        }
"""
Standalone PubMed Retriever
===========================

A lightweight PubMed retriever that doesn't depend on the full service stack.
This module provides basic functionality for retrieving paper metadata and full text
from PubMed and PubMed Central without requiring heavy dependencies.
"""

import requests
import time
import logging
from typing import Dict, Any, Optional, List
from xml.etree import ElementTree

logger = logging.getLogger(__name__)


class PubMedRetrieverError(Exception):
    """Custom exception for PubMed retrieval errors."""
    pass


class StandalonePubMedRetriever:
    """
    A standalone PubMed retriever for basic paper data retrieval.
    
    This class provides essential functionality for retrieving paper metadata
    and full text from PubMed and PubMed Central without requiring the full
    BioAnalyzer service stack.
    """
    
    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    DEFAULT_TIMEOUT = 10
    RATE_LIMIT_DELAY = 0.34  # NCBI recommended delay
    
    def __init__(self, api_key: Optional[str] = None, email: str = "bioanalyzer@example.com"):
        """
        Initialize the PubMed retriever.
        
        Args:
            api_key: Optional NCBI API key for higher rate limits
            email: Contact email for NCBI (required for API usage)
        """
        self.api_key = api_key
        self.email = email
        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Create a configured requests session."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": f"BioAnalyzer/1.0 (contact: {self.email})"
        })
        return session
    
    def _make_request(self, endpoint: str, params: Dict[str, Any], retries: int = 3) -> Optional[str]:
        """
        Make a request to NCBI E-utilities with retry logic.
        
        Args:
            endpoint: The E-utilities endpoint to call
            params: Parameters for the request
            retries: Number of retry attempts
            
        Returns:
            Response text or None if all retries failed
        """
        url = f"{self.BASE_URL}/{endpoint}"
        
        # Add required parameters
        if self.api_key:
            params["api_key"] = self.api_key
        params.update({
            "email": self.email,
            "tool": "BioAnalyzer"
        })
        
        for attempt in range(retries):
            try:
                time.sleep(self.RATE_LIMIT_DELAY)
                response = self.session.get(url, params=params, timeout=self.DEFAULT_TIMEOUT)
                response.raise_for_status()
                return response.text
            except requests.exceptions.RequestException as e:
                logger.warning(f"NCBI request failed (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                logger.error(f"All retry attempts failed for {endpoint}")
                return None
    
    def fetch_paper_metadata(self, pmid: str) -> Dict[str, Any]:
        """
        Fetch paper metadata from PubMed.
        
        Args:
            pmid: PubMed ID of the paper
            
        Returns:
            Dictionary containing paper metadata or error information
        """
        xml_data = self._make_request("efetch.fcgi", {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        })
        
        if not xml_data:
            return {"error": "PubMed unreachable or invalid response."}
        
        try:
            return self._parse_pubmed_xml(xml_data, pmid)
        except ElementTree.ParseError as e:
            logger.error(f"XML parsing error for PMID {pmid}: {e}")
            return {"error": f"XML parsing failed: {e}"}
    
    def _parse_pubmed_xml(self, xml_data: str, pmid: str) -> Dict[str, Any]:
        """Parse PubMed XML response."""
        root = ElementTree.fromstring(xml_data)
        article = root.find(".//PubmedArticle/MedlineCitation/Article")
        
        if article is None:
            return {"error": "No article metadata found."}
        
        # Extract basic metadata
        title = article.findtext("ArticleTitle", default="N/A")
        journal = article.findtext("Journal/Title", default="N/A")
        
        # Extract abstract
        abstract_parts = []
        for abstract_text in article.findall(".//AbstractText"):
            if abstract_text.text:
                abstract_parts.append(abstract_text.text)
        abstract = " ".join(abstract_parts)
        
        # Extract authors
        authors = self._extract_authors(article)
        
        # Extract publication date
        pub_date = self._extract_publication_date(article)
        
        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "authors": authors,
            "publication_date": pub_date
        }
    
    def _extract_authors(self, article) -> List[str]:
        """Extract author names from article XML."""
        authors = []
        for author in article.findall(".//Author"):
            forename = author.findtext("ForeName", default="")
            lastname = author.findtext("LastName", default="")
            if lastname:  # Only include authors with last names
                full_name = f"{forename} {lastname}".strip()
                authors.append(full_name)
        return authors
    
    def _extract_publication_date(self, article) -> str:
        """Extract publication date from article XML."""
        # Try journal issue date first
        pub_date = article.findtext("Journal/JournalIssue/PubDate/Year")
        if not pub_date:
            # Fallback to article date
            pub_date = article.findtext("ArticleDate/Year")
        return pub_date or ""
    
    def get_pmc_fulltext(self, pmid: str) -> str:
        """
        Retrieve full text from PubMed Central if available.
        
        Args:
            pmid: PubMed ID of the paper
            
        Returns:
            Full text content or empty string if not available
        """
        try:
            pmc_id = self._get_pmc_id_from_pmid(pmid)
            if not pmc_id:
                logger.info(f"No PMC ID found for PMID {pmid}")
                return ""
            
            return self._get_pmc_fulltext_by_id(pmc_id)
        except Exception as e:
            logger.warning(f"Error retrieving full text for PMID {pmid}: {e}")
            return ""
    
    def _get_pmc_id_from_pmid(self, pmid: str) -> Optional[str]:
        """Get PMC ID from PMID using ELink."""
        xml_data = self._make_request("elink.fcgi", {
            "dbfrom": "pubmed",
            "db": "pmc",
            "id": pmid,
            "retmode": "xml"
        })
        
        if not xml_data:
            return None
        
        try:
            root = ElementTree.fromstring(xml_data)
            for linksetdb in root.findall(".//LinkSetDb"):
                # Check if DbTo child element equals "pmc"
                db_to_elem = linksetdb.find("DbTo")
                if db_to_elem is not None and db_to_elem.text == "pmc":
                    # Look for the direct PMC link (not references)
                    link_name_elem = linksetdb.find("LinkName")
                    if link_name_elem is not None and link_name_elem.text == "pubmed_pmc":
                        for id_elem in linksetdb.findall(".//Id"):
                            pmc_id = id_elem.text
                            if pmc_id:
                                # Add PMC prefix if not present
                                if not pmc_id.startswith("PMC"):
                                    pmc_id = f"PMC{pmc_id}"
                                return pmc_id
            return None
        except ElementTree.ParseError:
            return None
    
    def _get_pmc_fulltext_by_id(self, pmc_id: str) -> str:
        """Retrieve full text from PMC using PMC ID."""
        clean_id = pmc_id.replace("PMC", "") if pmc_id.startswith("PMC") else pmc_id
        
        xml_data = self._make_request("efetch.fcgi", {
            "db": "pmc",
            "id": clean_id,
            "retmode": "xml"
        })
        
        if not xml_data:
            return ""
        
        try:
            return self._parse_pmc_xml(xml_data)
        except ElementTree.ParseError:
            return ""
    
    def _parse_pmc_xml(self, xml_data: str) -> str:
        """Parse PMC XML response to extract full text."""
        root = ElementTree.fromstring(xml_data)
        full_text_parts = []
        
        # Extract title
        title = root.findtext(".//article-title")
        if title:
            full_text_parts.append(f"Title: {title}")
        
        # Extract abstract
        abstract = root.findtext(".//abstract")
        if abstract:
            full_text_parts.append(f"Abstract: {abstract}")
        
        # Extract body text
        body_text = self._extract_body_text(root)
        if body_text:
            full_text_parts.append(f"Full Text: {body_text}")
        
        return "\n\n".join(full_text_parts)
    
    def _extract_body_text(self, root) -> str:
        """Extract text from the article body."""
        body = root.find(".//body")
        if body is None:
            return ""
        
        paragraphs = []
        for p in body.findall(".//p"):
            if p.text:
                paragraphs.append(p.text.strip())
        
        return " ".join(paragraphs)
    
    def get_full_paper_data(self, pmid: str) -> Dict[str, Any]:
        """
        Retrieve complete paper data including metadata and full text.
        
        Args:
            pmid: PubMed ID of the paper
            
        Returns:
            Dictionary containing complete paper data
        """
        try:
            logger.info(f"Retrieving paper data for PMID: {pmid}")
            
            # Get metadata first
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
    
    def search_papers(self, query: str, max_results: int = 10) -> List[str]:
        """
        Search for papers using a query string.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of PMIDs matching the query
        """
        xml_data = self._make_request("esearch.fcgi", {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "xml"
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

"""
PubMed Full Text Retrieval Service
=================================

This service provides comprehensive PubMed paper retrieval capabilities including
full text extraction from PubMed Central (PMC) when available.
"""

import logging
import asyncio
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from app.services.data_retrieval import PubMedRetriever
from app.utils.config import NCBI_API_KEY

logger = logging.getLogger(__name__)


class PubMedRetrievalService:
    """
    Service for retrieving full paper data from PubMed including metadata and full text.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or NCBI_API_KEY
        self.retriever = PubMedRetriever(api_key=self.api_key)
        self.results_dir = Path("results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
    
    async def retrieve_paper(self, pmid: str, save_to_file: bool = False) -> Dict[str, Any]:
        """
        Retrieve complete paper data including metadata and full text.
        
        Args:
            pmid: PubMed ID of the paper to retrieve
            save_to_file: Whether to save the retrieved data to a file
            
        Returns:
            Dictionary containing complete paper data
        """
        try:
            logger.info(f"Starting paper retrieval for PMID: {pmid}")
            
            # Retrieve full paper data
            paper_data = await self.retriever.get_full_paper_data_async(pmid)
            
            if "error" in paper_data:
                logger.error(f"Failed to retrieve paper data for PMID {pmid}: {paper_data['error']}")
                return paper_data
            
            # Add retrieval metadata
            paper_data.update({
                "retrieval_service": "PubMedRetrievalService",
                "retrieval_timestamp": datetime.now().isoformat(),
                "api_key_used": bool(self.api_key)
            })
            
            # Save to file if requested
            if save_to_file:
                self._save_paper_data(paper_data)
            
            logger.info(f"Successfully retrieved paper data for PMID: {pmid}")
            return paper_data
            
        except Exception as e:
            logger.error(f"Error retrieving paper for PMID {pmid}: {e}")
            return {
                "pmid": pmid,
                "error": f"Retrieval failed: {str(e)}",
                "retrieval_service": "PubMedRetrievalService",
                "retrieval_timestamp": datetime.now().isoformat()
            }
    
    def _save_paper_data(self, paper_data: Dict[str, Any]) -> str:
        """
        Save paper data to a JSON file.
        
        Args:
            paper_data: The paper data to save
            
        Returns:
            Path to the saved file
        """
        try:
            pmid = paper_data.get("pmid", "unknown")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"paper_data_{pmid}_{timestamp}.json"
            filepath = self.results_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(paper_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Paper data saved to: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error saving paper data: {e}")
            return ""
    
    async def retrieve_multiple_papers(self, pmids: List[str], save_to_file: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieve multiple papers concurrently.
        
        Args:
            pmids: List of PubMed IDs to retrieve
            save_to_file: Whether to save each paper's data to a file
            
        Returns:
            List of paper data dictionaries
        """
        try:
            logger.info(f"Starting retrieval of {len(pmids)} papers")
            
            # Retrieve papers concurrently
            tasks = [self.retrieve_paper(pmid, save_to_file) for pmid in pmids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            paper_data_list = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error retrieving PMID {pmids[i]}: {result}")
                    paper_data_list.append({
                        "pmid": pmids[i],
                        "error": f"Retrieval failed: {str(result)}",
                        "retrieval_service": "PubMedRetrievalService",
                        "retrieval_timestamp": datetime.now().isoformat()
                    })
                else:
                    paper_data_list.append(result)
            
            logger.info(f"Completed retrieval of {len(pmids)} papers")
            return paper_data_list
            
        except Exception as e:
            logger.error(f"Error retrieving multiple papers: {e}")
            return []
    
    def format_paper_summary(self, paper_data: Dict[str, Any]) -> str:
        """
        Format paper data into a human-readable summary.
        
        Args:
            paper_data: The paper data to format
            
        Returns:
            Formatted string summary
        """
        if "error" in paper_data:
            return f"❌ Error retrieving PMID {paper_data.get('pmid', 'unknown')}: {paper_data['error']}"
        
        pmid = paper_data.get("pmid", "N/A")
        title = paper_data.get("title", "N/A")
        journal = paper_data.get("journal", "N/A")
        authors = paper_data.get("authors", [])
        publication_date = paper_data.get("publication_date", "N/A")
        has_full_text = paper_data.get("has_full_text", False)
        abstract = paper_data.get("abstract", "")
        full_text = paper_data.get("full_text", "")
        
        # Format authors
        if authors:
            if len(authors) > 3:
                authors_str = f"{', '.join(authors[:3])} et al."
            else:
                authors_str = ", ".join(authors)
        else:
            authors_str = "N/A"
        
        # Format abstract (truncate if too long)
        abstract_preview = abstract[:300] + "..." if len(abstract) > 300 else abstract
        
        # Format full text info
        full_text_info = "✅ Available" if has_full_text else "❌ Not available"
        full_text_preview = ""
        if has_full_text and full_text:
            full_text_preview = full_text[:500] + "..." if len(full_text) > 500 else full_text
        
        summary = f"""
📄 PMID: {pmid}
📝 Title: {title}
📰 Journal: {journal}
👥 Authors: {authors_str}
📅 Publication Date: {publication_date}
📖 Full Text: {full_text_info}

📋 Abstract:
{abstract_preview}

"""
        
        if has_full_text and full_text_preview:
            summary += f"""
📄 Full Text Preview:
{full_text_preview}
"""
        
        return summary.strip()
    
    def get_paper_stats(self, paper_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get statistics about the retrieved paper.
        
        Args:
            paper_data: The paper data to analyze
            
        Returns:
            Dictionary containing paper statistics
        """
        if "error" in paper_data:
            return {"error": "Cannot generate stats for failed retrieval"}
        
        stats = {
            "pmid": paper_data.get("pmid", "N/A"),
            "title_length": len(paper_data.get("title", "")),
            "abstract_length": len(paper_data.get("abstract", "")),
            "full_text_length": len(paper_data.get("full_text", "")),
            "has_full_text": paper_data.get("has_full_text", False),
            "author_count": len(paper_data.get("authors", [])),
            "journal": paper_data.get("journal", "N/A"),
            "publication_date": paper_data.get("publication_date", "N/A"),
            "retrieval_timestamp": paper_data.get("retrieval_timestamp", "N/A")
        }
        
        return stats

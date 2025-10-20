"""
Simplified analysis service focused only on the 6 essential BugSigDB fields.
"""
import logging
from typing import Dict, Optional
import asyncio
import json

from app.models.unified_qa import UnifiedQA
from app.services.data_retrieval import PubMedRetriever
from app.utils.config import DEFAULT_MODEL, GEMINI_API_KEY, NCBI_API_KEY, ANALYSIS_TIMEOUT
from app.api.utils.api_utils import get_current_timestamp

logger = logging.getLogger(__name__)

# Initialize services
unified_qa = UnifiedQA(use_gemini=True, gemini_api_key=GEMINI_API_KEY)
pubmed_retriever = PubMedRetriever(api_key=NCBI_API_KEY)

# The 6 essential BugSigDB fields
ESSENTIAL_FIELDS = {
    "host_species": "What host species is being studied in this research?",
    "body_site": "What body site or anatomical location was sampled for microbiome analysis?", 
    "condition": "What disease, treatment, or condition is being studied?",
    "sequencing_type": "What sequencing method or molecular technique was used?",
    "taxa_level": "What taxonomic level was analyzed (phylum, genus, species, etc.)?",
    "sample_size": "How many samples or participants were included in the study?"
}


async def analyze_paper_simple(pmid: str) -> Optional[Dict]:
    """
    Simple analysis focused only on the 6 essential BugSigDB fields.
    """
    try:
        logger.info(f"Starting simple analysis for PMID: {pmid}")
        
        # Get paper metadata
        texts = await pubmed_retriever.get_texts_for_analysis_async(pmid)
        if not texts.get('title') and not texts.get('abstract'):
            logger.warning(f"No content found for PMID: {pmid}")
            return None
        
        # Prepare text for analysis
        title = texts.get('title', '')
        abstract = texts.get('abstract', '')
        full_text = texts.get('full_text', '')
        
        # Combine text (prioritize abstract, then full text)
        analysis_text = abstract
        if full_text and len(analysis_text) < 1000:
            analysis_text += f"\n\n{full_text[:2000]}"
        
        if not analysis_text.strip():
            logger.warning(f"No analyzable text found for PMID: {pmid}")
            return None
        
        # Analyze each of the 6 essential fields
        field_results = {}
        for field_name, question in ESSENTIAL_FIELDS.items():
            try:
                field_result = await analyze_single_field(analysis_text, field_name, question, pmid)
                field_results[field_name] = field_result
            except Exception as e:
                logger.error(f"Error analyzing field {field_name} for PMID {pmid}: {e}")
                field_results[field_name] = create_empty_field_result(field_name)
        
        # Create final result
        result = {
            "pmid": pmid,
            "title": title,
            "authors": texts.get('authors', []),
            "journal": texts.get('journal', ''),
            "publication_date": texts.get('publication_date', ''),
            "fields": field_results,
            "analysis_timestamp": get_current_timestamp(),
            "model_used": DEFAULT_MODEL
        }
        
        logger.info(f"Simple analysis completed for PMID: {pmid}")
        return result
        
    except Exception as e:
        logger.error(f"Error in simple analysis for PMID {pmid}: {e}")
        return None


async def analyze_single_field(text: str, field_name: str, question: str, pmid: str) -> Dict:
    """
    Analyze a single field using the LLM.
    """
    try:
        prompt = f"""
        Context: {text[:2000]}
        
        Question: {question}
        
        Please provide a specific answer based on the context. If the information is not available, clearly state that.
        
        Respond in this JSON format:
        {{
            "value": "specific answer or null if not found",
            "status": "PRESENT|PARTIALLY_PRESENT|ABSENT",
            "confidence": 0.0-1.0,
            "reason_if_missing": "explanation if absent"
        }}
        """
        
        response = await asyncio.wait_for(
            unified_qa.chat(prompt),
            timeout=ANALYSIS_TIMEOUT
        )
        
        # Parse the response
        answer = response.get('text', '')
        confidence = response.get('confidence', 0.0)
        
        # Try to extract JSON from response
        try:
            # Look for JSON in the response
            json_start = answer.find('{')
            json_end = answer.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = answer[json_start:json_end]
                field_data = json.loads(json_str)
                return {
                    "value": field_data.get("value"),
                    "status": field_data.get("status", "ABSENT"),
                    "confidence": float(field_data.get("confidence", confidence)),
                    "reason_if_missing": field_data.get("reason_if_missing", "")
                }
        except (json.JSONDecodeError, KeyError):
            pass
        
        # Fallback: parse response text
        if not answer or confidence < 0.3:
            return create_empty_field_result(field_name)
        
        # Determine status based on confidence and content
        if confidence >= 0.8 and answer.lower() not in ['not found', 'not available', 'none', 'n/a']:
            status = "PRESENT"
        elif confidence >= 0.4:
            status = "PARTIALLY_PRESENT"
        else:
            status = "ABSENT"
        
        return {
            "value": answer if status != "ABSENT" else None,
            "status": status,
            "confidence": confidence,
            "reason_if_missing": "" if status != "ABSENT" else "Information not found in the paper"
        }
        
    except asyncio.TimeoutError:
        logger.warning(f"Field {field_name} analysis timed out for PMID {pmid}")
        return create_empty_field_result(field_name)
    except Exception as e:
        logger.error(f"Error analyzing field {field_name} for PMID {pmid}: {e}")
        return create_empty_field_result(field_name)


def create_empty_field_result(field_name: str) -> Dict:
    """Create an empty field result for failed analyses."""
    return {
        "value": None,
        "status": "ABSENT",
        "confidence": 0.0,
        "reason_if_missing": "Analysis failed or timed out"
    }

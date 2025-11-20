"""
Paper-QA Agent Integration for BioAnalyzer

This module integrates Paper-QA as an agent for BioAnalyzer, replacing direct
Gemini API calls. Paper-QA supports multiple LLMs including Gemini via litellm.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, Union, List
import asyncio
import json

# Paper-QA imports
try:
    from paperqa import Docs, Settings
    from paperqa.settings import AgentSettings
    from paperqa.agents import agent_query
    from paperqa.agents.models import AnswerResponse
    PAPERQA_AVAILABLE = True
except ImportError as e:
    PAPERQA_AVAILABLE = False
    logging.warning(f"Paper-QA not available: {e}")

from app.utils.config import GEMINI_TIMEOUT

logger = logging.getLogger(__name__)


class PaperQAAgent:
    """
    Paper-QA Agent wrapper for BioAnalyzer.
    
    This class wraps Paper-QA's agent functionality to provide a unified
    interface compatible with the existing BioAnalyzer codebase.
    """
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        model: str = "gemini/gemini-2.0-flash",
        paper_directory: Optional[Path] = None
    ):
        """
        Initialize Paper-QA Agent.
        
        Args:
            api_key: Gemini API key (or set GEMINI_API_KEY env var)
            model: LLM model to use (default: gemini/gemini-2.0-flash)
            paper_directory: Directory to store papers (optional)
        """
        if not PAPERQA_AVAILABLE:
            raise ImportError(
                "Paper-QA is not installed. Please install it: "
                "pip install paper-qa"
            )
        
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self.paper_directory = paper_directory or Path(tempfile.mkdtemp(prefix="paperqa_"))
        self.paper_directory.mkdir(parents=True, exist_ok=True)
        
        if not self.api_key:
            logger.warning("No API key provided. Set GEMINI_API_KEY in your environment.")
        
        # Configure Paper-QA settings with Gemini
        self.settings = Settings(
            llm=self.model,
            summary_llm=self.model,
            agent=AgentSettings(
                agent_llm=self.model,
                agent_type="simple",  # Use simple agent for faster responses
            ),
            paper_directory=str(self.paper_directory),
            # Use Gemini embedding if available, otherwise fallback
            embedding="gemini/text-embedding-004" if self.api_key else None,
        )
        
        # Set API key in environment for litellm
        if self.api_key:
            os.environ["GEMINI_API_KEY"] = self.api_key
        
        logger.info(f"PaperQAAgent initialized with model: {self.model}")
    
    async def chat(self, prompt: str) -> Dict:
        """
        Chat with the Paper-QA agent (simple query without paper context).
        
        Args:
            prompt: The question or prompt
            
        Returns:
            Dict with 'text' and 'confidence' keys
        """
        try:
            # Create empty Docs for simple queries
            docs = Docs()
            
            # Use agent_query for agent-based responses
            response: AnswerResponse = await asyncio.wait_for(
                agent_query(
                    query=prompt,
                    settings=self.settings,
                    docs=docs,
                ),
                timeout=GEMINI_TIMEOUT
            )
            
            answer_text = response.session.answer if hasattr(response.session, 'answer') else str(response)
            confidence = 0.8  # Default confidence for agent responses
            
            return {
                "text": answer_text,
                "confidence": confidence
            }
        except asyncio.TimeoutError:
            logger.error(f"Paper-QA agent query timed out after {GEMINI_TIMEOUT}s")
            return {"text": "Query timed out", "confidence": 0.0}
        except Exception as e:
            logger.error(f"Paper-QA agent query error: {e}")
            return {"text": f"Error: {str(e)}", "confidence": 0.0}
    
    async def analyze_paper(self, paper_content: Dict[str, str]) -> Dict[str, Union[str, float, Dict[str, float]]]:
        """
        Analyze a paper using Paper-QA agent.
        
        Args:
            paper_content: Dict with 'title', 'abstract', and optionally 'full_text'
            
        Returns:
            Analysis results in expected format
        """
        try:
            # Create temporary file with paper content
            title = paper_content.get('title', 'Untitled Paper')
            abstract = paper_content.get('abstract', '')
            full_text = paper_content.get('full_text', '')
            
            # Combine content
            content = f"Title: {title}\n\nAbstract: {abstract}\n\n"
            if full_text:
                content += f"Full Text: {full_text}\n"
            
            # Create temporary markdown file
            temp_file = self.paper_directory / f"paper_{hash(content)}.md"
            temp_file.write_text(content, encoding='utf-8')
            
            # Add to Docs
            docs = Docs()
            await docs.aadd(
                path=str(temp_file),
                citation=title,
                title=title,
                settings=self.settings
            )
            
            # Query the agent about the paper
            query = """You are an expert scientific curator specializing in microbial signature analysis. 
            Analyze this paper and provide a comprehensive assessment of its curation readiness based on 
            the methods and experimental design. Focus on identifying the 6 essential BugSigDB fields:
            1. Host Species
            2. Body Site
            3. Condition
            4. Sequencing Type
            5. Taxa Level
            6. Sample Size
            
            Provide a detailed analysis of what information is present or missing for each field."""
            
            response: AnswerResponse = await asyncio.wait_for(
                agent_query(
                    query=query,
                    settings=self.settings,
                    docs=docs,
                ),
                timeout=GEMINI_TIMEOUT
            )
            
            answer_text = response.session.answer if hasattr(response.session, 'answer') else str(response)
            
            # Parse the response to extract structured information
            # For now, return a simplified structure
            return {
                "analysis": answer_text,
                "confidence": 0.8,
                "key_findings": answer_text,
                "curation_readiness": "UNKNOWN"
            }
            
        except asyncio.TimeoutError:
            logger.error(f"Paper analysis timed out after {GEMINI_TIMEOUT}s")
            return {
                "error": "Analysis timed out",
                "confidence": 0.0,
                "key_findings": "",
                "curation_readiness": "UNKNOWN"
            }
        except Exception as e:
            logger.error(f"Paper analysis error: {e}")
            return {
                "error": str(e),
                "confidence": 0.0,
                "key_findings": "",
                "curation_readiness": "UNKNOWN"
            }
    
    async def analyze_paper_enhanced(self, prompt: str) -> Dict[str, Union[str, float, List[str]]]:
        """
        Enhanced analysis method for BugSigDB curation requirements.
        
        This method uses Paper-QA agent to analyze paper content and extract
        the 6 essential BugSigDB fields with structured output.
        
        Args:
            prompt: The paper content and analysis prompt
            
        Returns:
            Dict with structured analysis results
        """
        try:
            # Extract paper content from prompt if it's in a specific format
            # Otherwise, treat the entire prompt as the paper content
            content = prompt
            
            # Create temporary file
            temp_file = self.paper_directory / f"analysis_{hash(content)}.md"
            temp_file.write_text(content, encoding='utf-8')
            
            # Add to Docs
            docs = Docs()
            await docs.aadd(
                path=str(temp_file),
                citation="Paper Analysis",
                settings=self.settings
            )
            
            # Enhanced query for BugSigDB field extraction
            query = """Analyze this scientific paper and extract information for BugSigDB curation.
            
            Extract the following 6 essential fields:
            1. Host Species - What host organism is being studied?
            2. Body Site - What body site or anatomical location was sampled?
            3. Condition - What disease, treatment, or condition is being studied?
            4. Sequencing Type - What sequencing method was used?
            5. Taxa Level - What taxonomic level was analyzed?
            6. Sample Size - How many samples or participants were included?
            
            For each field, provide:
            - Value: The extracted information or null if not found
            - Status: PRESENT, PARTIALLY_PRESENT, or ABSENT
            - Confidence: A score from 0.0 to 1.0
            - Reason if missing: Explanation if the field is absent
            
            Respond in JSON format with the following structure:
            {
                "host_species": {
                    "value": "...",
                    "status": "PRESENT|PARTIALLY_PRESENT|ABSENT",
                    "confidence": 0.0-1.0,
                    "reason_if_missing": "..."
                },
                "body_site": {...},
                "condition": {...},
                "sequencing_type": {...},
                "taxa_level": {...},
                "sample_size": {...}
            }"""
            
            response: AnswerResponse = await asyncio.wait_for(
                agent_query(
                    query=query,
                    settings=self.settings,
                    docs=docs,
                ),
                timeout=GEMINI_TIMEOUT
            )
            
            answer_text = response.session.answer if hasattr(response.session, 'answer') else str(response)
            
            # Try to parse JSON from response
            try:
                json_start = answer_text.find('{')
                json_end = answer_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_text = answer_text[json_start:json_end]
                    parsed_json = json.loads(json_text)
                    return parsed_json
            except (json.JSONDecodeError, ValueError):
                pass
            
            # Fallback: return the text response
            return {
                "analysis": answer_text,
                "confidence": 0.7,
                "key_findings": answer_text
            }
            
        except asyncio.TimeoutError:
            logger.error(f"Enhanced analysis timed out after {GEMINI_TIMEOUT}s")
            return {
                "error": "Analysis timed out",
                "key_findings": "{}",
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"Enhanced analysis error: {e}")
            return {
                "error": str(e),
                "key_findings": "{}",
                "confidence": 0.0
            }
    
    async def ask_question(self, question: str, context: Optional[str] = None, pmid: Optional[str] = None) -> Dict:
        """
        Ask a question with optional context.
        
        Args:
            question: The question to ask
            context: Optional context (paper content)
            pmid: Optional PMID for tracking
            
        Returns:
            Dict with 'answer', 'confidence', and 'pmid'
        """
        try:
            docs = Docs()
            
            # If context is provided, add it to docs
            if context:
                temp_file = self.paper_directory / f"context_{hash(context)}.md"
                temp_file.write_text(context, encoding='utf-8')
                await docs.aadd(
                    path=str(temp_file),
                    citation=f"Context for PMID {pmid}" if pmid else "Context",
                    settings=self.settings
                )
            
            # Query the agent
            full_query = question
            if context:
                full_query = f"Context: {context[:2000]}\n\nQuestion: {question}"
            
            response: AnswerResponse = await asyncio.wait_for(
                agent_query(
                    query=full_query,
                    settings=self.settings,
                    docs=docs,
                ),
                timeout=GEMINI_TIMEOUT
            )
            
            answer_text = response.session.answer if hasattr(response.session, 'answer') else str(response)
            
            return {
                "answer": answer_text,
                "confidence": 0.8,
                "pmid": pmid
            }
            
        except asyncio.TimeoutError:
            logger.error(f"Question query timed out after {GEMINI_TIMEOUT}s")
            return {
                "answer": "Query timed out",
                "confidence": 0.0,
                "pmid": pmid
            }
        except Exception as e:
            logger.error(f"Question query error: {e}")
            return {
                "answer": f"Error: {str(e)}",
                "confidence": 0.0,
                "pmid": pmid
            }


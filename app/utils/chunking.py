"""
Chunking Utilities for BioAnalyzer

Uses Paper-QA's chunking functions for text processing.
"""
import logging
from typing import Optional

from paperqa.readers import chunk_text, chunk_pdf
from paperqa.types import Doc, Text, ParsedText

logger = logging.getLogger(__name__)


class ChunkingService:
    """
    Text chunking service using Paper-QA's chunking strategies.
    """
    
    def __init__(
        self,
        chunk_chars: int = 3000,
        overlap: int = 100
    ):
        """
        Initialize the chunking service.
        
        Args:
            chunk_chars: Size of each chunk in characters
            overlap: Overlap between chunks in characters
        """
        self.chunk_chars = chunk_chars
        self.overlap = overlap
    
    async def chunk_markdown(
        self,
        markdown: str,
        doc_name: str = "study",
        doc_key: Optional[str] = None
    ) -> list[Text]:
        """
        Chunk markdown text into Text objects.
        
        Args:
            markdown: Markdown content
            doc_name: Name of the document
            doc_key: Unique key for the document
            
        Returns:
            List of Text objects
        """
        logger.info(
            f"Chunking markdown: {len(markdown)} chars "
            f"(chunk_size={self.chunk_chars}, overlap={self.overlap})"
        )
        
        # Create Doc object
        doc = Doc(
            docname=doc_name,
            dockey=doc_key or doc_name,
            citation=f"{doc_name} - BioAnalyzer Study Analysis"
        )
        
        # Create ParsedText
        from paperqa.types import ParsedMetadata
        parsed_text = ParsedText(
            content=markdown,
            metadata=ParsedMetadata(
                parsing_libraries=["html2text"],
                paperqa_version="5.0.0",
                total_parsed_text_length=len(markdown),
                name="markdown"
            )
        )
        
        # Chunk using Paper-QA's chunk_text function
        chunks = chunk_text(
            parsed_text=parsed_text,
            doc=doc,
            chunk_chars=self.chunk_chars,
            overlap=self.overlap,
            use_tiktoken=True
        )
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks
    
    def get_chunk_stats(self, chunks: list[Text]) -> dict:
        """Get statistics about chunks."""
        if not chunks:
            return {
                "num_chunks": 0,
                "avg_length": 0,
                "min_length": 0,
                "max_length": 0
            }
        
        lengths = [len(chunk.text) for chunk in chunks]
        
        return {
            "num_chunks": len(chunks),
            "avg_length": sum(lengths) / len(lengths),
            "min_length": min(lengths),
            "max_length": max(lengths),
            "total_chars": sum(lengths)
        }

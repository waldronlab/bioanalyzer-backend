"""
Converter Service for BioAnalyzer

Converts downloaded files to markdown and merges with image descriptions.
Uses Paper-QA's parsing functions for file conversion.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from paperqa.readers import parse_text, chunk_text
from paperqa.types import Doc, ParsedMedia, ParsedText

logger = logging.getLogger(__name__)


class ConverterService:
    """
    File converter service that merges study content with image descriptions.
    
    Uses Paper-QA's parsing functions to convert various file formats
    to markdown and combines everything into a single enhanced document.
    """
    
    def __init__(self):
        """Initialize the converter service."""
        pass
    
    async def create_enhanced_markdown(
        self,
        base_markdown: str,
        image_descriptions: list[dict],
        downloaded_files: list[dict],
        source_url: str
    ) -> str:
        """
        Create enhanced markdown by merging base content with images and files.
        
        Args:
            base_markdown: Base markdown from web scraping
            image_descriptions: List of dicts with 'url' and 'description'
            downloaded_files: List of dicts with file info
            source_url: Original source URL
            
        Returns:
            Enhanced markdown string
        """
        logger.info("Creating enhanced markdown document")
        
        # Start with header
        enhanced = f"# Study Analysis\n\n"
        enhanced += f"**Source:** {source_url}\n\n"
        enhanced += "---\n\n"
        
        # Add base content
        enhanced += "## Main Content\n\n"
        enhanced += base_markdown
        enhanced += "\n\n---\n\n"
        
        # Add image descriptions
        if image_descriptions:
            enhanced += "## Figure Descriptions\n\n"
            for i, img_desc in enumerate(image_descriptions, 1):
                enhanced += f"### Figure {i}\n\n"
                enhanced += f"**Source:** {img_desc.get('url', 'Unknown')}\n\n"
                enhanced += img_desc.get('description', 'No description available')
                enhanced += "\n\n"
            enhanced += "---\n\n"
        
        # Add supplementary files
        if downloaded_files:
            enhanced += "## Supplementary Materials\n\n"
            
            for file_info in downloaded_files:
                file_path = Path(file_info['path'])
                file_type = file_info.get('type', file_path.suffix)
                
                enhanced += f"### {file_info.get('filename', file_path.name)}\n\n"
                enhanced += f"- **Type:** {file_type}\n"
                enhanced += f"- **Size:** {file_info.get('size', 0) / 1024:.2f} KB\n"
                enhanced += f"- **Source:** {file_info.get('url', 'Unknown')}\n\n"
                
                # Try to extract content from file
                file_content = await self._extract_file_content(file_path)
                if file_content:
                    enhanced += "**Content:**\n\n"
                    enhanced += file_content
                    enhanced += "\n\n"
            
            enhanced += "---\n\n"
        
        logger.info(
            f"Enhanced markdown created: {len(enhanced)} chars, "
            f"{len(image_descriptions)} images, {len(downloaded_files)} files"
        )
        
        return enhanced
    
    async def _extract_file_content(self, file_path: Path) -> Optional[str]:
        """
        Extract content from a file using Paper-QA's parsing functions.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Extracted content as markdown string or None
        """
        try:
            suffix = file_path.suffix.lower()
            
            # Text files
            if suffix in ['.txt', '.md', '.csv']:
                parsed_text = await asyncio.to_thread(
                    parse_text,
                    file_path,
                    html=False
                )
                return self._format_parsed_text(parsed_text)
            
            # HTML files
            elif suffix in ['.html', '.htm']:
                parsed_text = await asyncio.to_thread(
                    parse_text,
                    file_path,
                    html=True
                )
                return self._format_parsed_text(parsed_text)
            
            # PDF files would require parse_pdf which needs a parser function
            # For now, we'll skip PDFs or add a note
            elif suffix == '.pdf':
                return "_PDF file - content extraction requires PDF parser_\n"
            
            # Binary files
            else:
                return f"_Binary file ({suffix}) - content not extracted_\n"
                
        except Exception as e:
            logger.warning(f"Could not extract content from {file_path}: {e}")
            return None
    
    def _format_parsed_text(self, parsed_text: ParsedText) -> str:
        """Format ParsedText content to string."""
        if isinstance(parsed_text.content, str):
            return parsed_text.content
        elif isinstance(parsed_text.content, list):
            return "\n".join(parsed_text.content)
        elif isinstance(parsed_text.content, dict):
            # For dict content, join all values
            parts = []
            for value in parsed_text.content.values():
                if isinstance(value, str):
                    parts.append(value)
                elif isinstance(value, tuple):
                    # (text, media) tuple
                    parts.append(value[0])
            return "\n\n".join(parts)
        else:
            return str(parsed_text.content)
    
    def save_markdown(self, markdown: str, output_path: str | Path) -> Path:
        """
        Save markdown to file.
        
        Args:
            markdown: Markdown content
            output_path: Output file path
            
        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_path.write_text(markdown, encoding='utf-8')
        logger.info(f"Saved markdown to {output_path}")
        
        return output_path

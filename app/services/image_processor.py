"""
Image Processor Service for BioAnalyzer

Uses Paper-QA's ParsedMedia pattern for image handling and visual LLM integration.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional

import aiohttp
from paperqa.types import ParsedMedia
from paperqa.readers import parse_image
from lmi.utils import encode_image_as_url

logger = logging.getLogger(__name__)


class ImageProcessorService:
    """
    Image processor using Paper-QA's ParsedMedia pattern.
    
    Handles image downloading, validation, and conversion to formats
    suitable for visual LLM processing.
    """
    
    def __init__(
        self,
        cache_dir: str = "cache/images",
        max_image_size_mb: int = 10
    ):
        """
        Initialize the image processor.
        
        Args:
            cache_dir: Directory to cache downloaded images
            max_image_size_mb: Maximum image size in MB
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_image_size = max_image_size_mb * 1024 * 1024
    
    async def process_image_url(
        self,
        image_url: str,
        index: int = 0
    ) -> Optional[ParsedMedia]:
        """
        Download and process an image URL into ParsedMedia format.
        
        Args:
            image_url: URL of the image
            index: Index of the image (for ordering)
            
        Returns:
            ParsedMedia object or None if processing fails
        """
        try:
            logger.info(f"Processing image: {image_url}")
            
            # Download image
            image_path = await self._download_image(image_url)
            if not image_path:
                return None
            
            # Parse using Paper-QA's parse_image function
            parsed_text = await parse_image(image_path)
            
            # Extract ParsedMedia from ParsedText
            # ParsedText.content is dict[str, tuple[str, list[ParsedMedia]]]
            if isinstance(parsed_text.content, dict):
                for page_content in parsed_text.content.values():
                    if isinstance(page_content, tuple) and len(page_content) > 1:
                        media_list = page_content[1]
                        if media_list:
                            parsed_media = media_list[0]
                            # Update index and add source URL to info
                            parsed_media.index = index
                            parsed_media.info["source_url"] = image_url
                            return parsed_media
            
            logger.warning(f"Could not extract ParsedMedia from {image_url}")
            return None
            
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {e}")
            return None
    
    async def _download_image(self, image_url: str) -> Optional[Path]:
        """Download image from URL to cache directory."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=30) as response:
                    response.raise_for_status()
                    
                    # Check size
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > self.max_image_size:
                        logger.warning(
                            f"Skipping {image_url}: image too large "
                            f"({int(content_length) / 1024 / 1024:.2f} MB)"
                        )
                        return None
                    
                    # Generate filename from URL
                    import hashlib
                    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:16]
                    
                    # Get extension from URL or content-type
                    extension = self._get_image_extension(
                        image_url,
                        response.headers.get('content-type', '')
                    )
                    
                    filename = f"{url_hash}{extension}"
                    image_path = self.cache_dir / filename
                    
                    # Download if not cached
                    if not image_path.exists():
                        content = await response.read()
                        image_path.write_bytes(content)
                        logger.info(f"Downloaded image: {filename}")
                    else:
                        logger.info(f"Using cached image: {filename}")
                    
                    return image_path
                    
        except Exception as e:
            logger.error(f"Error downloading image {image_url}: {e}")
            return None
    
    def _get_image_extension(self, url: str, content_type: str) -> str:
        """Determine image extension from URL or content-type."""
        # Try URL first
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']:
            if path.endswith(ext):
                return ext
        
        # Try content-type
        content_type_map = {
            'image/png': '.png',
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/gif': '.gif',
            'image/svg+xml': '.svg',
            'image/webp': '.webp'
        }
        
        return content_type_map.get(content_type.lower(), '.png')
    
    def get_image_url_for_llm(self, parsed_media: ParsedMedia) -> str:
        """
        Convert ParsedMedia to image URL for visual LLM.
        
        Uses Paper-QA's to_image_url() method which creates
        RFC 2397 data URL format.
        
        Args:
            parsed_media: ParsedMedia object
            
        Returns:
            Data URL string suitable for visual LLM input
        """
        return parsed_media.to_image_url()
    
    async def describe_image_with_llm(
        self,
        parsed_media: ParsedMedia,
        llm_service,
        prompt: Optional[str] = None
    ) -> str:
        """
        Generate description of image using visual LLM.
        
        Args:
            parsed_media: ParsedMedia object
            llm_service: LLM service with visual capabilities
            prompt: Optional custom prompt
            
        Returns:
            Image description text
        """
        if prompt is None:
            prompt = (
                "Describe this scientific figure or image in detail. "
                "Focus on:\n"
                "1. What type of figure it is (graph, diagram, microscopy, etc.)\n"
                "2. Key visual elements and data shown\n"
                "3. Any labels, legends, or annotations\n"
                "4. Scientific findings or patterns visible\n"
                "5. Experimental methods or conditions shown"
            )
        
        # Get image URL for LLM
        image_url = self.get_image_url_for_llm(parsed_media)
        
        # Call LLM with image
        try:
            description = await llm_service.analyze_image(image_url, prompt)
            
            # Store description in ParsedMedia info
            parsed_media.info["enriched_description"] = description
            
            logger.info(
                f"Generated description for image {parsed_media.index}: "
                f"{len(description)} chars"
            )
            
            return description
            
        except Exception as e:
            logger.error(f"Error describing image: {e}")
            return ""
    
    def cleanup_cache(self):
        """Clean up cached images."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            logger.info(f"Cleaned up image cache: {self.cache_dir}")

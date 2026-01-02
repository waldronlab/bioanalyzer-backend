"""Image processor service for downloading and converting images for visual LLM processing."""

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ProcessedImage:
    """Lightweight representation of a downloaded image."""

    path: Path
    index: int
    source_url: str
    mime_type: str = "image/png"
    info: dict = field(default_factory=dict)

    def to_image_url(self) -> str:
        """Return a RFC 2397 data URL for use with visual LLMs."""
        data = self.path.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{self.mime_type};base64,{encoded}"


class ImageProcessorService:
    """Image processor for downloading and caching images for visual LLM processing."""

    def __init__(self, cache_dir: str = "cache/images", max_image_size_mb: int = 10):
        """Initialize image processor."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_image_size = max_image_size_mb * 1024 * 1024

    async def process_image_url(self, image_url: str, index: int = 0) -> Optional[ProcessedImage]:
        """Download image URL and prepare for processing."""
        try:
            logger.info("Processing image: %s", image_url)
            download = await self._download_image(image_url)
            if not download:
                return None

            image_path, mime_type = download
            processed = ProcessedImage(
                path=image_path, index=index, source_url=image_url, mime_type=mime_type or "image/png"
            )
            processed.info["source_url"] = image_url
            return processed

        except Exception as exc:
            logger.error("Error processing image %s: %s", image_url, exc)
            return None

    async def _download_image(self, image_url: str) -> Optional[tuple[Path, str]]:
        """Download image from URL to cache directory."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=30) as response:
                    response.raise_for_status()

                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self.max_image_size:
                        logger.warning(
                            "Skipping %s: image too large (%.2f MB)", image_url, int(content_length) / 1024 / 1024
                        )
                        return None

                    import hashlib

                    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:16]
                    mime_type = response.headers.get("content-type", "").lower()
                    extension = self._get_image_extension(image_url, mime_type)

                    filename = f"{url_hash}{extension}"
                    image_path = self.cache_dir / filename

                    if not image_path.exists():
                        content = await response.read()
                        image_path.write_bytes(content)
                        logger.info("Downloaded image: %s", filename)
                    else:
                        logger.info("Using cached image: %s", filename)

                    return image_path, self._infer_mime_type(extension, mime_type)

        except Exception as exc:
            logger.error("Error downloading image %s: %s", image_url, exc)
            return None

    def _infer_mime_type(self, extension: str, fallback: str) -> str:
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }
        if extension in mapping:
            return mapping[extension]
        return fallback or "image/png"

    def _get_image_extension(self, url: str, content_type: str) -> str:
        """Determine image extension from URL or content-type."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.lower()

        for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]:
            if path.endswith(ext):
                return ext

        content_type_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            "image/webp": ".webp",
        }

        return content_type_map.get(content_type.lower(), ".png")

    def get_image_url_for_llm(self, parsed_media: ProcessedImage) -> str:
        """Return a data URL suitable for visual LLM input."""
        return parsed_media.to_image_url()

    async def describe_image_with_llm(
        self, parsed_media: ProcessedImage, llm_service, prompt: Optional[str] = None
    ) -> str:
        """
        Generate description of image using a visual LLM.
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

        image_url = self.get_image_url_for_llm(parsed_media)

        try:
            description = await llm_service.analyze_image(image_url, prompt)
            parsed_media.info["enriched_description"] = description
            logger.info("Generated description for image %s (%d chars)", parsed_media.index, len(description))
            return description

        except Exception as exc:
            logger.error("Error describing image: %s", exc)
            return ""

    def cleanup_cache(self):
        """Clean up cached images."""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            logger.info("Cleaned up image cache: %s", self.cache_dir)

"""Web scraper service using html2text for converting web pages to markdown."""

import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import requests
from bs4 import BeautifulSoup
from html2text import html2text

logger = logging.getLogger(__name__)


class WebScraperService:
    """Web scraper service that converts web pages to markdown."""

    def __init__(
        self,
        download_dir: str = "downloads",
        max_file_size_mb: int = 50,
        timeout: int = 30,
    ):
        """Initialize web scraper."""
        self.download_dir = self._ensure_writable_directory(download_dir)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.timeout = timeout

        self.downloadable_extensions = {
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".xlsx",
            ".xls",
            ".csv",
            ".zip",
            ".tar",
            ".gz",
        }

        self.image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".svg"}

    def _ensure_writable_directory(self, download_dir: str) -> Path:
        """
        Ensure the download directory exists and is writable.
        
        If the specified directory cannot be created or is not writable,
        falls back to a temporary directory.
        
        Args:
            download_dir: Desired download directory path
            
        Returns:
            Path to a writable download directory
        """
        download_path = Path(download_dir)
        
        try:
            # Try to create the directory if it doesn't exist
            if not download_path.exists():
                download_path.mkdir(parents=True, exist_ok=True)
            
            # Check if the directory is writable by trying to create a test file
            test_file = download_path / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()  # Clean up test file
                logger.info(f"Using download directory: {download_path.absolute()}")
                return download_path
            except (OSError, PermissionError) as e:
                logger.warning(
                    f"Download directory '{download_path}' is not writable: {e}. "
                    f"Falling back to temporary directory."
                )
        except (OSError, PermissionError) as e:
            logger.warning(
                f"Cannot create download directory '{download_path}': {e}. "
                f"Falling back to temporary directory."
            )
        
        # Fall back to a temporary directory
        temp_dir = Path(tempfile.gettempdir()) / "bioanalyzer_downloads"
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using temporary download directory: {temp_dir.absolute()}")
            return temp_dir
        except Exception as e:
            # Last resort: use system temp directory directly
            logger.error(
                f"Cannot create temporary download directory: {e}. "
                f"Using system temp directory."
            )
            return Path(tempfile.gettempdir())

    async def scrape_url_to_markdown(self, url: str) -> dict:
        """Scrape URL and convert to markdown."""
        try:
            logger.info(f"Scraping URL: {url}")

            html_content = await self._fetch_html(url)
            soup = BeautifulSoup(html_content, "html.parser")

            # Extract links before conversion
            links = self._extract_links(soup, url)

            # Convert to markdown using html2text (Paper-QA pattern)
            markdown = html2text(html_content)

            # Extract and categorize links
            image_urls = [link for link in links if self._is_image_url(link)]
            file_urls = [link for link in links if self._is_downloadable_file(link)]

            # Download files
            downloaded_files = await self._download_files(file_urls, url)

            logger.info(
                f"Scraping complete: {len(markdown)} chars, "
                f"{len(image_urls)} images, {len(downloaded_files)} files"
            )

            return {
                "markdown": markdown,
                "images": image_urls,
                "files": downloaded_files,
                "links": links,
                "source_url": url,
            }

        except Exception as e:
            logger.error(f"Error scraping URL {url}: {e}")
            raise

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML content from URL."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=self.timeout) as response:
                response.raise_for_status()
                return await response.text()

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Extract all links from HTML."""
        links = []

        # Extract from <a> tags
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)

        # Extract from <img> tags
        for tag in soup.find_all("img", src=True):
            src = tag["src"]
            absolute_url = urljoin(base_url, src)
            links.append(absolute_url)

        # Extract from <link> tags (stylesheets, etc.)
        for tag in soup.find_all("link", href=True):
            href = tag["href"]
            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)

        return list(set(links))

    def _is_image_url(self, url: str) -> bool:
        """Check if URL points to an image."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in self.image_extensions)

    def _is_downloadable_file(self, url: str) -> bool:
        """Check if URL points to a downloadable file."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        return any(path.endswith(ext) for ext in self.downloadable_extensions)

    async def _download_files(self, file_urls: list[str], base_url: str) -> list[dict]:
        """
        Download files from URLs.

        Returns:
            List of dictionaries with file info:
                - url: Original URL
                - path: Local file path
                - size: File size in bytes
                - type: File extension
        """
        downloaded = []

        async with aiohttp.ClientSession() as session:
            for url in file_urls:
                try:
                    downloaded_file = await self._download_single_file(
                        session, url, base_url
                    )
                    if downloaded_file:
                        downloaded.append(downloaded_file)
                except Exception as e:
                    logger.warning(f"Failed to download {url}: {e}")
                    continue

        return downloaded

    async def _download_single_file(
        self, session: aiohttp.ClientSession, url: str, base_url: str
    ) -> Optional[dict]:
        """Download a single file."""
        try:
            async with session.get(url, timeout=self.timeout) as response:
                response.raise_for_status()

                # Check file size
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.max_file_size:
                    logger.warning(
                        f"Skipping {url}: file too large "
                        f"({int(content_length) / 1024 / 1024:.2f} MB)"
                    )
                    return None

                # Generate filename
                filename = self._generate_filename(url)
                file_path = self.download_dir / filename

                # Ensure parent directory exists and is writable
                try:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                except (OSError, PermissionError) as e:
                    logger.error(
                        f"Cannot create directory for {filename}: {e}. "
                        f"Download directory may not be writable."
                    )
                    return None

                # Download file
                content = await response.read()
                try:
                    file_path.write_bytes(content)
                except (OSError, PermissionError) as e:
                    logger.error(
                        f"Cannot write file {filename}: {e}. "
                        f"Download directory may not be writable."
                    )
                    return None

                logger.info(f"Downloaded: {filename} ({len(content)} bytes)")

                return {
                    "url": url,
                    "path": str(file_path),
                    "size": len(content),
                    "type": file_path.suffix,
                    "filename": filename,
                }

        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return None

    def _generate_filename(self, url: str) -> str:
        """Generate a safe filename from URL."""
        parsed = urlparse(url)
        path = parsed.path

        filename = Path(path).name

        if not filename or "." not in filename:
            # Use hash of URL as filename
            import hashlib

            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            filename = f"file_{url_hash}.bin"

        # Sanitize filename
        filename = re.sub(r"[^\w\-_\.]", "_", filename)

        return filename

    def cleanup_downloads(self):
        """Clean up downloaded files."""
        import shutil

        if not self.download_dir.exists():
            return

        # Don't delete the system temp directory itself, only our subdirectory
        system_temp = Path(tempfile.gettempdir())
        if self.download_dir == system_temp:
            logger.warning(
                "Skipping cleanup: download directory is system temp directory. "
                "Individual files will be cleaned up by the system."
            )
            return

        try:
            # Only delete files in the directory, not the directory itself if it's a shared temp dir
            if "bioanalyzer_downloads" in str(self.download_dir):
                # It's our temp directory, safe to delete
                shutil.rmtree(self.download_dir)
                logger.info(f"Cleaned up download directory: {self.download_dir}")
            else:
                # It's a custom directory, just clean up files
                for file_path in self.download_dir.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                logger.info(f"Cleaned up files in download directory: {self.download_dir}")
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not clean up download directory {self.download_dir}: {e}")

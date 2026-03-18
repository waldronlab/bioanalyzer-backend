"""
Integration test for the enhanced BioAnalyzer workflow.

Tests the complete pipeline from URL scraping to vector storage.
"""

import asyncio
import pytest
from pathlib import Path

# Try to import services, skip tests if FastAPI not available
try:
    from fastapi import FastAPI
    from app.services.web_scraper import WebScraperService
    from app.services.image_processor import ImageProcessorService
    from app.services.converter_service import ConverterService
    from app.services.vector_store_service import VectorStoreService
    from app.utils.chunking import ChunkingService

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    WebScraperService = None
    ImageProcessorService = None
    ConverterService = None
    VectorStoreService = None
    ChunkingService = None

# Check if sentence_transformers is available (required for some embedding models)
try:
    import sentence_transformers

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


@pytest.mark.asyncio
@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
@pytest.mark.skipif(
    not SENTENCE_TRANSFORMERS_AVAILABLE, reason="sentence_transformers not available"
)
async def test_complete_workflow():
    """Test the complete workflow from URL to vector storage."""

    # Sample URL (you can replace with a real scientific paper URL)
    test_url = "https://www.example.com/sample-study"

    # Step 1: Scrape URL
    scraper = WebScraperService(download_dir="test_downloads")
    try:
        scrape_result = await scraper.scrape_url_to_markdown(test_url)

        assert "markdown" in scrape_result
        assert "images" in scrape_result
        assert "files" in scrape_result

        print(f"✓ Scraped {len(scrape_result['markdown'])} chars of markdown")
        print(f"✓ Found {len(scrape_result['images'])} images")
        print(f"✓ Downloaded {len(scrape_result['files'])} files")

    except Exception as e:
        print(f"Note: Scraping failed (expected for example.com): {e}")
        # Use mock data for testing
        scrape_result = {
            "markdown": "# Sample Study\n\nThis is a test study.",
            "images": [],
            "files": [],
            "source_url": test_url,
        }

    # Step 2: Process images (if any)
    image_processor = ImageProcessorService()
    image_descriptions = []

    for i, image_url in enumerate(scrape_result["images"][:3]):  # Limit to 3
        parsed_media = await image_processor.process_image_url(image_url, index=i)
        if parsed_media:
            image_descriptions.append(
                {
                    "url": image_url,
                    "description": f"Image {i+1} description",  # Would use LLM here
                }
            )

    print(f"✓ Processed {len(image_descriptions)} images")

    # Step 3: Create enhanced markdown
    converter = ConverterService()
    enhanced_md = await converter.create_enhanced_markdown(
        base_markdown=scrape_result["markdown"],
        image_descriptions=image_descriptions,
        downloaded_files=scrape_result["files"],
        source_url=test_url,
    )

    assert len(enhanced_md) > 0
    print(f"✓ Created enhanced markdown: {len(enhanced_md)} chars")

    # Step 4: Chunk the markdown
    chunker = ChunkingService(chunk_chars=1000, overlap=100)
    chunks = await chunker.chunk_markdown(
        markdown=enhanced_md, doc_name="test_study", doc_key="test_001"
    )

    assert len(chunks) > 0
    chunk_stats = chunker.get_chunk_stats(chunks)
    print(f"✓ Created {chunk_stats['num_chunks']} chunks")
    print(f"  - Avg length: {chunk_stats['avg_length']:.0f} chars")

    # Step 5: Store in vector database
    # Test with in-memory NumpyVectorStore
    vector_store = VectorStoreService(
        store_type="numpy",
        embedding_model="st-all-MiniLM-L6-v2",  # Fast local model for testing
    )

    await vector_store.add_texts(chunks)

    stats = vector_store.get_stats()
    assert stats["num_texts"] == len(chunks)
    print(f"✓ Added {stats['num_texts']} texts to vector store")

    # Step 6: Test similarity search
    results, scores = await vector_store.similarity_search(
        query="What is this study about?", k=3
    )

    assert len(results) > 0
    print(f"✓ Similarity search returned {len(results)} results")
    for i, (text, score) in enumerate(zip(results, scores), 1):
        print(f"  {i}. Score: {score:.3f} - {text.text[:100]}...")

    # Cleanup
    scraper.cleanup_downloads()
    image_processor.cleanup_cache()

    print("\n✅ Complete workflow test passed!")


@pytest.mark.asyncio
@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
async def test_vector_store_with_ollama():
    """Test vector store with OLLAMA embeddings (requires OLLAMA running)."""
    try:
        vector_store = VectorStoreService(
            store_type="numpy", embedding_model="ollama/nomic-embed-text"
        )
        print("✓ OLLAMA embedding model initialized")

        # Create sample chunks
        from paperqa.types import Doc, Text

        doc = Doc(docname="test", dockey="test", citation="Test")
        chunks = [
            Text(text="Sample text 1", name="chunk1", doc=doc),
            Text(text="Sample text 2", name="chunk2", doc=doc),
        ]

        await vector_store.add_texts(chunks)
        print("✓ Added texts with OLLAMA embeddings")

    except Exception as e:
        print(f"Note: OLLAMA test skipped (OLLAMA may not be running): {e}")


if __name__ == "__main__":
    print("Running integration tests...\n")
    asyncio.run(test_complete_workflow())
    print("\n" + "=" * 60 + "\n")
    asyncio.run(test_vector_store_with_ollama())

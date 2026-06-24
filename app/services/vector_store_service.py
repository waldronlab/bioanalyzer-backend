"""Vector store service using Paper-QA's implementations."""

import asyncio
import logging
from typing import Optional

from paperqa.llms import NumpyVectorStore, embedding_model_factory

try:
    # Optional in some paper-qa versions; tests patch this symbol directly.
    from paperqa.llms import QdrantVectorStore  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - handled via runtime fallback
    QdrantVectorStore = None  # type: ignore[assignment]

from paperqa.types import Text

logger = logging.getLogger(__name__)


async def _get_embeddable_text(text: Text) -> str:
    """Get text content for embedding; use get_embeddable_text if available else text.text."""
    getter = getattr(text, "get_embeddable_text", None)
    if callable(getter):
        result = getter(with_enrichment=True)
        if asyncio.iscoroutine(result):
            return await result
        return result
    return text.text


class VectorStoreService:
    """Vector store service using Paper-QA's implementations."""

    def __init__(
        self,
        store_type: str = "numpy",
        collection_name: str = "bioanalyzer_studies",
        qdrant_path: Optional[str] = None,
        embedding_model: str = "gemini/text-embedding-004",
    ):
        """Initialize vector store service."""
        self.store_type = store_type.lower()
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model

        self.embedding_model = embedding_model_factory(embedding_model)
        logger.info(f"Initialized embedding model: {embedding_model}")

        if self.store_type == "numpy":
            self.vector_store = NumpyVectorStore()
            logger.info("Using NumpyVectorStore (in-memory)")
        elif self.store_type == "qdrant":
            if QdrantVectorStore is None:
                logger.warning(
                    "QdrantVectorStore not available in this paper-qa version; "
                    "falling back to NumpyVectorStore"
                )
                self.vector_store = NumpyVectorStore()
            else:
                try:
                    from qdrant_client import AsyncQdrantClient

                    if qdrant_path:
                        client = AsyncQdrantClient(path=qdrant_path)
                    else:
                        client = AsyncQdrantClient(location=":memory:")

                    self.vector_store = QdrantVectorStore(
                        client=client, collection_name=collection_name
                    )
                    logger.info(f"Using QdrantVectorStore: {collection_name}")
                except ImportError:
                    logger.warning(
                        "qdrant-client not installed, falling back to NumpyVectorStore"
                    )
                    self.vector_store = NumpyVectorStore()
        else:
            raise ValueError(f"Unknown store_type: {store_type}")

    async def add_texts(self, texts: list[Text]) -> None:
        """
        Add text chunks to the vector store.

        Args:
            texts: List of Text objects (from Paper-QA)
        """
        logger.info(f"Adding {len(texts)} texts to vector store")

        # Generate embeddings for texts that don't have them
        texts_to_embed = [t for t in texts if t.embedding is None]

        if texts_to_embed:
            # Get embeddable text (use get_embeddable_text if available, else text.text)
            embeddable_texts = []
            for text in texts_to_embed:
                embeddable_text = await _get_embeddable_text(text)
                embeddable_texts.append(embeddable_text)

            # Generate embeddings
            embeddings = await self.embedding_model.embed_documents(embeddable_texts)

            # Assign embeddings to texts
            for text, embedding in zip(texts_to_embed, embeddings):
                text.embedding = embedding

        # Add to vector store
        await self.vector_store.add_texts_and_embeddings(texts)

        logger.info(f"Successfully added {len(texts)} texts to vector store")

    async def similarity_search(
        self, query: str, k: int = 5
    ) -> tuple[list[Text], list[float]]:
        """
        Search for similar texts.

        Args:
            query: Query string
            k: Number of results to return

        Returns:
            Tuple of (texts, scores)
        """
        logger.info(f"Searching for: {query} (k={k})")

        texts, scores = await self.vector_store.similarity_search(
            query=query, k=k, embedding_model=self.embedding_model
        )

        logger.info(f"Found {len(texts)} results")
        return texts, scores

    async def mmr_search(
        self, query: str, k: int = 5, fetch_k: int = 20
    ) -> tuple[list[Text], list[float]]:
        """
        Maximal Marginal Relevance search for diverse results.

        Args:
            query: Query string
            k: Number of results to return
            fetch_k: Number of results to fetch before MMR

        Returns:
            Tuple of (texts, scores)
        """
        logger.info(f"MMR search for: {query} (k={k}, fetch_k={fetch_k})")

        texts, scores = await self.vector_store.max_marginal_relevance_search(
            query=query, k=k, fetch_k=fetch_k, embedding_model=self.embedding_model
        )

        logger.info(f"Found {len(texts)} diverse results")
        return texts, scores

    def clear(self) -> None:
        """Clear all data from the vector store."""
        self.vector_store.clear()
        logger.info("Vector store cleared")

    def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        return {
            "type": self.store_type,
            "collection_name": self.collection_name,
            "embedding_model": self.embedding_model_name,
            "num_texts": len(self.vector_store),
        }

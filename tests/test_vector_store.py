"""
Tests for Vector Store Service and Embedding Generation.

Tests embedding generation and vector store operations.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import numpy as np

from app.services.vector_store_service import VectorStoreService
from paperqa.types import Text


@pytest.fixture
def sample_texts():
    """Create sample Text objects for testing."""
    from paperqa.types import Doc
    
    test_doc = Doc(
        docname="test_paper",
        dockey="test_key",
        citation="Test Paper Citation"
    )
    return [
        Text(
            text="This study examined the gut microbiome in human participants.",
            name="text_1",
            doc=test_doc,
        ),
        Text(
            text="The host species was identified as Homo sapiens.",
            name="text_2",
            doc=test_doc,
        ),
        Text(
            text="Samples were collected from the gastrointestinal tract.",
            name="text_3",
            doc=test_doc,
        ),
    ]


@pytest.fixture
def mock_embedding_model():
    """Create a mock embedding model."""
    mock = Mock()
    mock.embed_documents = AsyncMock(
        return_value=[
            np.random.rand(768).tolist(),
            np.random.rand(768).tolist(),
            np.random.rand(768).tolist(),
        ]
    )
    mock.embed_query = AsyncMock(return_value=np.random.rand(768).tolist())
    return mock


@pytest.fixture
def mock_vector_store():
    """Create a mock vector store."""
    mock = Mock()
    mock.add_texts_and_embeddings = AsyncMock(return_value=None)
    mock.similarity_search = AsyncMock(return_value=([], []))
    mock.max_marginal_relevance_search = AsyncMock(return_value=([], []))
    return mock


class TestVectorStoreService:
    """Test VectorStoreService."""

    def test_initialization_numpy(self, mock_embedding_model):
        """Test initialization with numpy vector store."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = mock_embedding_model
            mock_numpy.return_value = Mock()

            service = VectorStoreService(
                store_type="numpy", embedding_model="gemini/text-embedding-004"
            )

            assert service.store_type == "numpy"
            assert service.embedding_model is not None

    def test_initialization_qdrant(self, mock_embedding_model):
        """Test initialization with Qdrant vector store."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.QdrantVectorStore"
        ) as mock_qdrant:
            mock_factory.return_value = mock_embedding_model
            mock_qdrant.return_value = Mock()

            service = VectorStoreService(
                store_type="qdrant",
                embedding_model="gemini/text-embedding-004",
                qdrant_path="/tmp/qdrant",
            )

            assert service.store_type == "qdrant"

    @pytest.mark.asyncio
    async def test_add_texts(
        self, sample_texts, mock_embedding_model, mock_vector_store
    ):
        """Test adding texts to vector store."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = mock_embedding_model
            mock_numpy.return_value = mock_vector_store

            service = VectorStoreService(store_type="numpy")
            service.vector_store = mock_vector_store
            service.embedding_model = mock_embedding_model

            await service.add_texts(sample_texts)

            # Should generate embeddings
            assert mock_embedding_model.embed_documents.called
            # Should add to vector store
            assert mock_vector_store.add_texts_and_embeddings.called

    @pytest.mark.asyncio
    async def test_add_texts_with_existing_embeddings(
        self, sample_texts, mock_vector_store
    ):
        """Test adding texts that already have embeddings."""
        # Add embeddings to texts
        for text in sample_texts:
            text.embedding = np.random.rand(768).tolist()

        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = Mock()
            mock_numpy.return_value = mock_vector_store

            service = VectorStoreService(store_type="numpy")
            service.vector_store = mock_vector_store
            service.embedding_model = Mock()

            await service.add_texts(sample_texts)

            # Should not generate new embeddings
            assert not service.embedding_model.embed_documents.called
            # Should still add to vector store
            assert mock_vector_store.add_texts_and_embeddings.called

    @pytest.mark.asyncio
    async def test_similarity_search(self, mock_embedding_model, mock_vector_store):
        """Test similarity search."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = mock_embedding_model
            mock_numpy.return_value = mock_vector_store

            # Mock search results
            from paperqa.types import Doc
            test_doc = Doc(docname="test", dockey="test_key", citation="Test")
            result_texts = [Text(text="Result 1", name="r1", doc=test_doc)]
            result_scores = [0.85]
            mock_vector_store.similarity_search = AsyncMock(
                return_value=(result_texts, result_scores)
            )

            service = VectorStoreService(store_type="numpy")
            service.vector_store = mock_vector_store
            service.embedding_model = mock_embedding_model

            texts, scores = await service.similarity_search("test query", k=5)

            assert len(texts) == len(scores)
            assert mock_vector_store.similarity_search.called

    @pytest.mark.asyncio
    async def test_mmr_search(self, mock_embedding_model, mock_vector_store):
        """Test MMR (Maximal Marginal Relevance) search."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = mock_embedding_model
            mock_numpy.return_value = mock_vector_store

            from paperqa.types import Doc
            test_doc = Doc(docname="test", dockey="test_key", citation="Test")
            result_texts = [Text(text="Result 1", name="r1", doc=test_doc)]
            result_scores = [0.85]
            mock_vector_store.max_marginal_relevance_search = AsyncMock(
                return_value=(result_texts, result_scores)
            )

            service = VectorStoreService(store_type="numpy")
            service.vector_store = mock_vector_store
            service.embedding_model = mock_embedding_model

            texts, scores = await service.mmr_search("test query", k=5, fetch_k=20)

            assert len(texts) == len(scores)
            assert mock_vector_store.max_marginal_relevance_search.called

    @pytest.mark.asyncio
    async def test_embedding_generation(self, sample_texts, mock_embedding_model, mock_vector_store):
        """Test embedding generation for texts."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = mock_embedding_model
            mock_numpy.return_value = mock_vector_store
            mock_vector_store.add_texts_and_embeddings = AsyncMock(return_value=None)

            service = VectorStoreService(store_type="numpy")
            service.vector_store = mock_vector_store
            service.embedding_model = mock_embedding_model

            # Mock get_embeddable_text
            for text in sample_texts:
                text.get_embeddable_text = AsyncMock(return_value=text.text)

            await service.add_texts(sample_texts)

            # Should generate embeddings
            assert mock_embedding_model.embed_documents.called
            call_args = mock_embedding_model.embed_documents.call_args
            assert len(call_args[0][0]) == len(sample_texts)

    @pytest.mark.asyncio
    async def test_empty_texts(self, mock_vector_store):
        """Test handling of empty text list."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory, patch(
            "app.services.vector_store_service.NumpyVectorStore"
        ) as mock_numpy:
            mock_factory.return_value = Mock()
            mock_numpy.return_value = mock_vector_store

            service = VectorStoreService(store_type="numpy")
            service.vector_store = mock_vector_store

            await service.add_texts([])

            # Should not fail
            assert True

    def test_embedding_model_initialization(self):
        """Test embedding model initialization."""
        with patch(
            "app.services.vector_store_service.embedding_model_factory"
        ) as mock_factory:
            mock_model = Mock()
            mock_factory.return_value = mock_model

            service = VectorStoreService(
                store_type="numpy", embedding_model="gemini/text-embedding-004"
            )

            assert service.embedding_model == mock_model
            assert service.embedding_model_name == "gemini/text-embedding-004"

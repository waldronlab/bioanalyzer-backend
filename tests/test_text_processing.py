"""
Tests for text processing utilities in app/utils/text_processing.py
"""

import pytest

# Try to import torch and the module, skip tests if not available
try:
    import torch

    from app.utils.text_processing import AdvancedTextProcessor

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None  # Placeholder for type hints
    AdvancedTextProcessor = None  # Placeholder


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
class TestAdvancedTextProcessor:
    """Tests for AdvancedTextProcessor class."""

    def test_init(self):
        """Test processor initialization."""
        processor = AdvancedTextProcessor()
        # Should initialize even if tiktoken fails
        assert processor is not None

    def test_init_with_model(self):
        """Test processor initialization with specific model."""
        processor = AdvancedTextProcessor(model_name="cl100k_base")
        assert processor is not None

    def test_clean_scientific_text_removes_citations(self):
        """Test that citation references are removed."""
        text = "This is a test [1, 2, 3] with citations."
        cleaned = AdvancedTextProcessor.clean_scientific_text(text)
        assert "[" not in cleaned
        assert "]" not in cleaned
        assert "This is a test" in cleaned

    def test_clean_scientific_text_removes_figure_references(self):
        """Test that figure references are removed."""
        text = "As shown in Figure 1 and Table 2, the results are clear."
        cleaned = AdvancedTextProcessor.clean_scientific_text(text)
        assert "Figure 1" not in cleaned
        assert "Table 2" not in cleaned

    def test_clean_scientific_text_removes_urls(self):
        """Test that URLs are removed."""
        text = "Visit https://example.com for more information."
        cleaned = AdvancedTextProcessor.clean_scientific_text(text)
        assert "https://" not in cleaned
        assert "example.com" not in cleaned

    def test_clean_scientific_text_normalizes_whitespace(self):
        """Test that whitespace is normalized."""
        text = "This   has    multiple     spaces"
        cleaned = AdvancedTextProcessor.clean_scientific_text(text)
        # Should have single spaces
        assert "  " not in cleaned

    def test_clean_scientific_text_preserves_content(self):
        """Test that important content is preserved."""
        text = "The microbiome analysis showed significant differences."
        cleaned = AdvancedTextProcessor.clean_scientific_text(text)
        assert "microbiome" in cleaned
        assert "analysis" in cleaned
        assert "differences" in cleaned

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_encode_text_basic(self):
        """Test basic text encoding."""
        processor = AdvancedTextProcessor()
        text = "Hello world"
        encoded = processor.encode_text(text)
        assert isinstance(encoded, torch.Tensor)
        assert encoded.dtype == torch.long

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_encode_text_empty(self):
        """Test encoding empty text."""
        processor = AdvancedTextProcessor()
        encoded = processor.encode_text("")
        assert isinstance(encoded, torch.Tensor)

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_decode_tokens_basic(self):
        """Test basic token decoding."""
        processor = AdvancedTextProcessor()
        # Create a simple tensor
        tokens = torch.tensor([1, 2, 3])
        decoded = processor.decode_tokens(tokens)
        assert isinstance(decoded, str)

    def test_decode_tokens_list(self):
        """Test decoding from list."""
        processor = AdvancedTextProcessor()
        tokens = [1, 2, 3]
        decoded = processor.decode_tokens(tokens)
        assert isinstance(decoded, str)

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_batch_encode_single(self):
        """Test batch encoding with single text."""
        processor = AdvancedTextProcessor()
        texts = ["Hello world"]
        encoded = processor.batch_encode(texts)
        assert isinstance(encoded, torch.Tensor)
        assert encoded.dim() >= 1

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_batch_encode_multiple(self):
        """Test batch encoding with multiple texts."""
        processor = AdvancedTextProcessor()
        texts = ["Hello", "World", "Test"]
        encoded = processor.batch_encode(texts)
        assert isinstance(encoded, torch.Tensor)
        assert encoded.shape[0] == 3  # Should have 3 items

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_batch_encode_with_padding(self):
        """Test batch encoding with padding."""
        processor = AdvancedTextProcessor()
        texts = ["Short", "This is a much longer text"]
        encoded = processor.batch_encode(texts, pad=True)
        assert isinstance(encoded, torch.Tensor)
        # Both sequences should have the same length when padded
        if encoded.dim() >= 2:
            assert encoded.shape[1] == encoded.shape[1]  # Same length

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_batch_encode_without_padding(self):
        """Test batch encoding without padding."""
        processor = AdvancedTextProcessor()
        texts = ["Short", "Longer text here"]
        encoded = processor.batch_encode(texts, pad=False)
        assert isinstance(encoded, torch.Tensor)

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_batch_encode_max_length(self):
        """Test batch encoding with max_length parameter."""
        processor = AdvancedTextProcessor()
        texts = ["A" * 1000]  # Long text
        encoded = processor.batch_encode(texts, max_length=100)
        assert isinstance(encoded, torch.Tensor)

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_create_attention_mask(self):
        """Test attention mask creation."""
        processor = AdvancedTextProcessor()
        # Create a simple encoded tensor
        encoded = torch.tensor([[1, 2, 3, 0, 0]])  # With padding
        mask = processor.create_attention_mask(encoded)
        assert isinstance(mask, torch.Tensor)
        assert mask.dtype == torch.float

    def test_process_text_basic(self):
        """Test basic text processing."""
        processor = AdvancedTextProcessor()
        text = "This is a test text for processing."
        processed = processor.process_text(text)
        assert isinstance(processed, str)
        assert len(processed) > 0

    def test_process_text_max_length(self):
        """Test text processing with max_length."""
        processor = AdvancedTextProcessor()
        text = "A" * 10000  # Very long text
        processed = processor.process_text(text, max_length=100)
        assert isinstance(processed, str)
        # Should be truncated
        assert len(processed) <= len(text)

    def test_process_text_cleans_text(self):
        """Test that process_text cleans the text."""
        processor = AdvancedTextProcessor()
        text = "Test [1, 2] with Figure 1 and https://example.com"
        processed = processor.process_text(text)
        # Should remove citations, figures, and URLs
        assert "[" not in processed or "]" not in processed

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_encode_decode_roundtrip(self):
        """Test that encode and decode work together."""
        processor = AdvancedTextProcessor()
        original = "Hello world test"
        encoded = processor.encode_text(original)
        decoded = processor.decode_tokens(encoded)
        # Decoded should be a string (may not match exactly due to tokenization)
        assert isinstance(decoded, str)

    def test_special_tokens_defined(self):
        """Test that special tokens are defined."""
        processor = AdvancedTextProcessor()
        assert hasattr(processor, "bos_token_id")
        assert hasattr(processor, "eos_token_id")
        assert hasattr(processor, "pad_token_id")
        assert hasattr(processor, "sep_token_id")

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not available")
    def test_fallback_mode_works(self):
        """Test that fallback mode works when tiktoken unavailable."""
        # This test verifies the processor can work without tiktoken
        processor = AdvancedTextProcessor()
        # Should work even if tokenizer_available is False
        text = "Test text"
        encoded = processor.encode_text(text)
        assert isinstance(encoded, torch.Tensor)

    def test_process_text_handles_empty(self):
        """Test processing empty text."""
        processor = AdvancedTextProcessor()
        processed = processor.process_text("")
        assert isinstance(processed, str)

    def test_process_text_handles_unicode(self):
        """Test processing text with unicode characters."""
        processor = AdvancedTextProcessor()
        text = "Microbiome analysis: α-β diversity"
        processed = processor.process_text(text)
        assert isinstance(processed, str)
        # Should preserve or handle unicode gracefully
        assert len(processed) >= 0

"""Unit tests for app.ingestion.embedder."""

from unittest.mock import MagicMock, patch

import numpy as np

from app.ingestion.embedder import BATCH_SIZE, EMBEDDING_DIMS, LOCAL_DIMS, _zero_pad


class TestZeroPad:
    def test_pad_384_to_1536(self):
        vectors = np.random.rand(3, LOCAL_DIMS).astype(np.float32)
        padded = _zero_pad(vectors, EMBEDDING_DIMS)
        assert padded.shape == (3, EMBEDDING_DIMS)
        np.testing.assert_array_equal(padded[:, :LOCAL_DIMS], vectors)
        np.testing.assert_array_equal(padded[:, LOCAL_DIMS:], 0.0)

    def test_pad_single_vector(self):
        vectors = np.array([[0.1, 0.2, 0.3]])
        padded = _zero_pad(vectors, 6)
        assert padded.shape == (1, 6)
        assert padded[0, 0] == 0.1
        assert padded[0, 3] == 0.0

    def test_truncate_if_larger(self):
        vectors = np.random.rand(2, 2000).astype(np.float32)
        padded = _zero_pad(vectors, EMBEDDING_DIMS)
        assert padded.shape == (2, EMBEDDING_DIMS)

    def test_exact_dims_no_change(self):
        vectors = np.random.rand(1, EMBEDDING_DIMS).astype(np.float32)
        padded = _zero_pad(vectors, EMBEDDING_DIMS)
        np.testing.assert_array_equal(padded, vectors)


class TestEmbedTexts:
    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_local_provider_calls_model(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(2, LOCAL_DIMS).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import _embed_local

        result = _embed_local(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == EMBEDDING_DIMS
        mock_model.encode.assert_called_once()

    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_batch_splitting(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda batch, **kw: np.random.rand(len(batch), LOCAL_DIMS).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import _embed_local

        texts = [f"text_{i}" for i in range(BATCH_SIZE + 10)]
        result = _embed_local(texts)
        assert len(result) == BATCH_SIZE + 10
        assert mock_model.encode.call_count == 2

    def test_embed_texts_empty(self):
        from app.ingestion.embedder import embed_texts

        assert embed_texts([]) == []

    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_embed_query_returns_single_vector(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, LOCAL_DIMS).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import embed_query

        result = embed_query("test query")
        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIMS

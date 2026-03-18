"""Unit tests for app.ingestion.embedder."""

from unittest.mock import MagicMock, patch

import numpy as np

from app.ingestion.embedder import BATCH_SIZE, EMBEDDING_DIMS, _adjust_dims


class TestAdjustDims:
    def test_pad_smaller_to_target(self):
        vectors = np.random.rand(3, 768).astype(np.float32)
        result = _adjust_dims(vectors, 1024)
        assert result.shape == (3, 1024)
        np.testing.assert_array_equal(result[:, :768], vectors)
        np.testing.assert_array_equal(result[:, 768:], 0.0)

    def test_truncate_larger_to_target(self):
        vectors = np.random.rand(2, 2000).astype(np.float32)
        result = _adjust_dims(vectors, 1024)
        assert result.shape == (2, 1024)

    def test_exact_dims_no_change(self):
        vectors = np.random.rand(1, EMBEDDING_DIMS).astype(np.float32)
        result = _adjust_dims(vectors, EMBEDDING_DIMS)
        np.testing.assert_array_equal(result, vectors)

    def test_pad_single_vector(self):
        vectors = np.array([[0.1, 0.2, 0.3]])
        result = _adjust_dims(vectors, 6)
        assert result.shape == (1, 6)
        assert result[0, 0] == 0.1
        assert result[0, 3] == 0.0


class TestEmbedTexts:
    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_local_provider_calls_model(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_local = "intfloat/multilingual-e5-large"

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(2, 1024).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import _embed_local

        result = _embed_local(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == EMBEDDING_DIMS
        mock_model.encode.assert_called_once()

    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_e5_adds_passage_prefix_for_indexing(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_local = "intfloat/multilingual-e5-large"

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(2, 1024).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import _embed_local

        _embed_local(["hello", "world"], is_query=False)
        call_args = mock_model.encode.call_args[0][0]
        assert call_args == ["passage: hello", "passage: world"]

    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_e5_adds_query_prefix_for_search(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_local = "intfloat/multilingual-e5-large"

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, 1024).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import _embed_local

        _embed_local(["how to open door"], is_query=True)
        call_args = mock_model.encode.call_args[0][0]
        assert call_args == ["query: how to open door"]

    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_non_e5_model_no_prefix(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = 1024
        mock_settings.embedding_model_local = "all-MiniLM-L6-v2"

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, 384).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import _embed_local

        _embed_local(["hello"], is_query=True)
        call_args = mock_model.encode.call_args[0][0]
        assert call_args == ["hello"]

    @patch("app.ingestion.embedder._get_local_model")
    @patch("app.ingestion.embedder.settings")
    def test_batch_splitting(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_local = "intfloat/multilingual-e5-large"

        mock_model = MagicMock()
        mock_model.encode.side_effect = lambda batch, **kw: np.random.rand(len(batch), 1024).astype(np.float32)
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
    def test_embed_query_returns_single_vector_with_query_prefix(self, mock_settings, mock_get_model):
        mock_settings.embedding_provider = "local"
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_local = "intfloat/multilingual-e5-large"

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, 1024).astype(np.float32)
        mock_get_model.return_value = mock_model

        from app.ingestion.embedder import embed_query

        result = embed_query("test query")
        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIMS
        call_args = mock_model.encode.call_args[0][0]
        assert call_args == ["query: test query"]

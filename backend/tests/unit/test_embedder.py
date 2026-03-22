"""Unit tests for app.ingestion.embedder (Gemini provider)."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import numpy as np

from app.ingestion.embedder import BATCH_SIZE, EMBEDDING_DIMS


def _make_embed_result(count: int, dims: int = EMBEDDING_DIMS):
    """Create a mock Gemini embed_content response."""
    result = MagicMock()
    embeddings = []
    for _ in range(count):
        emb = MagicMock()
        emb.values = np.random.rand(dims).astype(np.float32).tolist()
        embeddings.append(emb)
    result.embeddings = embeddings
    return result


@dataclass
class _FakeEmbedConfig:
    task_type: str
    output_dimensionality: int


def _fake_embed_config(*, task_type: str, output_dimensionality: int):
    return _FakeEmbedConfig(task_type=task_type, output_dimensionality=output_dimensionality)


class TestEmbedTexts:
    @patch("app.ingestion.embedder._embed_config", side_effect=_fake_embed_config)
    @patch("app.ingestion.embedder._get_gemini_client")
    @patch("app.ingestion.embedder.settings")
    def test_gemini_calls_embed_content(self, mock_settings, mock_get_client, _mock_config):
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_gemini = "gemini-embedding-2-preview"

        mock_client = MagicMock()
        mock_client.models.embed_content.return_value = _make_embed_result(2)
        mock_get_client.return_value = mock_client

        from app.ingestion.embedder import embed_texts

        result = embed_texts(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == EMBEDDING_DIMS
        mock_client.models.embed_content.assert_called_once()

    @patch("app.ingestion.embedder._embed_config", side_effect=_fake_embed_config)
    @patch("app.ingestion.embedder._get_gemini_client")
    @patch("app.ingestion.embedder.settings")
    def test_document_task_type_for_indexing(self, mock_settings, mock_get_client, _mock_config):
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_gemini = "gemini-embedding-2-preview"

        mock_client = MagicMock()
        mock_client.models.embed_content.return_value = _make_embed_result(1)
        mock_get_client.return_value = mock_client

        from app.ingestion.embedder import embed_texts

        embed_texts(["some document text"], is_query=False)
        call_kwargs = mock_client.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_DOCUMENT"

    @patch("app.ingestion.embedder._embed_config", side_effect=_fake_embed_config)
    @patch("app.ingestion.embedder._get_gemini_client")
    @patch("app.ingestion.embedder.settings")
    def test_query_task_type_for_search(self, mock_settings, mock_get_client, _mock_config):
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_gemini = "gemini-embedding-2-preview"

        mock_client = MagicMock()
        mock_client.models.embed_content.return_value = _make_embed_result(1)
        mock_get_client.return_value = mock_client

        from app.ingestion.embedder import embed_texts

        embed_texts(["how to open door"], is_query=True)
        call_kwargs = mock_client.models.embed_content.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config.task_type == "RETRIEVAL_QUERY"

    @patch("app.ingestion.embedder._embed_config", side_effect=_fake_embed_config)
    @patch("app.ingestion.embedder._get_gemini_client")
    @patch("app.ingestion.embedder.settings")
    def test_batch_splitting(self, mock_settings, mock_get_client, _mock_config):
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_gemini = "gemini-embedding-2-preview"

        mock_client = MagicMock()
        mock_client.models.embed_content.side_effect = lambda **kw: _make_embed_result(len(kw["contents"]))
        mock_get_client.return_value = mock_client

        from app.ingestion.embedder import embed_texts

        texts = [f"text_{i}" for i in range(BATCH_SIZE + 10)]
        result = embed_texts(texts)
        assert len(result) == BATCH_SIZE + 10
        assert mock_client.models.embed_content.call_count == 2

    def test_embed_texts_empty(self):
        from app.ingestion.embedder import embed_texts

        assert embed_texts([]) == []

    @patch("app.ingestion.embedder._embed_config", side_effect=_fake_embed_config)
    @patch("app.ingestion.embedder._get_gemini_client")
    @patch("app.ingestion.embedder.settings")
    def test_embed_query_returns_single_vector(self, mock_settings, mock_get_client, _mock_config):
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_gemini = "gemini-embedding-2-preview"

        mock_client = MagicMock()
        mock_client.models.embed_content.return_value = _make_embed_result(1)
        mock_get_client.return_value = mock_client

        from app.ingestion.embedder import embed_query

        result = embed_query("test query")
        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIMS

    @patch("app.ingestion.embedder._embed_config", side_effect=_fake_embed_config)
    @patch("app.ingestion.embedder._get_gemini_client")
    @patch("app.ingestion.embedder.settings")
    def test_vectors_are_l2_normalized(self, mock_settings, mock_get_client, _mock_config):
        mock_settings.embedding_dims = EMBEDDING_DIMS
        mock_settings.embedding_model_gemini = "gemini-embedding-2-preview"

        mock_client = MagicMock()
        result_mock = MagicMock()
        emb = MagicMock()
        emb.values = [3.0, 4.0] + [0.0] * (EMBEDDING_DIMS - 2)
        result_mock.embeddings = [emb]
        mock_client.models.embed_content.return_value = result_mock
        mock_get_client.return_value = mock_client

        from app.ingestion.embedder import embed_texts

        result = embed_texts(["test"])
        vec = np.array(result[0])
        norm = np.linalg.norm(vec)
        np.testing.assert_almost_equal(norm, 1.0, decimal=5)

"""Unit tests for app.search.reranker."""

from unittest.mock import MagicMock, patch

import numpy as np

from app.search.reranker import rerank


class TestRerank:
    def test_empty_results(self):
        assert rerank("query", []) == []

    def test_single_result(self):
        results = [{"content": "hello", "similarity": 0.9}]
        assert rerank("query", results, top_k=5) == results

    @patch("app.search.reranker._get_reranker")
    def test_reranks_by_cross_encoder_score(self, mock_get):
        model = MagicMock()
        model.predict.return_value = np.array([0.1, 0.9, 0.5])
        mock_get.return_value = model

        results = [
            {"content": "low relevance", "similarity": 0.95},
            {"content": "high relevance", "similarity": 0.70},
            {"content": "medium relevance", "similarity": 0.80},
        ]
        reranked = rerank("test query", results, top_k=3)

        assert reranked[0]["content"] == "high relevance"
        assert reranked[1]["content"] == "medium relevance"
        assert reranked[2]["content"] == "low relevance"

    @patch("app.search.reranker._get_reranker")
    def test_top_k_limits_output(self, mock_get):
        model = MagicMock()
        model.predict.return_value = np.array([0.3, 0.9, 0.1, 0.7, 0.5])
        mock_get.return_value = model

        results = [{"content": f"chunk {i}", "similarity": 0.5} for i in range(5)]
        reranked = rerank("query", results, top_k=2)

        assert len(reranked) == 2
        assert reranked[0]["content"] == "chunk 1"
        assert reranked[1]["content"] == "chunk 3"

    @patch("app.search.reranker._get_reranker")
    def test_passes_enriched_pairs_to_model(self, mock_get):
        model = MagicMock()
        model.predict.return_value = np.array([0.5, 0.5])
        mock_get.return_value = model

        results = [
            {"content": "first chunk", "heading_path": "API > Auth", "similarity": 0.8},
            {"content": "second chunk", "heading_path": "Setup", "similarity": 0.7},
        ]
        rerank("my query", results, top_k=2)

        pairs = model.predict.call_args[0][0]
        assert pairs == [
            ["my query", "[API > Auth]\nfirst chunk"],
            ["my query", "[Setup]\nsecond chunk"],
        ]

    @patch("app.search.reranker._get_reranker")
    def test_no_heading_path_uses_content_only(self, mock_get):
        model = MagicMock()
        model.predict.return_value = np.array([0.5, 0.5])
        mock_get.return_value = model

        results = [
            {"content": "first chunk", "similarity": 0.8},
            {"content": "second chunk", "heading_path": "", "similarity": 0.7},
        ]
        rerank("my query", results, top_k=2)

        pairs = model.predict.call_args[0][0]
        assert pairs[0] == ["my query", "first chunk"]
        assert pairs[1] == ["my query", "second chunk"]

    @patch("app.search.reranker._get_reranker")
    def test_markdown_cleaned_before_scoring(self, mock_get):
        model = MagicMock()
        model.predict.return_value = np.array([0.8, 0.5])
        mock_get.return_value = model

        results = [
            {
                "content": "Use **HMAC-SHA256** for [auth](https://example.com).",
                "heading_path": "API",
                "similarity": 0.8,
            },
            {
                "content": "Other content.",
                "heading_path": "Other",
                "similarity": 0.5,
            },
        ]
        rerank("auth query", results, top_k=2)

        pairs = model.predict.call_args[0][0]
        text_sent = pairs[0][1]
        assert "**" not in text_sent
        assert "https://example.com" not in text_sent
        assert "HMAC-SHA256" in text_sent
        assert "auth" in text_sent

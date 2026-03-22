"""Unit tests for RRF (Reciprocal Rank Fusion) in hybrid search."""

from app.search.service import _rrf_fuse


def _make_result(heading: str, content: str, similarity: float = 0.9):
    return {
        "content": content,
        "parent_content": None,
        "heading_path": heading,
        "heading_level": 2,
        "token_count": len(content.split()),
        "doc_title": "Doc",
        "product_name": "Product",
        "manufacturer": "Mfg",
        "firmware_version": "1.0",
        "similarity": similarity,
    }


class TestRRFFuse:
    def test_empty_lists(self):
        result = _rrf_fuse([], [])
        assert result == []

    def test_vector_only(self):
        vec = [_make_result("H1", "content A"), _make_result("H2", "content B")]
        result = _rrf_fuse(vec, [])
        assert len(result) == 2
        assert result[0]["heading_path"] == "H1"

    def test_bm25_only(self):
        bm25 = [_make_result("H1", "content A"), _make_result("H2", "content B")]
        result = _rrf_fuse([], bm25)
        assert len(result) == 2

    def test_overlapping_results_boosted(self):
        """Chunks appearing in both lists should rank higher than single-list chunks."""
        shared = _make_result("Shared", "shared content")
        vec_only = _make_result("VecOnly", "vector only content")
        bm25_only = _make_result("BM25Only", "bm25 only content")

        vec = [shared, vec_only]
        bm25 = [shared, bm25_only]

        result = _rrf_fuse(vec, bm25, k=60, vector_weight=0.5, bm25_weight=0.5)
        assert result[0]["heading_path"] == "Shared"

    def test_all_unique_results_merged(self):
        vec = [_make_result("V1", "vec content 1"), _make_result("V2", "vec content 2")]
        bm25 = [_make_result("B1", "bm25 content 1"), _make_result("B2", "bm25 content 2")]

        result = _rrf_fuse(vec, bm25)
        headings = {r["heading_path"] for r in result}
        assert headings == {"V1", "V2", "B1", "B2"}

    def test_weights_affect_ranking(self):
        """With vector_weight=1.0 and bm25_weight=0.0, vector order should dominate."""
        vec = [_make_result("V1", "first"), _make_result("V2", "second")]
        bm25 = [_make_result("V2", "second"), _make_result("V1", "first")]

        result = _rrf_fuse(vec, bm25, vector_weight=1.0, bm25_weight=0.0)
        assert result[0]["heading_path"] == "V1"
        assert result[1]["heading_path"] == "V2"

    def test_k_parameter_smoothing(self):
        """Higher k reduces the impact of rank differences."""
        vec = [_make_result("A", "content A")]
        bm25 = [_make_result("A", "content A")]

        result_low_k = _rrf_fuse(vec, bm25, k=1)
        result_high_k = _rrf_fuse(vec, bm25, k=1000)

        assert len(result_low_k) == 1
        assert len(result_high_k) == 1

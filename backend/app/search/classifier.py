"""Lightweight query classifier for search (shared by Web Chat RAG and MCP).

Re-exports the classify function from chat.rag to avoid code duplication.
"""

from app.chat.rag import _classify_query as classify_query, _load_product_names as load_product_names

__all__ = ["classify_query", "load_product_names"]

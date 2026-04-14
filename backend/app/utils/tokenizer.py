"""Token counting utility with tiktoken (cl100k_base) and heuristic fallback."""

import logging

logger = logging.getLogger(__name__)

_encoding = None
_USE_TIKTOKEN = True


def _get_encoding():
    global _encoding, _USE_TIKTOKEN
    if _encoding is not None:
        return _encoding
    try:
        import tiktoken
        _encoding = tiktoken.get_encoding("cl100k_base")
        return _encoding
    except Exception:
        logger.warning("tiktoken unavailable, falling back to heuristic token counting (words*1.3)")
        _USE_TIKTOKEN = False
        return None


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken cl100k_base, falling back to word-based heuristic."""
    if not text:
        return 1
    enc = _get_encoding()
    if enc is not None:
        return max(1, len(enc.encode(text, disallowed_special=())))
    return max(1, int(len(text.split()) * 1.3))

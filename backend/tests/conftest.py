"""Root conftest: shared helpers and fake embedding for all tests."""

import hashlib
import math
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Pre-register mocks for heavy dependencies that are only available inside
# the Docker container (celery, boto3, structlog).  This lets the full test
# suite run on a developer machine where only lightweight deps are installed.
# Each block is guarded by a try/import so it's a no-op when the real
# package IS available.
# ---------------------------------------------------------------------------

try:
    import celery as _celery_check  # noqa: F401
except ModuleNotFoundError:
    _mock_celery = MagicMock()

    def _fake_task_decorator(*args, **kwargs):
        """Simulate @celery.task(bind=True, ...) for tests without celery."""
        bind = kwargs.get("bind", False)

        def wrapper(fn):
            fn.request = MagicMock(id="mock-task-id")
            fn.retry = MagicMock(side_effect=Exception("retry"))
            if bind:
                import functools

                @functools.wraps(fn)
                def _bound_run(**kw):
                    return fn(fn, **kw)

                fn.run = _bound_run
            return fn

        return wrapper

    _mock_celery.Celery.return_value.task = _fake_task_decorator
    _mock_celery.Celery.return_value.conf = MagicMock()
    sys.modules.setdefault("celery", _mock_celery)
    sys.modules.setdefault("celery.signals", MagicMock())

try:
    import boto3 as _boto3_check  # noqa: F401
except ModuleNotFoundError:
    sys.modules.setdefault("boto3", MagicMock())
    _mock_botocore = MagicMock()

    class _FakeClientError(Exception):
        """Stand-in for botocore.exceptions.ClientError."""

        def __init__(self, error_response=None, operation_name=""):
            self.response = error_response or {}
            self.operation_name = operation_name
            super().__init__(str(error_response))

    _mock_botocore.exceptions.ClientError = _FakeClientError
    sys.modules.setdefault("botocore", _mock_botocore)
    sys.modules.setdefault("botocore.exceptions", _mock_botocore.exceptions)

try:
    import structlog as _structlog_check  # noqa: F401
except ModuleNotFoundError:
    _mock_structlog = MagicMock()
    _mock_structlog.get_logger.return_value = MagicMock()
    _mock_structlog.configure = MagicMock()
    _mock_structlog.make_filtering_bound_logger = MagicMock(return_value=MagicMock)
    _mock_structlog.PrintLogger = MagicMock
    _mock_structlog.WriteLogger = MagicMock
    # Processors must be callable and return the event_dict
    _identity = lambda logger, method, event_dict: event_dict  # noqa: E731
    _mock_structlog.stdlib.ProcessorFormatter = MagicMock()
    _mock_structlog.stdlib.add_log_level = _identity
    _mock_structlog.stdlib.filter_by_level = _identity
    _mock_structlog.stdlib.render_to_log_kwargs = _identity
    _mock_structlog.dev.ConsoleRenderer = MagicMock(return_value=_identity)
    _mock_structlog.processors.JSONRenderer = MagicMock(return_value=_identity)
    _mock_structlog.processors.TimeStamper = MagicMock(return_value=_identity)
    _mock_structlog.processors.StackInfoRenderer = MagicMock(return_value=_identity)
    _mock_structlog.processors.format_exc_info = _identity
    _mock_structlog.processors.UnicodeDecoder = MagicMock(return_value=_identity)
    _mock_structlog.contextvars.merge_contextvars = _identity
    sys.modules.setdefault("structlog", _mock_structlog)
    sys.modules.setdefault("structlog.stdlib", _mock_structlog.stdlib)
    sys.modules.setdefault("structlog.dev", _mock_structlog.dev)
    sys.modules.setdefault("structlog.processors", _mock_structlog.processors)
    sys.modules.setdefault("structlog.contextvars", _mock_structlog.contextvars)

# Other optional heavy deps


EMBEDDING_DIMS = 1024


def fake_embed_single(text: str) -> list[float]:
    """Generate a deterministic 1024-dim vector from text hash.

    Similar texts won't produce similar vectors (unlike real embeddings),
    but identical texts always produce identical vectors. This is sufficient
    for testing DB storage, retrieval, and cosine distance ordering when
    we control which vectors are "close" by using the same text.
    """
    h = hashlib.sha256(text.encode()).digest()
    raw = [float(b) / 255.0 for b in h]
    vec = (raw * (EMBEDDING_DIMS // len(raw) + 1))[:EMBEDDING_DIMS]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def fake_embed_texts(texts: list[str], **kwargs) -> list[list[float]]:
    """Batch fake embedding — returns list of 1024-dim vectors."""
    if not texts:
        return []
    return [fake_embed_single(t) for t in texts]


def fake_embed_query(text: str) -> list[float]:
    """Single fake embedding — returns 1024-dim vector."""
    return fake_embed_single(text)

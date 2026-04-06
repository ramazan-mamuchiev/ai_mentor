"""Simple synchronous retry with exponential backoff."""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 120.0,
    is_retryable: Callable[[Exception], bool] = lambda _e: False,
    label: str = "",
) -> T:
    """Call *fn()* up to `max_retries + 1` times with exponential backoff.

    Args:
        fn: zero-arg callable to execute.
        max_retries: how many extra attempts after the first failure.
        base_delay: initial delay in seconds (doubles each retry).
        max_delay: ceiling for the computed delay.
        is_retryable: predicate -- return True to retry the exception.
        label: short string for log messages.

    Raises:
        The last exception if all attempts are exhausted or the error
        is not retryable.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0 and last_exc is not None:
            delay = min(base_delay * 2 ** (attempt - 1), max_delay)
            logger.warning(
                "%s: retrying (%d/%d) in %.1fs",
                label or "retry_call",
                attempt + 1,
                max_retries + 1,
                delay,
                extra={"attempt": attempt + 1, "delay_s": delay, "label": label},
            )
            time.sleep(delay)
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc) or attempt == max_retries:
                raise
    raise last_exc  # type: ignore[misc]

"""Custom Locust metrics for Redis commands.

Wraps Redis calls so that each command is reported as a Locust request event
with proper name, response time, and error tracking.  Errors are categorised
using :func:`workloads.lib.topology_clients.classify_error` so that Locust
groups failures by type (``connection_error``, ``timeout``, etc.) instead of
showing raw exception tracebacks.
"""

import time
import logging
from contextlib import contextmanager
from typing import Optional

from locust import events

from workloads.lib.topology_clients import classify_error

logger = logging.getLogger(__name__)


class CategorisedError(Exception):
    """Thin wrapper that carries a human-readable failure category."""

    def __init__(self, category: str, original: Exception):
        self.category = category
        self.original = original
        super().__init__(f"{category}: {original}")


@contextmanager
def redis_command_timer(command_name: str, key: Optional[str] = None):
    """Context manager that reports a Redis command as a Locust request event.

    Usage::

        with redis_command_timer("GET", key="cache:electronics:42"):
            value = r.get("cache:electronics:42")

    Args:
        command_name: The Redis command (e.g. ``GET``, ``HSET``).
        key: Optional key name for logging (not included in the Locust
             request name to avoid cardinality explosion).
    """
    request_type = "redis"
    name = command_name
    start = time.perf_counter()
    exc: Optional[Exception] = None
    try:
        yield
    except Exception as e:
        exc = e
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if exc is None:
            events.request.fire(
                request_type=request_type,
                name=name,
                response_time=elapsed_ms,
                response_length=0,
                exception=None,
            )
        else:
            category = classify_error(exc)
            logger.debug("Redis %s failed (key=%s, category=%s): %s",
                         command_name, key, category, exc)
            events.request.fire(
                request_type=request_type,
                name=name,
                response_time=elapsed_ms,
                response_length=0,
                exception=CategorisedError(category, exc),
            )


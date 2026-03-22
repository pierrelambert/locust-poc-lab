"""Custom Locust metrics for Redis commands.

Wraps Redis calls so that each command is reported as a Locust request event
with proper name, response time, and error tracking.
"""

import time
import logging
from contextlib import contextmanager
from typing import Optional

from locust import events

logger = logging.getLogger(__name__)


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
            logger.debug("Redis %s failed (key=%s): %s", command_name, key, exc)
            events.request.fire(
                request_type=request_type,
                name=name,
                response_time=elapsed_ms,
                response_length=0,
                exception=exc,
            )


"""Redis connection management — one client per Locust worker process.

Delegates to :mod:`workloads.lib.topology_clients` for topology-aware
client creation (standalone, sentinel, cluster, enterprise).
"""

import logging
from typing import Any, Dict, Optional

import redis

from workloads.lib.topology_clients import create_client

logger = logging.getLogger(__name__)

# Module-level singleton (one per worker process)
_client: Optional[redis.Redis] = None


def get_redis_client(conn_cfg: Optional[Dict[str, Any]] = None, **kwargs) -> redis.Redis:
    """Return a Redis client, creating it on first call.

    The client type is determined by ``connection_mode`` in *conn_cfg*
    (defaults to ``standalone`` for backward compatibility).

    Args:
        conn_cfg: The ``workload.connection`` section of a loaded profile.
        **kwargs: Extra arguments forwarded to the adapter factory
                  (e.g. ``replica=True`` for sentinel mode).
    """
    global _client
    if _client is None:
        if conn_cfg is None:
            raise RuntimeError("Connection not initialized — pass conn_cfg on first call")
        _client = create_client(conn_cfg, **kwargs)
    return _client


def reset_pool() -> None:
    """Tear down the client (useful for tests and test_stop events)."""
    global _client
    if _client:
        try:
            _client.close()
        except Exception:
            pass
    _client = None


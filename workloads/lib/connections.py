"""Redis connection pooling — one pool per Locust worker process."""

import logging
from typing import Any, Dict, Optional

import redis

logger = logging.getLogger(__name__)

# Module-level pool singleton (one per worker process)
_pool: Optional[redis.ConnectionPool] = None
_client: Optional[redis.Redis] = None


def create_redis_pool(conn_cfg: Dict[str, Any]) -> redis.ConnectionPool:
    """Create a Redis connection pool from a profile's connection config.

    Args:
        conn_cfg: The ``workload.connection`` section of a loaded profile.

    Returns:
        A ``redis.ConnectionPool`` instance.
    """
    global _pool
    pool_kwargs = {
        "host": conn_cfg.get("host", "localhost"),
        "port": conn_cfg.get("port", 6379),
        "db": conn_cfg.get("db", 0),
        "socket_timeout": conn_cfg.get("socket_timeout", 5.0),
        "socket_connect_timeout": conn_cfg.get("socket_timeout", 5.0),
        "retry_on_timeout": conn_cfg.get("retry_on_timeout", True),
        "max_connections": conn_cfg.get("max_connections", 50),
        "decode_responses": True,
    }

    password = conn_cfg.get("password")
    if password and str(password).strip():
        pool_kwargs["password"] = password

    if conn_cfg.get("ssl", False):
        pool_kwargs["ssl"] = True
        pool_kwargs["ssl_cert_reqs"] = "required"

    _pool = redis.ConnectionPool(**pool_kwargs)
    logger.info(
        "Redis pool created: %s:%s db=%s max_connections=%s",
        pool_kwargs["host"],
        pool_kwargs["port"],
        pool_kwargs["db"],
        pool_kwargs["max_connections"],
    )
    return _pool


def get_redis_client(conn_cfg: Optional[Dict[str, Any]] = None) -> redis.Redis:
    """Return a Redis client backed by the shared connection pool.

    Creates the pool on first call if it doesn't exist yet.
    """
    global _client, _pool
    if _pool is None:
        if conn_cfg is None:
            raise RuntimeError("Connection pool not initialized — call create_redis_pool first")
        create_redis_pool(conn_cfg)
    if _client is None:
        _client = redis.Redis(connection_pool=_pool)
    return _client


def reset_pool() -> None:
    """Tear down the pool (useful for tests)."""
    global _pool, _client
    if _client:
        _client.close()
    if _pool:
        _pool.disconnect()
    _pool = None
    _client = None


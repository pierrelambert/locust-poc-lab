"""Topology-aware Redis client adapters.

Supports four connection modes driven by the ``connection_mode`` field in a
workload profile's ``connection`` section:

* **standalone** — plain ``redis.Redis`` with a connection pool (default,
  backward-compatible).
* **sentinel** — uses ``redis.sentinel.Sentinel`` for master discovery;
  returns a master or replica client depending on ``replica_reads``.
* **cluster** — uses ``redis.cluster.RedisCluster`` with automatic
  MOVED/ASK redirect handling.
* **enterprise** — connects to a Redis Enterprise proxy endpoint with
  optional TLS/SNI support.

Connection config schema (YAML)::

    connection:
      connection_mode: standalone | sentinel | cluster | enterprise
      host: localhost          # standalone / enterprise host
      port: 6379               # standalone / enterprise port
      password: ""             # optional
      db: 0                    # standalone / enterprise only
      ssl: false
      socket_timeout: 5.0
      retry_on_timeout: true
      max_connections: 50
      # sentinel-specific
      sentinel_hosts:          # list of "host:port" strings
        - "localhost:26379"
      sentinel_service: mymaster
      sentinel_password: ""    # password for sentinel instances themselves
      # cluster-specific (host/port used as seed node)
      # enterprise-specific
      sni_hostname: ""         # optional SNI for multi-tenant TLS
"""

import logging
import ssl as _ssl
from typing import Any, Dict, List, Optional, Tuple, Union

import redis
import redis.sentinel
import redis.cluster

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Failure categorisation
# ---------------------------------------------------------------------------

class FailureCategory:
    """Lightweight failure categories reported in Locust error output."""
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    MOVED_REDIRECT = "moved_redirect"
    ASK_REDIRECT = "ask_redirect"
    READONLY = "readonly"
    CLUSTER_DOWN = "cluster_down"
    AUTH_ERROR = "auth_error"
    UNKNOWN = "unknown"


def classify_error(exc: Exception) -> str:
    """Return a short failure category string for *exc*.

    The category is used as the Locust exception message so that the UI
    groups errors meaningfully instead of showing raw tracebacks.
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()

    if isinstance(exc, redis.AuthenticationError):
        return FailureCategory.AUTH_ERROR
    if isinstance(exc, redis.TimeoutError) or "timeout" in name:
        return FailureCategory.TIMEOUT
    if isinstance(exc, redis.ConnectionError) or isinstance(exc, ConnectionError):
        return FailureCategory.CONNECTION_ERROR
    if "moved" in msg:
        return FailureCategory.MOVED_REDIRECT
    if "ask" in msg:
        return FailureCategory.ASK_REDIRECT
    if "readonly" in msg:
        return FailureCategory.READONLY
    if "clusterdown" in msg:
        return FailureCategory.CLUSTER_DOWN
    return FailureCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def _common_pool_kwargs(conn_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build keyword arguments shared across all connection modes."""
    kwargs: Dict[str, Any] = {
        "socket_timeout": conn_cfg.get("socket_timeout", 5.0),
        "socket_connect_timeout": conn_cfg.get("socket_timeout", 5.0),
        "retry_on_timeout": conn_cfg.get("retry_on_timeout", True),
        "decode_responses": True,
    }
    password = conn_cfg.get("password")
    if password and str(password).strip():
        kwargs["password"] = password
    return kwargs


def _apply_ssl(kwargs: Dict[str, Any], conn_cfg: Dict[str, Any]) -> None:
    """Mutate *kwargs* to add SSL/TLS options when enabled.

    When certificate paths (``ssl_certfile``, ``ssl_keyfile``,
    ``ssl_ca_certs``) are present in *conn_cfg*,
    :class:`~workloads.lib.tls_manager.TLSCertificateManager` is used
    to build the full set of SSL kwargs.  Otherwise falls back to
    simple flag-based SSL.
    """
    if not conn_cfg.get("ssl", False):
        return

    # Check whether explicit cert paths are provided
    has_certs = any(
        conn_cfg.get(k)
        for k in ("ssl_certfile", "ssl_keyfile", "ssl_ca_certs")
    )

    if has_certs:
        from workloads.lib.tls_manager import TLSCertificateManager

        mgr = TLSCertificateManager(
            cert_path=conn_cfg.get("ssl_certfile"),
            key_path=conn_cfg.get("ssl_keyfile"),
            ca_path=conn_cfg.get("ssl_ca_certs"),
            sni_hostname=conn_cfg.get("sni_hostname"),
        )
        kwargs.update(mgr.ssl_kwargs())
    else:
        kwargs["ssl"] = True
        kwargs["ssl_cert_reqs"] = "required"
        sni = conn_cfg.get("sni_hostname")
        if sni:
            kwargs["ssl_check_hostname"] = True


# ---------------------------------------------------------------------------
# Adapter factories
# ---------------------------------------------------------------------------


def create_standalone_client(conn_cfg: Dict[str, Any]) -> redis.Redis:
    """Create a plain ``redis.Redis`` client backed by a connection pool."""
    pool_kwargs = _common_pool_kwargs(conn_cfg)
    pool_kwargs.update({
        "host": conn_cfg.get("host", "localhost"),
        "port": conn_cfg.get("port", 6379),
        "db": conn_cfg.get("db", 0),
        "max_connections": conn_cfg.get("max_connections", 50),
    })
    _apply_ssl(pool_kwargs, conn_cfg)
    pool = redis.ConnectionPool(**pool_kwargs)
    client = redis.Redis(connection_pool=pool)
    logger.info(
        "Standalone client created: %s:%s db=%s",
        pool_kwargs["host"], pool_kwargs["port"], pool_kwargs["db"],
    )
    return client


def create_sentinel_client(
    conn_cfg: Dict[str, Any],
    *,
    replica: bool = False,
) -> redis.Redis:
    """Create a client via Sentinel master discovery.

    Args:
        conn_cfg: Connection config from the profile.
        replica: If ``True``, return a replica (read-only) client.

    Returns:
        A ``redis.Redis`` instance obtained from the Sentinel.
    """
    sentinel_hosts = _parse_sentinel_hosts(conn_cfg.get("sentinel_hosts"))
    if not sentinel_hosts:
        # Fallback: use host:port as a single sentinel endpoint
        sentinel_hosts = [(conn_cfg.get("host", "localhost"), conn_cfg.get("port", 26379))]

    service_name = conn_cfg.get("sentinel_service", "mymaster")

    sentinel_kwargs: Dict[str, Any] = {}
    sentinel_password = conn_cfg.get("sentinel_password")
    if sentinel_password and str(sentinel_password).strip():
        sentinel_kwargs["password"] = sentinel_password

    common = _common_pool_kwargs(conn_cfg)
    # Sentinel client password goes in connection_kwargs, not sentinel_kwargs
    connection_kwargs = {**common}
    connection_kwargs["db"] = conn_cfg.get("db", 0)
    connection_kwargs["max_connections"] = conn_cfg.get("max_connections", 50)

    if conn_cfg.get("ssl", False):
        connection_kwargs["ssl"] = True
        connection_kwargs["ssl_cert_reqs"] = "required"

    sentinel = redis.sentinel.Sentinel(
        sentinel_hosts,
        sentinel_kwargs=sentinel_kwargs,
        **{k: v for k, v in common.items() if k in ("socket_timeout", "socket_connect_timeout")},
    )

    if replica:
        client = sentinel.slave_for(service_name, **connection_kwargs)
        logger.info("Sentinel replica client created for service '%s'", service_name)
    else:
        client = sentinel.master_for(service_name, **connection_kwargs)
        logger.info("Sentinel master client created for service '%s'", service_name)

    return client


def create_cluster_client(conn_cfg: Dict[str, Any]) -> redis.cluster.RedisCluster:
    """Create a ``RedisCluster`` client with automatic redirect handling."""
    common = _common_pool_kwargs(conn_cfg)
    cluster_kwargs: Dict[str, Any] = {
        "host": conn_cfg.get("host", "localhost"),
        "port": conn_cfg.get("port", 6379),
        **common,
    }
    _apply_ssl(cluster_kwargs, conn_cfg)
    # RedisCluster doesn't use db
    cluster_kwargs.pop("db", None)

    client = redis.cluster.RedisCluster(**cluster_kwargs)
    logger.info(
        "Cluster client created (seed %s:%s)",
        cluster_kwargs["host"], cluster_kwargs["port"],
    )
    return client


def create_enterprise_client(conn_cfg: Dict[str, Any]) -> redis.Redis:
    """Create a client for a Redis Enterprise proxy endpoint.

    Functionally identical to standalone but logs the enterprise context
    and supports SNI for multi-tenant TLS setups.
    """
    pool_kwargs = _common_pool_kwargs(conn_cfg)
    pool_kwargs.update({
        "host": conn_cfg.get("host", "localhost"),
        "port": conn_cfg.get("port", 6379),
        "db": conn_cfg.get("db", 0),
        "max_connections": conn_cfg.get("max_connections", 50),
    })
    _apply_ssl(pool_kwargs, conn_cfg)
    pool = redis.ConnectionPool(**pool_kwargs)
    client = redis.Redis(connection_pool=pool)
    logger.info(
        "Enterprise client created: %s:%s (ssl=%s)",
        pool_kwargs["host"], pool_kwargs["port"], conn_cfg.get("ssl", False),
    )
    return client


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

_FACTORIES = {
    "standalone": lambda cfg, **kw: create_standalone_client(cfg),
    "sentinel": lambda cfg, **kw: create_sentinel_client(cfg, **kw),
    "cluster": lambda cfg, **kw: create_cluster_client(cfg),
    "enterprise": lambda cfg, **kw: create_enterprise_client(cfg),
}


def create_client(conn_cfg: Dict[str, Any], **kwargs) -> redis.Redis:
    """Create a Redis client based on ``connection_mode`` in *conn_cfg*.

    Falls back to ``standalone`` when the field is absent for backward
    compatibility.

    Extra *kwargs* are forwarded to the adapter factory (e.g.
    ``replica=True`` for sentinel mode).
    """
    mode = conn_cfg.get("connection_mode", "standalone")
    factory = _FACTORIES.get(mode)
    if factory is None:
        raise ValueError(
            f"Unknown connection_mode '{mode}'. "
            f"Supported: {', '.join(_FACTORIES)}"
        )
    return factory(conn_cfg, **kwargs)


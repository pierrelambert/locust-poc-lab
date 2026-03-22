"""Data seeding utilities for Locust workloads.

Provides generic seeding with pluggable key/value generators and
pipeline batching for efficient bulk loading.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Tuple

import redis

logger = logging.getLogger(__name__)


def seed_data(
    client: redis.Redis,
    key_generator: Callable[[int], str],
    value_generator: Callable[[int], Any],
    key_count: int,
    batch_size: int = 1000,
    command: str = "SET",
    ttl_range: Tuple[int, int] | None = None,
    rng=None,
) -> int:
    """Seed Redis with generated key/value pairs using pipelining.

    Args:
        client: Redis client instance.
        key_generator: Function(index) -> key string.
        value_generator: Function(index) -> value (string, dict, etc.).
        key_count: Total number of keys to seed.
        batch_size: Keys per pipeline batch.
        command: Redis command to use (``SET`` or ``HSET``).
        ttl_range: Optional (min, max) TTL in seconds. Applied per key.
        rng: Random number generator for TTL selection.

    Returns:
        Number of keys seeded.
    """
    import random as _random
    if rng is None:
        rng = _random

    seeded = 0
    start = time.monotonic()

    for batch_start in range(0, key_count, batch_size):
        batch_end = min(batch_start + batch_size, key_count)
        pipe = client.pipeline(transaction=False)

        for i in range(batch_start, batch_end):
            key = key_generator(i)
            value = value_generator(i)

            if command.upper() == "HSET":
                if isinstance(value, dict):
                    pipe.hset(key, mapping=value)
                else:
                    raise ValueError("HSET command requires dict values")
            else:
                pipe.set(key, value)

            if ttl_range:
                ttl = rng.randint(ttl_range[0], ttl_range[1])
                pipe.expire(key, ttl)

        pipe.execute()
        seeded += batch_end - batch_start

        if seeded % (batch_size * 10) == 0 or seeded == key_count:
            logger.info("Seeded %d / %d keys", seeded, key_count)

    elapsed = time.monotonic() - start
    logger.info("Seeding complete: %d keys in %.2f seconds", seeded, elapsed)
    return seeded


def verify_seed(client: redis.Redis, expected_pattern: str, expected_count: int) -> bool:
    """Verify that the expected number of keys exist.

    Uses DBSIZE as a fast check. For pattern-specific verification,
    a SCAN-based count is used.

    Args:
        client: Redis client instance.
        expected_pattern: Key pattern glob (e.g. ``cache:*``).
        expected_count: Expected minimum key count.

    Returns:
        True if verification passes.
    """
    count = 0
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=expected_pattern, count=1000)
        count += len(keys)
        if cursor == 0:
            break

    if count < expected_count:
        logger.error(
            "Seed verification FAILED: found %d keys matching '%s', expected >= %d",
            count, expected_pattern, expected_count,
        )
        return False

    logger.info(
        "Seed verification PASSED: %d keys matching '%s' (expected >= %d)",
        count, expected_pattern, expected_count,
    )
    return True


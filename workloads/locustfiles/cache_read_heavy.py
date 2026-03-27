"""Locustfile for the cache_read_heavy workload.

Business narrative: A product catalog / content cache serving high-volume
read traffic (90 %) with occasional cache-invalidation writes (10 %).

Usage::

    locust -f workloads/locustfiles/cache_read_heavy.py \
           --host http://localhost \
           --env WORKLOAD_PROFILE=workloads/profiles/cache_read_heavy.yaml
"""

import json
import logging
import os
import random
import time

from locust import User, between, events, task

from workloads.lib.config import load_profile
from workloads.lib.connections import get_redis_client, reset_pool
from workloads.lib.metrics import redis_command_timer
from workloads.lib.seeding import seed_data, verify_seed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile & constants
# ---------------------------------------------------------------------------
PROFILE_PATH = os.environ.get(
    "WORKLOAD_PROFILE", "workloads/profiles/cache_read_heavy.yaml"
)

CATEGORIES = [
    "electronics", "clothing", "home", "sports", "toys",
    "books", "food", "beauty", "automotive", "garden",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _key_for_index(index: int) -> str:
    """Deterministic key from index."""
    cat = CATEGORIES[index % len(CATEGORIES)]
    return f"cache:{cat}:{index}"


def _generate_json_payload(index: int, rng: random.Random, min_size: int, max_size: int) -> str:
    """Generate a JSON payload within the configured size range."""
    base = {
        "id": index,
        "category": CATEGORIES[index % len(CATEGORIES)],
        "name": f"item-{index}",
        "price": round(rng.uniform(1.0, 999.99), 2),
        "in_stock": rng.choice([True, False]),
    }
    payload = json.dumps(base)
    # Pad to reach minimum size
    if len(payload) < min_size:
        base["description"] = "x" * (min_size - len(payload))
        payload = json.dumps(base)
    # Truncate if over max (unlikely with controlled padding)
    return payload[:max_size]


# ---------------------------------------------------------------------------
# Locust lifecycle events
# ---------------------------------------------------------------------------

_seeded = False


@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
    """Seed data once at the start of the test run."""
    global _seeded
    if _seeded:
        return

    profile = load_profile(PROFILE_PATH)
    wl = profile["workload"]
    conn_cfg = wl["connection"]
    seed_cfg = wl.get("seeding", {})
    data_cfg = wl["data_config"]

    client = get_redis_client(conn_cfg)

    if seed_cfg.get("enabled", True):
        rng = random.Random(seed_cfg.get("random_seed", 42))
        key_count = seed_cfg.get("key_count", 100_000)
        batch_size = seed_cfg.get("batch_size", 1000)

        seed_data(
            client=client,
            key_generator=_key_for_index,
            value_generator=lambda i: _generate_json_payload(
                i, rng, data_cfg["value_size_min"], data_cfg["value_size_max"]
            ),
            key_count=key_count,
            batch_size=batch_size,
            command="SET",
            ttl_range=(data_cfg["ttl_min"], data_cfg["ttl_max"]),
            rng=rng,
        )

        if seed_cfg.get("verify_after_seed", True):
            ok = verify_seed(client, "cache:*", key_count)
            if not ok:
                raise RuntimeError("Seed verification failed — aborting test")

    _seeded = True
    logger.info("cache_read_heavy: seeding complete, workload starting")


@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    reset_pool()


# ---------------------------------------------------------------------------
# Locust User
# ---------------------------------------------------------------------------

class CacheReadHeavyUser(User):
    """Simulates a product-catalog cache consumer."""

    # Default think time — overridden in on_start from profile values
    wait_time = between(0.001, 0.005)

    def on_start(self):
        profile = load_profile(PROFILE_PATH)
        wl = profile["workload"]
        self.conn_cfg = wl["connection"]
        self.key_cfg = wl["key_config"]
        self.data_cfg = wl["data_config"]
        self.traffic_cfg = wl["traffic_config"]

        # Use think time from profile (milliseconds → seconds)
        think_min = self.traffic_cfg.get("think_time_min_ms", 1) / 1000.0
        think_max = self.traffic_cfg.get("think_time_max_ms", 5) / 1000.0
        self.wait_time = lambda: random.uniform(think_min, think_max)

        self.rng = random.Random()
        self.key_space = self.key_cfg["key_space_size"]
        self.read_ratio = self.traffic_cfg["read_ratio"]
        self.client = get_redis_client(self.conn_cfg)

    # ---- tasks ----

    @task(90)
    def read_cache(self):
        """GET or MGET a cache key (read path)."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _key_for_index(idx)

        # 80 % single GET, 20 % MGET batch of 5
        if self.rng.random() < 0.80:
            with redis_command_timer("GET", key=key):
                self.client.get(key)
        else:
            indices = [self.rng.randint(0, self.key_space - 1) for _ in range(5)]
            keys = [_key_for_index(i) for i in indices]
            with redis_command_timer("MGET", key=keys[0]):
                self.client.mget(keys)

    @task(10)
    def write_cache(self):
        """SET with TTL or DEL a cache key (write path)."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _key_for_index(idx)

        if self.rng.random() < 0.80:
            # SET with TTL
            payload = _generate_json_payload(
                idx, self.rng,
                self.data_cfg["value_size_min"],
                self.data_cfg["value_size_max"],
            )
            ttl = self.rng.randint(self.data_cfg["ttl_min"], self.data_cfg["ttl_max"])
            with redis_command_timer("SET", key=key):
                self.client.set(key, payload, ex=ttl)
        else:
            # DEL (cache invalidation)
            with redis_command_timer("DEL", key=key):
                self.client.delete(key)


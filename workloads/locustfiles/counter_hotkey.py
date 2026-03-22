"""Locustfile for the counter_hotkey workload.

Business narrative: Inventory counters, rate limiters, or real-time metrics
where a subset of keys receives disproportionate write traffic. Demonstrates
hot-key pressure, latency spikes under contention, and failover sensitivity
when write-heavy keys move between nodes.

Usage::

    locust -f workloads/locustfiles/counter_hotkey.py \
           --host http://localhost \
           --env WORKLOAD_PROFILE=workloads/profiles/counter_hotkey.yaml
"""

import logging
import math
import os
import random

from locust import User, between, events, task

from workloads.lib.config import load_profile
from workloads.lib.connections import get_redis_client, reset_pool
from workloads.lib.metrics import redis_command_timer
from workloads.lib.seeding import seed_data, verify_seed

logger = logging.getLogger(__name__)

PROFILE_PATH = os.environ.get(
    "WORKLOAD_PROFILE", "workloads/profiles/counter_hotkey.yaml"
)

SCOPES = ["inventory", "ratelimit", "metrics", "clicks", "views"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _counter_key(index: int) -> str:
    scope = SCOPES[index % len(SCOPES)]
    return f"counter:{scope}:{index}"


def _generate_counter_value(index: int) -> str:
    """Return a string integer for SET seeding."""
    return "0"


def _pick_key_index(rng: random.Random, key_space: int, hot_key_count: int,
                    hot_key_pct: int) -> int:
    """Select a key index using Zipfian-like hot-key distribution.

    ``hot_key_pct`` percent of requests target the first ``hot_key_count`` keys.
    """
    if hot_key_count > 0 and rng.randint(1, 100) <= hot_key_pct:
        return rng.randint(0, hot_key_count - 1)
    return rng.randint(0, key_space - 1)


# ---------------------------------------------------------------------------
# Locust lifecycle events
# ---------------------------------------------------------------------------

_seeded = False


@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
    global _seeded
    if _seeded:
        return

    profile = load_profile(PROFILE_PATH)
    wl = profile["workload"]
    conn_cfg = wl["connection"]
    seed_cfg = wl.get("seeding", {})

    client = get_redis_client(conn_cfg)

    if seed_cfg.get("enabled", True):
        rng = random.Random(seed_cfg.get("random_seed", 42))
        key_count = seed_cfg.get("key_count", 10_000)
        batch_size = seed_cfg.get("batch_size", 1000)

        seed_data(
            client=client,
            key_generator=_counter_key,
            value_generator=_generate_counter_value,
            key_count=key_count,
            batch_size=batch_size,
            command="SET",
            rng=rng,
        )

        if seed_cfg.get("verify_after_seed", True):
            ok = verify_seed(client, "counter:*", key_count)
            if not ok:
                raise RuntimeError("Seed verification failed — aborting test")

    _seeded = True
    logger.info("counter_hotkey: seeding complete, workload starting")


@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    reset_pool()


# ---------------------------------------------------------------------------
# Locust User
# ---------------------------------------------------------------------------

class CounterHotkeyUser(User):
    """Simulates counter/rate-limiter traffic with hot-key skew (60/40 r/w)."""

    wait_time = between(0.001, 0.005)

    def on_start(self):
        profile = load_profile(PROFILE_PATH)
        wl = profile["workload"]
        self.conn_cfg = wl["connection"]
        self.key_cfg = wl["key_config"]
        self.traffic_cfg = wl["traffic_config"]

        self.rng = random.Random()
        self.key_space = self.key_cfg["key_space_size"]
        self.hot_key_count = self.key_cfg.get("hot_key_count", 100)
        self.hot_key_pct = self.key_cfg.get("hot_key_percentage", 80)
        self.client = get_redis_client(self.conn_cfg)

    def _pick(self) -> int:
        return _pick_key_index(self.rng, self.key_space,
                               self.hot_key_count, self.hot_key_pct)

    # ---- read tasks (weight 60) ----

    @task(45)
    def read_counter(self):
        """GET — read a single counter."""
        key = _counter_key(self._pick())
        with redis_command_timer("GET", key=key):
            self.client.get(key)

    @task(15)
    def read_batch(self):
        """MGET — read a batch of 5 counters."""
        keys = [_counter_key(self._pick()) for _ in range(5)]
        with redis_command_timer("MGET", key=keys[0]):
            self.client.mget(keys)

    # ---- write tasks (weight 40) ----

    @task(20)
    def increment_counter(self):
        """INCR — atomic increment."""
        key = _counter_key(self._pick())
        with redis_command_timer("INCR", key=key):
            self.client.incr(key)

    @task(10)
    def increment_by(self):
        """INCRBY — increment by random amount."""
        key = _counter_key(self._pick())
        amount = self.rng.randint(1, 100)
        with redis_command_timer("INCRBY", key=key):
            self.client.incrby(key, amount)

    @task(5)
    def decrement_counter(self):
        """DECR — atomic decrement."""
        key = _counter_key(self._pick())
        with redis_command_timer("DECR", key=key):
            self.client.decr(key)

    @task(5)
    def reset_counter(self):
        """SET — reset counter to zero."""
        key = _counter_key(self._pick())
        with redis_command_timer("SET", key=key):
            self.client.set(key, 0)


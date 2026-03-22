"""Locustfile for the session_mixed workload.

Business narrative: A login and session-state store where users authenticate,
read session data on every request, and periodically update session attributes.
Demonstrates reconnect behavior and stale/lost session risk during failover.

Usage::

    locust -f workloads/locustfiles/session_mixed.py \
           --host http://localhost \
           --env WORKLOAD_PROFILE=workloads/profiles/session_mixed.yaml
"""

import logging
import os
import random
import string
import uuid

from locust import User, between, events, task

from workloads.lib.config import load_profile
from workloads.lib.connections import get_redis_client, reset_pool
from workloads.lib.metrics import redis_command_timer
from workloads.lib.seeding import seed_data, verify_seed

logger = logging.getLogger(__name__)

PROFILE_PATH = os.environ.get(
    "WORKLOAD_PROFILE", "workloads/profiles/session_mixed.yaml"
)

ROLES = ["admin", "editor", "viewer", "guest", "moderator"]
SESSION_TTL = 1800  # seconds

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_key(index: int) -> str:
    return f"session:{index}"


def _generate_session_hash(index: int, rng: random.Random) -> dict:
    """Generate a realistic session hash with 5-10 fields."""
    fields = {
        "user_id": str(index),
        "role": rng.choice(ROLES),
        "preferences": f'{{"theme":"{rng.choice(["dark","light"])}","lang":"{rng.choice(["en","fr","de","es"])}"}}',
        "last_active": str(rng.randint(1700000000, 1711000000)),
        "csrf_token": uuid.UUID(int=rng.getrandbits(128)).hex,
    }
    # Add 0-5 extra fields to vary hash size (5-10 total)
    extra_count = rng.randint(0, 5)
    for j in range(extra_count):
        fields[f"attr_{j}"] = "".join(rng.choices(string.ascii_lowercase, k=rng.randint(10, 50)))
    return fields


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
        key_count = seed_cfg.get("key_count", 50_000)
        batch_size = seed_cfg.get("batch_size", 1000)

        seed_data(
            client=client,
            key_generator=_session_key,
            value_generator=lambda i: _generate_session_hash(i, rng),
            key_count=key_count,
            batch_size=batch_size,
            command="HSET",
            ttl_range=(SESSION_TTL, SESSION_TTL),
            rng=rng,
        )

        if seed_cfg.get("verify_after_seed", True):
            ok = verify_seed(client, "session:*", key_count)
            if not ok:
                raise RuntimeError("Seed verification failed — aborting test")

    _seeded = True
    logger.info("session_mixed: seeding complete, workload starting")


@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    reset_pool()


# ---------------------------------------------------------------------------
# Locust User
# ---------------------------------------------------------------------------

class SessionMixedUser(User):
    """Simulates a session-store consumer with 70/30 read/write split."""

    wait_time = between(0.010, 0.050)

    def on_start(self):
        profile = load_profile(PROFILE_PATH)
        wl = profile["workload"]
        self.conn_cfg = wl["connection"]
        self.key_cfg = wl["key_config"]
        self.data_cfg = wl["data_config"]
        self.traffic_cfg = wl["traffic_config"]

        self.rng = random.Random()
        self.key_space = self.key_cfg["key_space_size"]
        self.client = get_redis_client(self.conn_cfg)

    # ---- read tasks (weight 70) ----

    @task(50)
    def read_full_session(self):
        """HGETALL — fetch entire session hash."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        with redis_command_timer("HGETALL", key=key):
            self.client.hgetall(key)

    @task(15)
    def read_single_field(self):
        """HGET — fetch a single session field."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        field = self.rng.choice(["user_id", "role", "preferences", "last_active", "csrf_token"])
        with redis_command_timer("HGET", key=key):
            self.client.hget(key, field)

    @task(5)
    def check_ttl(self):
        """TTL — check remaining session lifetime."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        with redis_command_timer("TTL", key=key):
            self.client.ttl(key)

    # ---- write tasks (weight 30) ----

    @task(12)
    def update_single_field(self):
        """HSET — update one session attribute."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        with redis_command_timer("HSET", key=key):
            self.client.hset(key, "last_active", str(int(self.rng.random() * 1e10)))

    @task(10)
    def update_multiple_fields(self):
        """HMSET — update several session attributes at once."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        updates = {
            "last_active": str(int(self.rng.random() * 1e10)),
            "csrf_token": uuid.UUID(int=self.rng.getrandbits(128)).hex,
        }
        with redis_command_timer("HMSET", key=key):
            self.client.hset(key, mapping=updates)

    @task(5)
    def refresh_expiry(self):
        """EXPIRE — refresh session TTL."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        with redis_command_timer("EXPIRE", key=key):
            self.client.expire(key, SESSION_TTL)

    @task(3)
    def delete_session(self):
        """DEL — simulate logout / session invalidation."""
        idx = self.rng.randint(0, self.key_space - 1)
        key = _session_key(idx)
        with redis_command_timer("DEL", key=key):
            self.client.delete(key)


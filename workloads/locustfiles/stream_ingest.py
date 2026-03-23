"""Locustfile for the stream_ingest workload.

Business narrative: An event or order pipeline where producers write events
to Redis Streams and consumers read them in consumer groups. Demonstrates
write durability, consumer lag during disruption, and recovery pacing when
the producer resumes after failover.

Usage::

    locust -f workloads/locustfiles/stream_ingest.py \
           --host http://localhost \
           --env WORKLOAD_PROFILE=workloads/profiles/stream_ingest.yaml
"""

import json
import logging
import os
import random
import time
import uuid

from locust import User, between, events, task

from workloads.lib.config import load_profile
from workloads.lib.connections import get_redis_client, reset_pool
from workloads.lib.metrics import redis_command_timer

logger = logging.getLogger(__name__)

PROFILE_PATH = os.environ.get(
    "WORKLOAD_PROFILE", "workloads/profiles/stream_ingest.yaml"
)

STREAM_COUNT = 10
TOPICS = ["orders", "events", "logs", "clicks", "payments",
          "notifications", "metrics", "alerts", "updates", "signals"]
CONSUMER_GROUP = "cg-locust"
MAX_STREAM_LEN = 100_000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stream_key(stream_index: int) -> str:
    topic = TOPICS[stream_index % len(TOPICS)]
    partition = stream_index // len(TOPICS)
    return f"stream:{topic}:{partition}"


def _generate_event_payload(rng: random.Random, min_size: int,
                            max_size: int) -> dict:
    """Generate a JSON event payload as a flat dict for XADD."""
    base = {
        "event_id": uuid.UUID(int=rng.getrandbits(128)).hex,
        "timestamp": str(int(time.time() * 1000)),
        "source": rng.choice(["web", "mobile", "api", "batch"]),
        "type": rng.choice(["create", "update", "delete", "read"]),
    }
    payload = json.dumps(base)
    if len(payload) < min_size:
        base["data"] = "x" * (min_size - len(payload))
    return base


# ---------------------------------------------------------------------------
# Seeding (create streams and consumer groups)
# ---------------------------------------------------------------------------

_seeded = False


def _seed_streams(client, stream_count: int, rng: random.Random,
                  min_size: int, max_size: int) -> None:
    """Create streams with initial entries and set up consumer groups."""
    start = time.monotonic()
    for s in range(stream_count):
        key = _stream_key(s)
        # Add a seed entry so the stream exists
        payload = _generate_event_payload(rng, min_size, max_size)
        client.xadd(key, payload, maxlen=MAX_STREAM_LEN)
        # Create consumer groups (1-3 per stream)
        group_count = (s % 3) + 1
        for g in range(group_count):
            group_name = f"{CONSUMER_GROUP}-{g}"
            try:
                client.xgroup_create(key, group_name, id="0", mkstream=True)
            except Exception:
                # Group may already exist
                pass
        logger.info("Stream %s seeded with %d consumer group(s)", key, group_count)

    elapsed = time.monotonic() - start
    logger.info("Stream seeding complete: %d streams in %.2fs", stream_count, elapsed)


@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
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
        _seed_streams(client, STREAM_COUNT, rng,
                      data_cfg["value_size_min"], data_cfg["value_size_max"])

    _seeded = True
    logger.info("stream_ingest: seeding complete, workload starting")


@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    reset_pool()


# ---------------------------------------------------------------------------
# Locust User
# ---------------------------------------------------------------------------

class StreamIngestUser(User):
    """Simulates stream producer/consumer traffic with 50/50 read/write."""

    wait_time = between(0.002, 0.010)

    def on_start(self):
        profile = load_profile(PROFILE_PATH)
        wl = profile["workload"]
        self.conn_cfg = wl["connection"]
        self.key_cfg = wl["key_config"]
        self.data_cfg = wl["data_config"]
        self.traffic_cfg = wl["traffic_config"]

        self.rng = random.Random()
        self.stream_count = STREAM_COUNT
        self.client = get_redis_client(self.conn_cfg)
        self.consumer_name = f"consumer-{uuid.uuid4().hex[:8]}"

    def _random_stream(self) -> str:
        return _stream_key(self.rng.randint(0, self.stream_count - 1))


    # ---- write tasks (weight 50) ----

    @task(50)
    def produce_event(self):
        """XADD — write an event to a stream with MAXLEN trimming."""
        key = self._random_stream()
        payload = _generate_event_payload(
            self.rng, self.data_cfg["value_size_min"],
            self.data_cfg["value_size_max"],
        )
        with redis_command_timer("XADD", key=key):
            self.client.xadd(key, payload, maxlen=MAX_STREAM_LEN, approximate=True)

    # ---- read tasks (weight 50) ----

    @task(30)
    def consume_events(self):
        """XREADGROUP — read pending events from a consumer group."""
        stream_idx = self.rng.randint(0, self.stream_count - 1)
        key = _stream_key(stream_idx)
        group_id = stream_idx % 3
        group_name = f"{CONSUMER_GROUP}-{group_id}"
        with redis_command_timer("XREADGROUP", key=key):
            messages = self.client.xreadgroup(
                group_name, self.consumer_name,
                {key: ">"}, count=10, block=100,
            )
        # ACK received messages
        if messages:
            for stream_name, entries in messages:
                if entries:
                    msg_ids = [entry[0] for entry in entries]
                    with redis_command_timer("XACK", key=key):
                        self.client.xack(key, group_name, *msg_ids)

    @task(10)
    def check_stream_length(self):
        """XLEN — check stream length."""
        key = self._random_stream()
        with redis_command_timer("XLEN", key=key):
            self.client.xlen(key)

    @task(10)
    def check_group_info(self):
        """XINFO GROUPS — check consumer group state."""
        key = self._random_stream()
        with redis_command_timer("XINFO GROUPS", key=key):
            self.client.xinfo_groups(key)

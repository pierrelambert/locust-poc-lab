"""Locustfile for the leaderboard_sorted_set workload.

Business narrative: A ranking system for gaming, e-commerce, or social
platforms where scores are updated frequently and leaderboard queries
retrieve top-N or rank-range results. Demonstrates sorted-set update
latency, cluster balance with large sorted sets, and recovery behavior.

Usage::

    locust -f workloads/locustfiles/leaderboard_sorted_set.py \
           --host http://localhost \
           --env WORKLOAD_PROFILE=workloads/profiles/leaderboard_sorted_set.yaml
"""

import logging
import os
import random
import time

from locust import User, between, events, task

from workloads.lib.config import load_profile
from workloads.lib.connections import get_redis_client, reset_pool
from workloads.lib.metrics import redis_command_timer

logger = logging.getLogger(__name__)

PROFILE_PATH = os.environ.get(
    "WORKLOAD_PROFILE", "workloads/profiles/leaderboard_sorted_set.yaml"
)

BOARD_COUNT = 50
MEMBERS_PER_BOARD = 10_000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _board_key(board_id: int) -> str:
    return f"leaderboard:{board_id}"


def _member_id(member_index: int) -> str:
    return f"user:{member_index}"


# ---------------------------------------------------------------------------
# Seeding (custom — sorted sets not supported by generic seed_data)
# ---------------------------------------------------------------------------

_seeded = False


def _seed_leaderboards(client, board_count: int, members_per_board: int,
                       batch_size: int, rng: random.Random) -> None:
    """Pre-populate sorted sets with randomized scores using pipelining."""
    start = time.monotonic()
    for board_id in range(board_count):
        key = _board_key(board_id)
        for batch_start in range(0, members_per_board, batch_size):
            batch_end = min(batch_start + batch_size, members_per_board)
            pipe = client.pipeline(transaction=False)
            for m in range(batch_start, batch_end):
                score = round(rng.uniform(0, 1_000_000), 2)
                pipe.zadd(key, {_member_id(m): score})
            pipe.execute()
        if (board_id + 1) % 10 == 0 or board_id == board_count - 1:
            logger.info("Seeded %d / %d leaderboards", board_id + 1, board_count)

    elapsed = time.monotonic() - start
    logger.info("Leaderboard seeding complete: %d boards × %d members in %.2fs",
                board_count, members_per_board, elapsed)


def _verify_leaderboards(client, board_count: int, members_per_board: int) -> bool:
    """Verify cardinality of each sorted set."""
    for board_id in range(board_count):
        card = client.zcard(_board_key(board_id))
        if card < members_per_board:
            logger.error("Board %d has %d members, expected >= %d",
                         board_id, card, members_per_board)
            return False
    logger.info("Leaderboard verification PASSED: %d boards verified", board_count)
    return True


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
        batch_size = seed_cfg.get("batch_size", 1000)
        _seed_leaderboards(client, BOARD_COUNT, MEMBERS_PER_BOARD, batch_size, rng)

        if seed_cfg.get("verify_after_seed", True):
            if not _verify_leaderboards(client, BOARD_COUNT, MEMBERS_PER_BOARD):
                raise RuntimeError("Seed verification failed — aborting test")

    _seeded = True
    logger.info("leaderboard_sorted_set: seeding complete, workload starting")


@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    reset_pool()


# ---------------------------------------------------------------------------
# Locust User
# ---------------------------------------------------------------------------

class LeaderboardSortedSetUser(User):
    """Simulates leaderboard traffic with 80/20 read/write split."""

    wait_time = between(0.010, 0.030)

    def on_start(self):
        profile = load_profile(PROFILE_PATH)
        wl = profile["workload"]
        self.conn_cfg = wl["connection"]
        self.key_cfg = wl["key_config"]
        self.traffic_cfg = wl["traffic_config"]

        self.rng = random.Random()
        self.board_count = BOARD_COUNT
        self.members_per_board = MEMBERS_PER_BOARD
        self.client = get_redis_client(self.conn_cfg)

    def _random_board(self) -> str:
        return _board_key(self.rng.randint(0, self.board_count - 1))

    def _random_member(self) -> str:
        return _member_id(self.rng.randint(0, self.members_per_board - 1))

    # ---- read tasks (weight 80) ----

    @task(30)
    def get_top_n(self):
        """ZREVRANGE — fetch top 10 from a leaderboard."""
        key = self._random_board()
        with redis_command_timer("ZREVRANGE", key=key):
            self.client.zrevrange(key, 0, 9, withscores=True)

    @task(20)
    def get_range(self):
        """ZRANGE — fetch a rank range (positions 50-100)."""
        key = self._random_board()
        start = self.rng.randint(0, self.members_per_board - 51)
        with redis_command_timer("ZRANGE", key=key):
            self.client.zrange(key, start, start + 49, withscores=True)

    @task(15)
    def get_rank(self):
        """ZRANK — get a member's rank."""
        key = self._random_board()
        member = self._random_member()
        with redis_command_timer("ZRANK", key=key):
            self.client.zrank(key, member)

    @task(10)
    def get_score(self):
        """ZSCORE — get a member's score."""
        key = self._random_board()
        member = self._random_member()
        with redis_command_timer("ZSCORE", key=key):
            self.client.zscore(key, member)

    @task(5)
    def get_cardinality(self):
        """ZCARD — get leaderboard size."""
        key = self._random_board()
        with redis_command_timer("ZCARD", key=key):
            self.client.zcard(key)

    # ---- write tasks (weight 20) ----

    @task(10)
    def update_score(self):
        """ZADD — set a new score for a member."""
        key = self._random_board()
        member = self._random_member()
        score = round(self.rng.uniform(0, 1_000_000), 2)
        with redis_command_timer("ZADD", key=key):
            self.client.zadd(key, {member: score})

    @task(7)
    def increment_score(self):
        """ZINCRBY — increment a member's score."""
        key = self._random_board()
        member = self._random_member()
        delta = round(self.rng.uniform(-100, 500), 2)
        with redis_command_timer("ZINCRBY", key=key):
            self.client.zincrby(key, delta, member)

    @task(3)
    def remove_member(self):
        """ZREM — remove a member from a leaderboard."""
        key = self._random_board()
        member = self._random_member()
        with redis_command_timer("ZREM", key=key):
            self.client.zrem(key, member)


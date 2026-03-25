"""Smoke tests: Docker-based OSS Sentinel stack integration test.

These tests require Docker and are skipped by default.
Run with: pytest tests/smoke/test_docker_oss_sentinel.py -m docker
"""

import subprocess
import time

import pytest

pytestmark = pytest.mark.docker

COMPOSE_FILE = "infra/docker/oss-sentinel/docker-compose.yml"
PROJECT_NAME = "oss-sentinel-smoke"


def _compose(*args):
    """Run a docker compose command and return the result."""
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def _redis_cli(*args, port=6380):
    """Run redis-cli and return the result."""
    cmd = ["redis-cli", "-p", str(port), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)


@pytest.fixture(scope="module")
def sentinel_stack():
    """Start the OSS Sentinel stack, yield, then tear it down."""
    # Start the stack
    result = _compose("up", "-d")
    assert result.returncode == 0, f"Failed to start stack: {result.stderr}"

    # Wait for Redis primary to be ready
    for attempt in range(30):
        ping = _redis_cli("PING")
        if ping.returncode == 0 and "PONG" in ping.stdout:
            break
        time.sleep(1)
    else:
        _compose("down", "-v")
        pytest.fail("Redis primary did not become ready within 30 seconds")

    yield

    # Tear down
    _compose("down", "-v")


def test_redis_primary_ping(sentinel_stack):
    """Redis primary should respond to PING."""
    result = _redis_cli("PING")
    assert result.returncode == 0
    assert "PONG" in result.stdout


def test_sentinel_ping(sentinel_stack):
    """At least one Sentinel should respond to PING."""
    result = _redis_cli("PING", port=26379)
    assert result.returncode == 0
    assert "PONG" in result.stdout


def test_redis_set_get(sentinel_stack):
    """Basic SET/GET should work on the primary."""
    set_result = _redis_cli("SET", "smoke_test_key", "smoke_test_value")
    assert set_result.returncode == 0

    get_result = _redis_cli("GET", "smoke_test_key")
    assert get_result.returncode == 0
    assert "smoke_test_value" in get_result.stdout


def test_sentinel_knows_master(sentinel_stack):
    """Sentinel should know about the master."""
    result = _redis_cli("SENTINEL", "masters", port=26379)
    assert result.returncode == 0
    # Sentinel masters command should return data about the monitored master
    assert len(result.stdout.strip()) > 0


def test_short_workload_run(sentinel_stack):
    """Run a very short Locust workload (headless, 2 users, 5 seconds)."""
    cmd = [
        ".venv/bin/python", "-m", "locust",
        "-f", "workloads/locustfiles/cache_read_heavy.py",
        "--host", "http://localhost",
        "--headless",
        "-u", "2",
        "-r", "2",
        "-t", "5s",
        "--stop-timeout", "2",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **__import__("os").environ,
            "WORKLOAD_PROFILE": "workloads/profiles/cache_read_heavy.yaml",
        },
    )
    # Locust should complete without crashing (exit code 0 or 1 for some failures is ok)
    assert result.returncode in (0, 1), f"Locust crashed: {result.stderr}"


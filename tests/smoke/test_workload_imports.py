"""Smoke tests: verify all 5 locustfiles import without errors."""

import importlib
import sys

import pytest

LOCUSTFILE_MODULES = [
    "workloads.locustfiles.cache_read_heavy",
    "workloads.locustfiles.counter_hotkey",
    "workloads.locustfiles.leaderboard_sorted_set",
    "workloads.locustfiles.session_mixed",
    "workloads.locustfiles.stream_ingest",
]


@pytest.mark.parametrize("module_path", LOCUSTFILE_MODULES)
def test_locustfile_imports(module_path):
    """Each locustfile should import without raising."""
    mod = importlib.import_module(module_path)
    assert mod is not None


@pytest.mark.parametrize("module_path", LOCUSTFILE_MODULES)
def test_locustfile_has_user_class(module_path):
    """Each locustfile should expose at least one Locust User subclass."""
    mod = importlib.import_module(module_path)
    from locust import User as LocustUser

    user_classes = [
        obj
        for name, obj in vars(mod).items()
        if isinstance(obj, type) and issubclass(obj, LocustUser) and obj is not LocustUser
    ]
    assert len(user_classes) >= 1, f"{module_path} has no Locust User subclass"


def test_lib_modules_import():
    """Core library modules should import cleanly."""
    for mod_name in [
        "workloads.lib.config",
        "workloads.lib.connections",
        "workloads.lib.metrics",
        "workloads.lib.seeding",
        "workloads.lib.topology_clients",
    ]:
        mod = importlib.import_module(mod_name)
        assert mod is not None


def test_cache_read_heavy_instance_wait_time_callable(monkeypatch):
    """cache_read_heavy should install an instance wait_time callable."""
    mod = importlib.import_module("workloads.locustfiles.cache_read_heavy")

    monkeypatch.setattr(
        mod,
        "load_profile",
        lambda _path: {
            "workload": {
                "connection": {},
                "key_config": {"key_space_size": 10},
                "data_config": {},
                "traffic_config": {
                    "read_ratio": 90,
                    "think_time_min_ms": 10,
                    "think_time_max_ms": 20,
                },
            }
        },
    )
    monkeypatch.setattr(mod, "get_redis_client", lambda _cfg: object())

    user = mod.CacheReadHeavyUser.__new__(mod.CacheReadHeavyUser)
    user.on_start()

    wait_seconds = user.wait_time()
    assert 0.01 <= wait_seconds <= 0.02


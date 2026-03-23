"""Smoke tests: validate all profile YAMLs have the required schema fields."""

from pathlib import Path

import pytest
import yaml

PROFILES_DIR = Path("workloads/profiles")

PROFILE_FILES = sorted(PROFILES_DIR.glob("*.yaml"))

# Required top-level and nested fields every profile must have
REQUIRED_SECTIONS = ["name", "description", "connection", "key_config", "data_config", "traffic_config"]

REQUIRED_CONNECTION_FIELDS = [
    "connection_mode",
    "host",
    "port",
]

REQUIRED_KEY_CONFIG_FIELDS = [
    "pattern",
    "key_space_size",
]

REQUIRED_DATA_CONFIG_FIELDS = [
    "value_size_min",
    "value_size_max",
]

REQUIRED_TRAFFIC_CONFIG_FIELDS = [
    "read_ratio",
    "write_ratio",
]


def _load_profile(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_has_workload_key(profile_path):
    """Every profile YAML must have a top-level 'workload' key."""
    data = _load_profile(profile_path)
    assert "workload" in data, f"{profile_path.name} missing top-level 'workload' key"


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_required_sections(profile_path):
    """Every profile must have the required sections under 'workload'."""
    wl = _load_profile(profile_path)["workload"]
    for section in REQUIRED_SECTIONS:
        assert section in wl, f"{profile_path.name} missing workload.{section}"


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_connection_fields(profile_path):
    """Connection section must have connection_mode, host, port."""
    conn = _load_profile(profile_path)["workload"]["connection"]
    for field in REQUIRED_CONNECTION_FIELDS:
        assert field in conn, f"{profile_path.name} missing connection.{field}"


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_connection_mode_valid(profile_path):
    """connection_mode must be one of the supported values."""
    conn = _load_profile(profile_path)["workload"]["connection"]
    valid_modes = {"standalone", "sentinel", "cluster", "enterprise"}
    assert conn["connection_mode"] in valid_modes, (
        f"{profile_path.name} has invalid connection_mode: {conn['connection_mode']}"
    )


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_key_config_fields(profile_path):
    """key_config must have pattern and key_space_size."""
    kc = _load_profile(profile_path)["workload"]["key_config"]
    for field in REQUIRED_KEY_CONFIG_FIELDS:
        assert field in kc, f"{profile_path.name} missing key_config.{field}"


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_data_config_fields(profile_path):
    """data_config must have value_size_min and value_size_max."""
    dc = _load_profile(profile_path)["workload"]["data_config"]
    for field in REQUIRED_DATA_CONFIG_FIELDS:
        assert field in dc, f"{profile_path.name} missing data_config.{field}"


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_traffic_config_fields(profile_path):
    """traffic_config must have read_ratio and write_ratio."""
    tc = _load_profile(profile_path)["workload"]["traffic_config"]
    for field in REQUIRED_TRAFFIC_CONFIG_FIELDS:
        assert field in tc, f"{profile_path.name} missing traffic_config.{field}"


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
def test_profile_ratios_sum(profile_path):
    """read_ratio + write_ratio should equal 100."""
    tc = _load_profile(profile_path)["workload"]["traffic_config"]
    total = tc["read_ratio"] + tc["write_ratio"]
    assert total == 100, f"{profile_path.name} ratios sum to {total}, expected 100"


"""Load and validate YAML workload profiles with environment variable substitution."""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict


_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${VAR_NAME} references in strings."""
    if isinstance(value, str):
        def _replace(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                raise ValueError(f"Environment variable '{var_name}' is not set")
            return env_val
        return _ENV_VAR_RE.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


def load_profile(profile_path: str) -> Dict[str, Any]:
    """Load a YAML workload profile, substituting environment variables.

    Args:
        profile_path: Path to the YAML profile file.

    Returns:
        Parsed and validated profile dictionary.
    """
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw or "workload" not in raw:
        raise ValueError(f"Profile must contain a top-level 'workload' key: {profile_path}")

    profile = _substitute_env_vars(raw)
    workload = profile["workload"]

    # Validate required sections
    required_sections = ["name", "connection", "key_config", "data_config", "traffic_config"]
    for section in required_sections:
        if section not in workload:
            raise ValueError(f"Profile missing required section: workload.{section}")

    # Validate replica_reads is explicitly declared (design rule 3)
    if "replica_reads" not in workload:
        raise ValueError("Profile must explicitly declare 'workload.replica_reads'")
    if "enabled" not in workload["replica_reads"]:
        raise ValueError("Profile must explicitly declare 'workload.replica_reads.enabled'")

    return profile


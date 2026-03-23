"""Smoke tests: run the exporter on synthetic data and verify output."""

import csv
import json
import os
import tempfile
from pathlib import Path

import pytest

from observability.exporters.run_summary_exporter import (
    build_run_summary,
    render_markdown,
)


def _create_synthetic_run_dir(tmp_path: Path) -> Path:
    """Create a minimal synthetic run directory with Locust-style outputs."""
    run_dir = tmp_path / "test_run_001"
    run_dir.mkdir()

    # environment.json
    env_data = {
        "run_id": "test_run_001",
        "platform": "oss-sentinel",
        "locust_file": "cache_read_heavy.py",
        "workload_profile": "cache_read_heavy.yaml",
        "locust_users": 10,
        "locust_spawn_rate": 2,
        "locust_host": "http://localhost",
        "redis_version": "7.2.4",
        "timestamp": "2025-01-01T00:00:00Z",
    }
    (run_dir / "environment.json").write_text(json.dumps(env_data))

    # Locust stats CSV
    stats_rows = [
        {
            "Type": "GET",
            "Name": "Aggregated",
            "Request Count": "1000",
            "Failure Count": "5",
            "Median Response Time": "2",
            "Average Response Time": "3.5",
            "Min Response Time": "1",
            "Max Response Time": "50",
            "Average Content Size": "100",
            "Requests/s": "500.0",
            "Failures/s": "2.5",
            "50%": "2",
            "66%": "3",
            "75%": "4",
            "80%": "5",
            "90%": "8",
            "95%": "12",
            "98%": "20",
            "99%": "30",
            "99.9%": "40",
            "99.99%": "45",
            "100%": "50",
        }
    ]
    stats_file = run_dir / "test_run_001_stats.csv"
    with open(stats_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(stats_rows[0].keys()))
        writer.writeheader()
        writer.writerows(stats_rows)

    # events.jsonl
    events_data = [
        {"timestamp": "2025-01-01T00:00:00Z", "epoch": 1735689600, "event": "test_start", "detail": "started"},
        {"timestamp": "2025-01-01T00:05:00Z", "epoch": 1735689900, "event": "test_stop", "detail": "stopped"},
    ]
    events_lines = "\n".join(json.dumps(e) for e in events_data)
    (run_dir / "events.jsonl").write_text(events_lines)

    return run_dir


def test_build_run_summary(tmp_path):
    """build_run_summary should produce a valid summary dict."""
    run_dir = _create_synthetic_run_dir(tmp_path)
    summary = build_run_summary(run_dir)

    assert summary["schema_version"] == "1.0"
    assert summary["run_id"] == "test_run_001"
    assert summary["scenario"] == "test_run_001"
    assert summary["test_metadata"]["platform"] == "oss-sentinel"
    assert summary["throughput"]["total_requests"] == 1000
    assert summary["throughput"]["requests_per_sec"] == 500.0
    assert summary["errors"]["total_failures"] == 5
    assert summary["errors"]["error_rate"] == pytest.approx(0.005, abs=0.001)
    assert "p99" in summary["latency_percentiles_ms"]
    assert len(summary["timeline_markers"]) == 2
    assert "dashboard" in summary["grafana"]


def test_render_markdown(tmp_path):
    """render_markdown should produce a non-empty markdown string with key sections."""
    run_dir = _create_synthetic_run_dir(tmp_path)
    summary = build_run_summary(run_dir)
    md = render_markdown(summary)

    assert isinstance(md, str)
    assert len(md) > 100
    assert "# Run Summary:" in md
    assert "## Latency Percentiles" in md
    assert "## Throughput" in md
    assert "## Errors" in md
    assert "## Timeline Markers" in md
    assert "test_run_001" in md


def test_summary_handles_missing_files(tmp_path):
    """Exporter should handle a run dir with no CSV/events gracefully."""
    empty_run = tmp_path / "empty_run"
    empty_run.mkdir()

    summary = build_run_summary(empty_run)
    assert summary["schema_version"] == "1.0"
    assert summary["timeline_markers"] == []
    assert "error" in summary.get("latency_percentiles_ms", {}) or summary.get("latency_percentiles_ms") == {}


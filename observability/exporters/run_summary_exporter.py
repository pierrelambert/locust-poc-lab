#!/usr/bin/env python3
"""Export a scenario run directory into a structured JSON summary and markdown report.

Reads Locust CSV output, events.jsonl timeline, and environment.json from a
completed scenario run directory and produces:
  - run_summary.json  — machine-readable summary
  - run_summary.md    — human-readable report compatible with POC_SCORECARD_TEMPLATE.md

Usage::

    python -m observability.exporters.run_summary_exporter results/<run_id>
    # or
    python observability/exporters/run_summary_exporter.py results/<run_id>

Environment variables:
    GRAFANA_BASE_URL  — Base URL for Grafana dashboard links (default: http://localhost:3000)
    GRAFANA_DASHBOARD_UID — Dashboard UID for screenshot URLs (default: poc-lab-overview)
"""

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Configuration ────────────────────────────────────────────────────────────

GRAFANA_BASE_URL = os.environ.get("GRAFANA_BASE_URL", "http://localhost:3000")
GRAFANA_DASHBOARD_UID = os.environ.get("GRAFANA_DASHBOARD_UID", "poc-lab-overview")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_csv(run_dir: Path, suffix: str) -> Optional[Path]:
    """Find a Locust CSV file by suffix pattern."""
    candidates = sorted(run_dir.glob(f"*{suffix}"))
    candidates = [c for c in candidates if "_warmup" not in c.name and "_baseline" not in c.name]
    return candidates[0] if candidates else None


def _read_csv(path: Path) -> List[Dict[str, str]]:
    """Read a CSV file into a list of dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _int(val: str) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_div(num: int, denom: int) -> float:
    return round(num / denom, 6) if denom else 0.0


def _list_run_files(run_dir: Path) -> List[str]:
    """List all files in the run directory."""
    return sorted(f.name for f in run_dir.iterdir() if f.is_file())


# ── Locust CSV Parsing ───────────────────────────────────────────────────────

def parse_locust_stats(run_dir: Path) -> Dict[str, Any]:
    """Parse Locust aggregated stats CSV into structured metrics."""
    stats_file = _find_csv(run_dir, "_stats.csv")
    if not stats_file:
        return {"error": "locust_stats.csv not found"}

    rows = _read_csv(stats_file)
    aggregated = [r for r in rows if r.get("Name") == "Aggregated"]
    if not aggregated:
        aggregated = rows[-1:] if rows else []
    if not aggregated:
        return {"error": "no aggregated row in stats CSV"}

    agg = aggregated[0]
    return {
        "request_count": _int(agg.get("Request Count", "0")),
        "failure_count": _int(agg.get("Failure Count", "0")),
        "error_rate": _safe_div(_int(agg.get("Failure Count", "0")),
                                _int(agg.get("Request Count", "1"))),
        "throughput_rps": _float(agg.get("Requests/s", "0")),
        "latency_ms": {
            "avg": _float(agg.get("Average Response Time", "0")),
            "min": _float(agg.get("Min Response Time", "0")),
            "max": _float(agg.get("Max Response Time", "0")),
            "median": _float(agg.get("Median Response Time", "0")),
            "p50": _float(agg.get("50%", "0")),
            "p66": _float(agg.get("66%", "0")),
            "p75": _float(agg.get("75%", "0")),
            "p80": _float(agg.get("80%", "0")),
            "p90": _float(agg.get("90%", "0")),
            "p95": _float(agg.get("95%", "0")),
            "p98": _float(agg.get("98%", "0")),
            "p99": _float(agg.get("99%", "0")),
            "p999": _float(agg.get("99.9%", "0")),
            "p9999": _float(agg.get("99.99%", "0")),
            "p100": _float(agg.get("100%", "0")),
        },
        "failures_per_sec": _float(agg.get("Failures/s", "0")),
    }


def parse_locust_errors(run_dir: Path) -> List[Dict[str, Any]]:
    """Parse Locust failures CSV."""
    err_file = _find_csv(run_dir, "_failures.csv")
    if not err_file:
        return []
    rows = _read_csv(err_file)
    return [{"method": r.get("Method", ""), "name": r.get("Name", ""),
             "error": r.get("Error", ""), "occurrences": _int(r.get("Occurrences", "0"))}
            for r in rows]


def parse_throughput_history(run_dir: Path) -> List[Dict[str, Any]]:
    """Parse Locust stats history CSV for time-series throughput data."""
    hist_file = _find_csv(run_dir, "_stats_history.csv")
    if not hist_file:
        return []


# ── Events / Timeline ───────────────────────────────────────────────────────

def parse_events(run_dir: Path) -> List[Dict[str, Any]]:
    """Parse events.jsonl timeline markers."""
    events_file = run_dir / "events.jsonl"
    if not events_file.exists():
        return []
    events = []
    for line in events_file.read_text().strip().splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ── Environment Metadata ─────────────────────────────────────────────────────

def parse_environment(run_dir: Path) -> Dict[str, Any]:
    """Parse environment.json test metadata."""
    env_file = run_dir / "environment.json"
    if not env_file.exists():
        return {}
    try:
        return json.loads(env_file.read_text())
    except json.JSONDecodeError:
        return {"error": "invalid environment.json"}


# ── Grafana URLs ─────────────────────────────────────────────────────────────

def build_grafana_urls(events: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build Grafana dashboard and screenshot URLs from event timestamps."""
    epochs = [e.get("epoch", 0) for e in events if e.get("epoch")]
    if not epochs:
        return {"dashboard": f"{GRAFANA_BASE_URL}/d/{GRAFANA_DASHBOARD_UID}",
                "note": "no event timestamps — set time range manually"}

    start_ms = (min(epochs) - 60) * 1000
    end_ms = (max(epochs) + 60) * 1000
    base = f"{GRAFANA_BASE_URL}/d/{GRAFANA_DASHBOARD_UID}"
    params = f"from={start_ms}&to={end_ms}"
    return {
        "dashboard": f"{base}?{params}",
        "render_png": f"{GRAFANA_BASE_URL}/render/d-solo/{GRAFANA_DASHBOARD_UID}?{params}&width=1200&height=600",
        "time_range": {"from_epoch": min(epochs), "to_epoch": max(epochs)},
    }


# ── Summary Builder ──────────────────────────────────────────────────────────

def build_run_summary(run_dir: Path) -> Dict[str, Any]:
    """Build the complete run summary from all available data sources."""
    env = parse_environment(run_dir)
    stats = parse_locust_stats(run_dir)
    errors = parse_locust_errors(run_dir)
    events = parse_events(run_dir)
    grafana = build_grafana_urls(events)

    run_id = env.get("run_id", run_dir.name)
    scenario_name = run_id.rsplit("_" + env.get("platform", ""), 1)[0] if env.get("platform") else run_id

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "scenario": scenario_name,
        "test_metadata": {
            "platform": env.get("platform", "unknown"),
            "locust_file": env.get("locust_file", ""),
            "workload_profile": env.get("workload_profile", ""),
            "locust_users": env.get("locust_users", 0),
            "locust_spawn_rate": env.get("locust_spawn_rate", 0),
            "locust_host": env.get("locust_host", ""),
            "redis_version": env.get("redis_version", "unknown"),
            "started_at": env.get("timestamp", ""),
        },
        "latency_percentiles_ms": stats.get("latency_ms", {}),
        "throughput": {
            "requests_per_sec": stats.get("throughput_rps", 0),
            "total_requests": stats.get("request_count", 0),
        },
        "errors": {
            "total_failures": stats.get("failure_count", 0),
            "error_rate": stats.get("error_rate", 0),
            "failures_per_sec": stats.get("failures_per_sec", 0),
            "error_details": errors,
        },
        "timeline_markers": events,
        "grafana": grafana,
        "files": _list_run_files(run_dir),
    }



# ── Markdown Renderer ────────────────────────────────────────────────────────

def render_markdown(summary: Dict[str, Any]) -> str:
    """Render the run summary as a markdown report compatible with the scorecard template."""
    meta = summary.get("test_metadata", {})
    lat = summary.get("latency_percentiles_ms", {})
    tp = summary.get("throughput", {})
    err = summary.get("errors", {})
    events = summary.get("timeline_markers", [])
    grafana = summary.get("grafana", {})

    lines = [
        f"# Run Summary: {summary.get('run_id', 'unknown')}",
        "",
        f"**Generated:** {summary.get('generated_at', '')}  ",
        f"**Scenario:** {summary.get('scenario', '')}  ",
        f"**Platform:** {meta.get('platform', '')}  ",
        f"**Redis version:** {meta.get('redis_version', '')}  ",
        "",
        "## Test Metadata",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Locust file | `{meta.get('locust_file', '')}` |",
        f"| Workload profile | `{meta.get('workload_profile', '')}` |",
        f"| Users | {meta.get('locust_users', '')} |",
        f"| Spawn rate | {meta.get('locust_spawn_rate', '')} |",
        f"| Host | `{meta.get('locust_host', '')}` |",
        f"| Started at | {meta.get('started_at', '')} |",
        "",
        "## Latency Percentiles (ms)",
        "",
        "| Percentile | Value (ms) |",
        "|---|---|",
    ]

    for pct in ["p50", "p75", "p90", "p95", "p99", "p999"]:
        val = lat.get(pct, "—")
        lines.append(f"| {pct} | {val} |")

    lines += [
        f"| avg | {lat.get('avg', '—')} |",
        f"| min | {lat.get('min', '—')} |",
        f"| max | {lat.get('max', '—')} |",
        "",
        "## Throughput",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Requests/sec | {tp.get('requests_per_sec', 0):.2f} |",
        f"| Total requests | {tp.get('total_requests', 0)} |",
        "",
        "## Errors",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total failures | {err.get('total_failures', 0)} |",
        f"| Error rate | {err.get('error_rate', 0):.4f} |",
        f"| Failures/sec | {err.get('failures_per_sec', 0):.2f} |",
    ]

    error_details = err.get("error_details", [])
    if error_details:
        lines += ["", "### Error Breakdown", "",
                   "| Method | Name | Error | Count |", "|---|---|---|---|"]
        for e in error_details:
            lines.append(f"| {e.get('method', '')} | {e.get('name', '')} "
                         f"| {e.get('error', '')[:80]} | {e.get('occurrences', 0)} |")

    lines += ["", "## Timeline Markers", ""]
    if events:
        lines += ["| Timestamp | Event | Detail |", "|---|---|---|"]
        for ev in events:
            lines.append(f"| {ev.get('timestamp', '')} | {ev.get('event', '')} "
                         f"| {ev.get('detail', '')} |")
    else:
        lines.append("_No timeline events recorded._")

    lines += [
        "", "## Grafana Dashboard", "",
        f"- **Dashboard URL:** [{grafana.get('dashboard', '')}]({grafana.get('dashboard', '')})",
    ]
    if "render_png" in grafana:
        lines.append(f"- **Screenshot URL:** [{grafana.get('render_png', '')}]"
                     f"({grafana.get('render_png', '')})")
    if "note" in grafana:
        lines.append(f"- **Note:** {grafana.get('note', '')}")

    lines += ["", "## Evidence Files", "", "| File |", "|---|"]
    for f in summary.get("files", []):
        lines.append(f"| `{f}` |")

    lines += [
        "", "---", "",
        "_This report was generated by `observability/exporters/run_summary_exporter.py` "
        "and is compatible with the POC Scorecard Template at "
        "`docs/templates/POC_SCORECARD_TEMPLATE.md`._",
    ]

    return "\n".join(lines) + "\n"


# ── Main ─────────────────────────────────────────────────────────────────────

def export_run_summary(run_dir_path: str) -> Dict[str, Any]:
    """Export a run summary from the given directory. Returns the summary dict."""
    run_dir = Path(run_dir_path)
    if not run_dir.is_dir():
        print(f"Error: {run_dir_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    summary = build_run_summary(run_dir)

    # Write JSON summary
    json_path = run_dir / "run_summary.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"[OK] JSON summary: {json_path}")

    # Write markdown report
    md_path = run_dir / "run_summary.md"
    md_path.write_text(render_markdown(summary))
    print(f"[OK] Markdown report: {md_path}")

    return summary


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m observability.exporters.run_summary_exporter <run_dir>",
              file=sys.stderr)
        print("       python observability/exporters/run_summary_exporter.py <run_dir>",
              file=sys.stderr)
        sys.exit(1)

    export_run_summary(sys.argv[1])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compare two run_summary.json files and produce a comparison report.

Usage::

    python -m tooling.compare_runs results/re_run/run_summary.json results/oss_run/run_summary.json
    python -m tooling.compare_runs a.json b.json --format json
    python -m tooling.compare_runs a.json b.json --format md
    python -m tooling.compare_runs a.json b.json --format both
    python -m tooling.compare_runs a.json b.json --format both --output-dir ./reports
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_get(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts."""
    current = data
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k, default)
    return current


def _pct_change(baseline: float, candidate: float) -> Optional[float]:
    """Return percentage change from baseline to candidate, or None if baseline is 0."""
    if baseline == 0:
        return None
    return round(((candidate - baseline) / abs(baseline)) * 100, 2)


def _extract_failover_recovery(events: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Extract failover and recovery durations from timeline markers.

    Looks for event pairs like failover_start/failover_end and
    recovery_start/recovery_end (or similar naming conventions).
    """
    result: Dict[str, Optional[float]] = {
        "failover_time_s": None,
        "recovery_time_s": None,
    }
    by_event: Dict[str, float] = {}
    for ev in events:
        name = ev.get("event", "")
        epoch = ev.get("epoch")
        if epoch is not None:
            by_event[name] = float(epoch)

    # Try common naming patterns
    for prefix in ("failover", "fault", "failure"):
        start = by_event.get(f"{prefix}_start") or by_event.get(f"{prefix}_inject")
        end = by_event.get(f"{prefix}_end") or by_event.get(f"{prefix}_detected")
        if start and end and end > start:
            result["failover_time_s"] = round(end - start, 3)
            break

    for prefix in ("recovery", "restore"):
        start = by_event.get(f"{prefix}_start") or by_event.get(f"failover_end")
        end = by_event.get(f"{prefix}_end") or by_event.get(f"{prefix}_complete")
        if start and end and end > start:
            result["recovery_time_s"] = round(end - start, 3)
            break

    return result


# ── RunComparator ────────────────────────────────────────────────────────────

class RunComparator:
    """Compare two run_summary.json structures and produce a comparison report."""

    def __init__(self, baseline: Dict[str, Any], candidate: Dict[str, Any]):
        self.baseline = baseline
        self.candidate = candidate

    # -- public API --

    def compare(self) -> Dict[str, Any]:
        """Return a structured comparison dict."""
        b, c = self.baseline, self.candidate
        lat_cmp = self._compare_latency()
        tp_cmp = self._compare_throughput()
        err_cmp = self._compare_errors()
        fo_b = _extract_failover_recovery(b.get("timeline_markers", []))
        fo_c = _extract_failover_recovery(c.get("timeline_markers", []))
        resiliency = self._compare_resiliency(fo_b, fo_c)

        return {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline": {
                "run_id": b.get("run_id", "unknown"),
                "platform": _safe_get(b, "test_metadata", "platform", default="unknown"),
            },
            "candidate": {
                "run_id": c.get("run_id", "unknown"),
                "platform": _safe_get(c, "test_metadata", "platform", default="unknown"),
            },
            "latency": lat_cmp,
            "throughput": tp_cmp,
            "errors": err_cmp,
            "resiliency": resiliency,
            "winner_summary": self._summarise_winners(lat_cmp, tp_cmp, err_cmp, resiliency),
        }

    # -- private helpers --

    def _compare_latency(self) -> Dict[str, Any]:
        percentiles = ["p50", "p95", "p99"]
        rows: List[Dict[str, Any]] = []
        for p in percentiles:
            b_val = _safe_get(self.baseline, "latency_percentiles_ms", p, default=None)
            c_val = _safe_get(self.candidate, "latency_percentiles_ms", p, default=None)
            b_f = float(b_val) if b_val is not None else None
            c_f = float(c_val) if c_val is not None else None
            row: Dict[str, Any] = {"percentile": p, "baseline_ms": b_f, "candidate_ms": c_f}
            if b_f is not None and c_f is not None:
                row["diff_ms"] = round(c_f - b_f, 2)
                row["pct_change"] = _pct_change(b_f, c_f)
                row["winner"] = "candidate" if c_f <= b_f else "baseline"
            else:
                row["diff_ms"] = None
                row["pct_change"] = None
                row["winner"] = None
            rows.append(row)
        return {"percentiles": rows}

    def _compare_throughput(self) -> Dict[str, Any]:
        b_rps = _safe_get(self.baseline, "throughput", "requests_per_sec", default=None)
        c_rps = _safe_get(self.candidate, "throughput", "requests_per_sec", default=None)
        b_f = float(b_rps) if b_rps is not None else None
        c_f = float(c_rps) if c_rps is not None else None
        result: Dict[str, Any] = {"baseline_rps": b_f, "candidate_rps": c_f}
        if b_f is not None and c_f is not None:
            result["diff_rps"] = round(c_f - b_f, 2)
            result["pct_change"] = _pct_change(b_f, c_f)
            result["winner"] = "candidate" if c_f >= b_f else "baseline"
        else:
            result["diff_rps"] = None
            result["pct_change"] = None
            result["winner"] = None
        return result

    def _compare_errors(self) -> Dict[str, Any]:
        b_rate = _safe_get(self.baseline, "errors", "error_rate", default=None)
        c_rate = _safe_get(self.candidate, "errors", "error_rate", default=None)
        b_f = float(b_rate) if b_rate is not None else None
        c_f = float(c_rate) if c_rate is not None else None
        result: Dict[str, Any] = {"baseline_error_rate": b_f, "candidate_error_rate": c_f}
        if b_f is not None and c_f is not None:
            result["diff"] = round(c_f - b_f, 6)
            result["pct_change"] = _pct_change(b_f, c_f) if b_f > 0 else None
            result["winner"] = "candidate" if c_f <= b_f else "baseline"
        else:
            result["diff"] = None
            result["pct_change"] = None
            result["winner"] = None
        return result

    def _compare_resiliency(
        self, fo_b: Dict[str, Optional[float]], fo_c: Dict[str, Optional[float]]
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, label in [("failover_time_s", "failover_time"), ("recovery_time_s", "recovery_time")]:
            b_val = fo_b.get(key)
            c_val = fo_c.get(key)
            entry: Dict[str, Any] = {"baseline_s": b_val, "candidate_s": c_val}
            if b_val is not None and c_val is not None:
                entry["diff_s"] = round(c_val - b_val, 3)
                entry["pct_change"] = _pct_change(b_val, c_val)
                entry["winner"] = "candidate" if c_val <= b_val else "baseline"
            else:
                entry["diff_s"] = None
                entry["pct_change"] = None
                entry["winner"] = None
            result[label] = entry
        return result

    @staticmethod
    def _summarise_winners(
        lat: Dict[str, Any], tp: Dict[str, Any],
        err: Dict[str, Any], res: Dict[str, Any],
    ) -> Dict[str, Any]:
        wins: Dict[str, int] = {"baseline": 0, "candidate": 0, "tie": 0}
        for row in lat.get("percentiles", []):
            w = row.get("winner")
            if w:
                wins[w] = wins.get(w, 0) + 1
        for section in [tp, err]:
            w = section.get("winner")
            if w:
                wins[w] = wins.get(w, 0) + 1
        for entry in res.values():
            if isinstance(entry, dict):
                w = entry.get("winner")
                if w:
                    wins[w] = wins.get(w, 0) + 1
        total = wins["baseline"] + wins["candidate"]
        if total == 0:
            overall = "insufficient_data"
        elif wins["candidate"] > wins["baseline"]:
            overall = "candidate"
        elif wins["baseline"] > wins["candidate"]:
            overall = "baseline"
        else:
            overall = "tie"
        return {"baseline_wins": wins["baseline"], "candidate_wins": wins["candidate"], "overall": overall}

    def compare_json(self) -> str:
        """Return comparison as a JSON string."""
        return json.dumps(self.compare(), indent=2) + "\n"

    def compare_markdown(self) -> str:
        """Return comparison as a markdown report."""
        return _render_comparison_md(self.compare())


# ── Markdown Renderer ────────────────────────────────────────────────────────

def _fmt(val: Any, suffix: str = "") -> str:
    if val is None:
        return "—"
    if isinstance(val, float):
        return f"{val:.2f}{suffix}"
    return f"{val}{suffix}"


def _winner_icon(winner: Optional[str]) -> str:
    if winner == "candidate":
        return "✅ candidate"
    if winner == "baseline":
        return "✅ baseline"
    return "—"


def _render_comparison_md(cmp: Dict[str, Any]) -> str:
    b_info = cmp.get("baseline", {})
    c_info = cmp.get("candidate", {})
    lines = [
        "# Cross-Run Comparison Report",
        "",
        f"**Generated:** {cmp.get('generated_at', '')}  ",
        "",
        "## Compared Runs",
        "",
        "| Role | Run ID | Platform |",
        "|---|---|---|",
        f"| Baseline | {b_info.get('run_id', '')} | {b_info.get('platform', '')} |",
        f"| Candidate | {c_info.get('run_id', '')} | {c_info.get('platform', '')} |",
        "",
        "## Latency Comparison (ms)",
        "",
        "| Percentile | Baseline | Candidate | Diff | % Change | Winner |",
        "|---|---|---|---|---|---|",
    ]
    for row in cmp.get("latency", {}).get("percentiles", []):
        lines.append(
            f"| {row['percentile']} | {_fmt(row.get('baseline_ms'))} "
            f"| {_fmt(row.get('candidate_ms'))} | {_fmt(row.get('diff_ms'))} "
            f"| {_fmt(row.get('pct_change'), '%')} | {_winner_icon(row.get('winner'))} |"
        )

    tp = cmp.get("throughput", {})
    lines += [
        "",
        "## Throughput Comparison",
        "",
        "| Metric | Baseline | Candidate | Diff | % Change | Winner |",
        "|---|---|---|---|---|---|",
        f"| Requests/sec | {_fmt(tp.get('baseline_rps'))} | {_fmt(tp.get('candidate_rps'))} "
        f"| {_fmt(tp.get('diff_rps'))} | {_fmt(tp.get('pct_change'), '%')} "
        f"| {_winner_icon(tp.get('winner'))} |",
    ]

    err = cmp.get("errors", {})
    lines += [
        "",
        "## Error Rate Comparison",
        "",
        "| Metric | Baseline | Candidate | Diff | % Change | Winner |",
        "|---|---|---|---|---|---|",
        f"| Error rate | {_fmt(err.get('baseline_error_rate'))} "
        f"| {_fmt(err.get('candidate_error_rate'))} | {_fmt(err.get('diff'))} "
        f"| {_fmt(err.get('pct_change'), '%')} | {_winner_icon(err.get('winner'))} |",
    ]

    res = cmp.get("resiliency", {})
    lines += [
        "",
        "## Resiliency Comparison",
        "",
        "| Metric | Baseline (s) | Candidate (s) | Diff (s) | % Change | Winner |",
        "|---|---|---|---|---|---|",
    ]
    for label in ["failover_time", "recovery_time"]:
        entry = res.get(label, {})
        lines.append(
            f"| {label.replace('_', ' ').title()} | {_fmt(entry.get('baseline_s'))} "
            f"| {_fmt(entry.get('candidate_s'))} | {_fmt(entry.get('diff_s'))} "
            f"| {_fmt(entry.get('pct_change'), '%')} | {_winner_icon(entry.get('winner'))} |"
        )

    ws = cmp.get("winner_summary", {})
    lines += [
        "",
        "## Overall Summary",
        "",
        f"- **Baseline wins:** {ws.get('baseline_wins', 0)}",
        f"- **Candidate wins:** {ws.get('candidate_wins', 0)}",
        f"- **Overall winner:** {ws.get('overall', 'unknown')}",
        "",
        "---",
        "",
        "_Generated by `tooling/compare_runs.py`._",
    ]
    return "\n".join(lines) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────

def _load_summary(path_str: str) -> Dict[str, Any]:
    p = Path(path_str)
    if not p.exists():
        print(f"Error: file not found: {p}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {p}: {exc}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Compare two run_summary.json files and produce a comparison report.",
    )
    parser.add_argument("baseline", help="Path to baseline run_summary.json")
    parser.add_argument("candidate", help="Path to candidate run_summary.json")
    parser.add_argument(
        "--format", choices=["json", "md", "both"], default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--output-dir", default=".", help="Directory for output files (default: cwd)",
    )
    args = parser.parse_args()

    baseline = _load_summary(args.baseline)
    candidate = _load_summary(args.candidate)
    comparator = RunComparator(baseline, candidate)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.format in ("json", "both"):
        json_path = out_dir / "comparison_report.json"
        json_path.write_text(comparator.compare_json(), encoding="utf-8")
        print(f"[OK] JSON report: {json_path}")

    if args.format in ("md", "both"):
        md_path = out_dir / "comparison_report.md"
        md_path.write_text(comparator.compare_markdown(), encoding="utf-8")
        print(f"[OK] Markdown report: {md_path}")


if __name__ == "__main__":
    main()

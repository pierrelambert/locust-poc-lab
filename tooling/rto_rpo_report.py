#!/usr/bin/env python3
"""RTO/RPO evidence reporter.

Parses ``events.jsonl`` (timeline markers) and ``canary_writes.jsonl``
(canary writer output) to compute Recovery Time Objective (RTO) and
Recovery Point Objective (RPO) metrics.

Definitions:
- **RTO** — time from fault injection to first successful write after recovery.
- **RPO** — number (and time span) of writes lost during the outage window.

Usage::

    python -m tooling.rto_rpo_report results/run1
    python -m tooling.rto_rpo_report results/run1 --output results/run1/rto_rpo.json

Programmatic::

    reporter = RtoRpoReporter("results/run1")
    report = reporter.compute()
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RtoRpoReporter:
    """Compute RTO and RPO from events.jsonl and canary_writes.jsonl."""

    def __init__(self, run_dir: str) -> None:
        self._run_dir = Path(run_dir)

    def compute(self) -> Dict[str, Any]:
        """Parse evidence files and return an RTO/RPO report dict."""
        events = self._parse_events()
        canary = self._parse_canary_log()

        fault_start, fault_end = self._find_fault_window(events)
        recovery_ts = self._find_recovery_ts(events)

        rto = self._compute_rto(fault_start, recovery_ts, canary)
        rpo = self._compute_rpo(fault_start, fault_end, canary)

        return {
            "schema_version": "1.0",
            "run_dir": str(self._run_dir),
            "fault_window": {
                "start_epoch": fault_start,
                "end_epoch": fault_end,
                "duration_s": round(fault_end - fault_start, 3) if fault_start and fault_end else None,
            },
            "rto": rto,
            "rpo": rpo,
            "canary_summary": {
                "total_writes": len(canary),
                "ok_writes": sum(1 for r in canary if r.get("status") == "ok"),
                "error_writes": sum(1 for r in canary if r.get("status") == "error"),
            },
            "events_count": len(events),
        }

    # ── parsers ──────────────────────────────────────────────────────────

    def _parse_events(self) -> List[Dict[str, Any]]:
        path = self._run_dir / "events.jsonl"
        if not path.exists():
            logger.warning("events.jsonl not found in %s", self._run_dir)
            return []
        records = []
        for line in path.read_text().strip().splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def _parse_canary_log(self) -> List[Dict[str, Any]]:
        path = self._run_dir / "canary_writes.jsonl"
        if not path.exists():
            logger.warning("canary_writes.jsonl not found in %s", self._run_dir)
            return []
        records = []
        for line in path.read_text().strip().splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    # ── fault window detection ───────────────────────────────────────────

    def _find_fault_window(
        self, events: List[Dict[str, Any]]
    ) -> tuple:
        """Find fault start and end epochs from events."""
        by_event: Dict[str, float] = {}
        for ev in events:
            name = ev.get("event", "")
            epoch = ev.get("epoch")
            if epoch is not None:
                by_event[name] = float(epoch)

        start = None
        for key in ("fault_inject", "failover_start", "fault_start", "failure_inject"):
            if key in by_event:
                start = by_event[key]
                break

        end = None
        for key in ("fault_end", "failover_end", "failure_end", "recovery_start"):
            if key in by_event:
                end = by_event[key]
                break

        return start, end

    def _find_recovery_ts(self, events: List[Dict[str, Any]]) -> Optional[float]:
        for ev in events:
            if ev.get("event") in ("recovery_end", "recovery_complete", "restore_complete"):
                return ev.get("epoch")
        return None

    # ── RTO computation ──────────────────────────────────────────────────

    def _compute_rto(
        self,
        fault_start: Optional[float],
        recovery_ts: Optional[float],
        canary: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """RTO = time from fault to first successful write after recovery."""
        if fault_start is None:
            return {"rto_seconds": None, "note": "no fault event found"}

        # Find first ok write after a gap of errors post-fault
        first_ok_after: Optional[float] = None
        saw_error = False
        for r in sorted(canary, key=lambda x: x.get("ts", 0)):
            ts = r.get("ts", 0)
            if ts <= fault_start:
                continue
            if r.get("status") == "error":
                saw_error = True
            elif r.get("status") == "ok" and saw_error:
                first_ok_after = ts
                break

        if first_ok_after is not None:
            rto_s = round(first_ok_after - fault_start, 3)
            return {"rto_seconds": rto_s, "first_ok_epoch": first_ok_after}

        # Fallback to event-based recovery
        if recovery_ts is not None:
            return {"rto_seconds": round(recovery_ts - fault_start, 3),
                    "note": "from events (no canary confirmation)"}

        return {"rto_seconds": None, "note": "recovery not detected"}

    # ── RPO computation ──────────────────────────────────────────────────

    def _compute_rpo(
        self,
        fault_start: Optional[float],
        fault_end: Optional[float],
        canary: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """RPO = writes lost during the outage window."""
        if fault_start is None:
            return {"lost_writes": 0, "note": "no fault event found"}

        # Count error writes during and after fault
        errors_during: List[Dict[str, Any]] = []
        for r in canary:
            ts = r.get("ts", 0)
            if ts >= fault_start and r.get("status") == "error":
                errors_during.append(r)

        if not errors_during:
            return {"lost_writes": 0, "rpo_seconds": 0, "note": "no writes lost"}

        first_err_ts = min(r["ts"] for r in errors_during)
        last_err_ts = max(r["ts"] for r in errors_during)
        rpo_s = round(last_err_ts - first_err_ts, 3)

        return {
            "lost_writes": len(errors_during),
            "rpo_seconds": rpo_s,
            "first_error_epoch": first_err_ts,
            "last_error_epoch": last_err_ts,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute RTO/RPO from scenario run evidence")
    parser.add_argument("run_dir", help="Path to the scenario run directory")
    parser.add_argument("--output", help="Output path for rto_rpo.json (default: <run_dir>/rto_rpo.json)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    reporter = RtoRpoReporter(args.run_dir)
    report = reporter.compute()

    output_path = args.output or str(Path(args.run_dir) / "rto_rpo.json")
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    print(f"[OK] RTO/RPO report: {output_path}")

    rto = report["rto"]
    rpo = report["rpo"]
    rto_val = rto.get("rto_seconds")
    rpo_val = rpo.get("lost_writes", 0)
    print(f"     RTO: {rto_val}s" if rto_val is not None else "     RTO: not determined")
    print(f"     RPO: {rpo_val} writes lost")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Post-run consistency checker for canary keys.

Reads canary keys back from Redis and cross-references with
``canary_writes.jsonl`` to detect missing, duplicate, or out-of-order keys.

Usage::

    python -m tooling.consistency_checker --host localhost --port 6379 \\
        --canary-log results/run1/canary_writes.jsonl \\
        --output results/run1/consistency_report.json

Programmatic::

    checker = ConsistencyChecker(client, "results/run1/canary_writes.jsonl")
    report = checker.check()
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import redis

from workloads.lib.topology_clients import create_client

logger = logging.getLogger(__name__)

CANARY_PREFIX = "canary"


class ConsistencyChecker:
    """Verify canary key consistency between write log and Redis state."""

    def __init__(
        self,
        client: redis.Redis,
        canary_log_path: str,
        *,
        key_prefix: str = CANARY_PREFIX,
    ) -> None:
        self._client = client
        self._log_path = Path(canary_log_path)
        self._key_prefix = key_prefix

    def check(self) -> Dict[str, Any]:
        """Run the consistency check and return a structured report.

        Returns a dict with keys:
        - total_written: number of successful writes in the log
        - total_found: number of keys found in Redis
        - missing_keys: list of seq IDs written but not found
        - unexpected_keys: list of seq IDs found but not in write log
        - out_of_order: list of seq IDs whose stored timestamp differs from log
        - duplicates: list of seq IDs that appear more than once in the log
        - error_writes: number of writes that failed (logged as error)
        - consistency_pct: percentage of successful writes found in Redis
        """
        written = self._parse_write_log()
        found = self._scan_canary_keys()
        return self._compare(written, found)

    def _parse_write_log(self) -> List[Dict[str, Any]]:
        """Parse canary_writes.jsonl and return successful write records."""
        if not self._log_path.exists():
            logger.warning("Canary log not found: %s", self._log_path)
            return []
        records: List[Dict[str, Any]] = []
        for line in self._log_path.read_text().strip().splitlines():
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def _scan_canary_keys(self) -> Dict[int, Dict[str, Any]]:
        """Scan Redis for canary keys and return {seq_id: value_dict}."""
        found: Dict[int, Dict[str, Any]] = {}
        cursor = 0
        pattern = f"{self._key_prefix}:*"
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=500)
            for key in keys:
                key_str = key if isinstance(key, str) else key.decode()
                try:
                    seq_id = int(key_str.split(":")[-1])
                except (ValueError, IndexError):
                    continue
                raw = self._client.get(key_str)
                if raw:
                    try:
                        found[seq_id] = json.loads(raw if isinstance(raw, str) else raw.decode())
                    except json.JSONDecodeError:
                        found[seq_id] = {"raw": raw}
            if cursor == 0:
                break
        return found

    def _compare(
        self,
        records: List[Dict[str, Any]],
        found: Dict[int, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare write log against Redis state."""
        ok_records = [r for r in records if r.get("status") == "ok"]
        error_count = sum(1 for r in records if r.get("status") == "error")

        written_seqs: List[int] = []
        seen: Set[int] = set()
        duplicates: List[int] = []
        for r in ok_records:
            seq = r["seq"]
            if seq in seen:
                duplicates.append(seq)
            else:
                seen.add(seq)
                written_seqs.append(seq)

        written_set = set(written_seqs)
        found_set = set(found.keys())

        missing = sorted(written_set - found_set)
        unexpected = sorted(found_set - written_set)

        # Check ordering: compare stored ts with log ts
        out_of_order: List[int] = []
        log_ts = {r["seq"]: r.get("ts", 0) for r in ok_records}
        for seq in sorted(written_set & found_set):
            stored = found[seq]
            if isinstance(stored, dict) and "ts" in stored:
                if abs(stored["ts"] - log_ts.get(seq, 0)) > 1.0:
                    out_of_order.append(seq)

        total_written = len(written_set)
        total_found_matching = len(written_set & found_set)
        consistency_pct = (total_found_matching / total_written * 100) if total_written > 0 else 100.0

        return {
            "total_written": total_written,
            "total_found": len(found_set),
            "missing_keys": missing,
            "missing_count": len(missing),
            "unexpected_keys": unexpected,
            "unexpected_count": len(unexpected),
            "out_of_order": out_of_order,
            "out_of_order_count": len(out_of_order),
            "duplicates": duplicates,
            "duplicate_count": len(duplicates),
            "error_writes": error_count,
            "consistency_pct": round(consistency_pct, 4),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-run canary key consistency checker")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--db", type=int, default=0)
    parser.add_argument("--password", default="")
    parser.add_argument("--ssl", action="store_true")
    parser.add_argument("--connection-mode", default="standalone",
                        choices=["standalone", "sentinel", "cluster", "enterprise"])
    parser.add_argument("--sentinel-hosts", default="")
    parser.add_argument("--sentinel-service", default="mymaster")
    parser.add_argument("--canary-log", required=True, help="Path to canary_writes.jsonl")
    parser.add_argument("--output", help="Output path for consistency_report.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn_cfg: Dict[str, Any] = {
        "connection_mode": args.connection_mode,
        "host": args.host,
        "port": args.port,
        "db": args.db,
        "password": args.password or "",
    }
    if args.connection_mode == "sentinel":
        conn_cfg["sentinel_hosts"] = (args.sentinel_hosts or "").split(",")
        conn_cfg["sentinel_service"] = args.sentinel_service
    if args.ssl:
        conn_cfg["ssl"] = True

    client = create_client(conn_cfg)
    checker = ConsistencyChecker(client, args.canary_log)
    report = checker.check()

    output_path = args.output or str(Path(args.canary_log).parent / "consistency_report.json")
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    print(f"[OK] Consistency report: {output_path}")
    print(f"     Written: {report['total_written']}, Found: {report['total_found']}, "
          f"Missing: {report['missing_count']}, Consistency: {report['consistency_pct']}%")

    if report["missing_count"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()


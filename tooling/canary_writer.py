#!/usr/bin/env python3
"""Continuous canary key writer for data-consistency proof.

Writes ``canary:<seq_id>`` keys at a configurable rate (default 10/s) and
logs every write attempt to ``canary_writes.jsonl`` for post-run analysis.

Supports all topology modes via :func:`workloads.lib.topology_clients.create_client`.

Usage (standalone)::

    python -m tooling.canary_writer --host localhost --port 6379 --output-dir results/run1
    python -m tooling.canary_writer --connection-mode sentinel \\
        --sentinel-hosts localhost:26379 --output-dir results/run1

Programmatic::

    writer = CanaryWriter(conn_cfg={"host": "localhost"}, output_dir="results/run1")
    writer.start()   # background thread
    ...
    writer.stop()
"""

import argparse
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from workloads.lib.topology_clients import create_client

logger = logging.getLogger(__name__)

DEFAULT_RATE_HZ = 10
DEFAULT_KEY_TTL = 3600  # 1 hour
CANARY_PREFIX = "canary"


class CanaryWriter:
    """Write canary keys at a fixed rate and log results to JSONL."""

    def __init__(
        self,
        conn_cfg: Dict[str, Any],
        output_dir: str,
        *,
        rate_hz: float = DEFAULT_RATE_HZ,
        key_ttl: int = DEFAULT_KEY_TTL,
        key_prefix: str = CANARY_PREFIX,
    ) -> None:
        self._conn_cfg = conn_cfg
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._rate_hz = rate_hz
        self._interval = 1.0 / rate_hz
        self._key_ttl = key_ttl
        self._key_prefix = key_prefix

        self._client = create_client(conn_cfg)
        self._log_path = self._output_dir / "canary_writes.jsonl"
        self._seq: int = 0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ── public API ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the canary writer in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("CanaryWriter already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="canary-writer")
        self._thread.start()
        logger.info("CanaryWriter started (rate=%s Hz, output=%s)", self._rate_hz, self._log_path)

    def stop(self) -> int:
        """Stop the writer and return the total number of writes attempted."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("CanaryWriter stopped after %d writes", self._seq)
        return self._seq

    @property
    def seq(self) -> int:
        """Current sequence number (total writes attempted)."""
        return self._seq

    # ── internal ─────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        with open(self._log_path, "a") as log_fh:
            while not self._stop_event.is_set():
                loop_start = time.monotonic()
                with self._lock:
                    self._seq += 1
                    seq_id = self._seq
                key = f"{self._key_prefix}:{seq_id}"
                ts = time.time()
                record: Dict[str, Any] = {
                    "seq": seq_id,
                    "key": key,
                    "ts": ts,
                    "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts)),
                }
                try:
                    self._client.set(key, json.dumps({"seq": seq_id, "ts": ts}), ex=self._key_ttl)
                    record["status"] = "ok"
                except Exception as exc:
                    record["status"] = "error"
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    logger.debug("Canary write %d failed: %s", seq_id, exc)

                log_fh.write(json.dumps(record) + "\n")
                log_fh.flush()

                elapsed = time.monotonic() - loop_start
                sleep_time = max(0, self._interval - elapsed)
                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)

    # ── CLI entry point ──────────────────────────────────────────────────


def _build_conn_cfg(args: argparse.Namespace) -> Dict[str, Any]:
    """Build a connection config dict from CLI arguments."""
    cfg: Dict[str, Any] = {
        "connection_mode": args.connection_mode,
        "host": args.host,
        "port": args.port,
        "db": args.db,
        "password": args.password or "",
    }
    if args.connection_mode == "sentinel":
        cfg["sentinel_hosts"] = (args.sentinel_hosts or "").split(",")
        cfg["sentinel_service"] = args.sentinel_service
    if args.ssl:
        cfg["ssl"] = True
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="Canary key writer for data-consistency proof")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--db", type=int, default=0)
    parser.add_argument("--password", default="")
    parser.add_argument("--ssl", action="store_true")
    parser.add_argument("--connection-mode", default="standalone",
                        choices=["standalone", "sentinel", "cluster", "enterprise"])
    parser.add_argument("--sentinel-hosts", default="", help="Comma-separated host:port list")
    parser.add_argument("--sentinel-service", default="mymaster")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE_HZ, help="Writes per second")
    parser.add_argument("--ttl", type=int, default=DEFAULT_KEY_TTL, help="Key TTL in seconds")
    parser.add_argument("--output-dir", required=True, help="Directory for canary_writes.jsonl")
    parser.add_argument("--duration", type=float, default=0,
                        help="Run for N seconds then stop (0 = until Ctrl-C)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn_cfg = _build_conn_cfg(args)
    writer = CanaryWriter(conn_cfg, args.output_dir, rate_hz=args.rate, key_ttl=args.ttl)
    writer.start()

    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        total = writer.stop()
        print(f"Canary writer finished: {total} writes logged to {writer._log_path}")


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""EventAnnotator — push scenario events as Grafana annotations.

Usage::

    from observability.annotator import EventAnnotator

    annotator = EventAnnotator(grafana_url="http://localhost:3000")
    annotator.annotate("scenario_start", tags=["failover", "oss-sentinel"])

Environment variables:
    GRAFANA_URL       — Grafana base URL (default: http://localhost:3000)
    GRAFANA_API_KEY   — Bearer token for Grafana API (optional; uses basic auth fallback)
    GRAFANA_USER      — Basic-auth user (default: admin)
    GRAFANA_PASSWORD  — Basic-auth password (default: admin)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight HTTP helper — avoids hard dependency on ``requests``
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, headers: dict, timeout: int = 5) -> int:
    """POST JSON and return HTTP status code.  Uses ``urllib`` so we have zero
    external dependencies.  Returns -1 on connection / timeout errors."""
    import urllib.request
    import urllib.error

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        logger.warning("Grafana annotation HTTP %s: %s", exc.code, exc.reason)
        return exc.code
    except Exception as exc:  # noqa: BLE001
        logger.debug("Grafana annotation failed (non-blocking): %s", exc)
        return -1


class EventAnnotator:
    """Push scenario lifecycle events to Grafana as dashboard annotations.

    Parameters
    ----------
    grafana_url : str
        Base URL of the Grafana instance.
    api_key : str | None
        Bearer API key.  Falls back to basic auth when *None*.
    dashboard_uid : str | None
        Scope annotations to a specific dashboard UID.
    enabled : bool
        Master switch — when *False* all calls are no-ops.
    """

    def __init__(
        self,
        grafana_url: str | None = None,
        api_key: str | None = None,
        dashboard_uid: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.grafana_url = (grafana_url or os.environ.get("GRAFANA_URL", "http://localhost:3000")).rstrip("/")
        self.api_key = api_key or os.environ.get("GRAFANA_API_KEY")
        self.dashboard_uid = dashboard_uid
        self.enabled = enabled
        self._annotations: List[Dict[str, Any]] = []

        if enabled:
            logger.info("EventAnnotator ready → %s", self.grafana_url)
        else:
            logger.info("EventAnnotator disabled")

    # -- public API ---------------------------------------------------------

    def annotate(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        epoch_ms: Optional[int] = None,
        time_end_ms: Optional[int] = None,
    ) -> bool:
        """Create an annotation.  Returns *True* on success or when disabled."""
        if not self.enabled:
            return True

        epoch_ms = epoch_ms or int(time.time() * 1000)
        body: Dict[str, Any] = {"text": text, "tags": tags or [], "time": epoch_ms}
        if time_end_ms:
            body["timeEnd"] = time_end_ms
        if self.dashboard_uid:
            body["dashboardUID"] = self.dashboard_uid

        self._annotations.append(body)
        return self._push(body)

    # Convenience helpers matching scenario lifecycle events
    def scenario_start(self, scenario: str, **kw: Any) -> bool:
        return self.annotate(f"Scenario started: {scenario}", tags=["scenario", "start", scenario], **kw)

    def failure_injected(self, detail: str = "", **kw: Any) -> bool:
        return self.annotate(f"Failure injected: {detail}", tags=["chaos", "failure-injected"], **kw)

    def failover_detected(self, detail: str = "", **kw: Any) -> bool:
        return self.annotate(f"Failover detected: {detail}", tags=["failover", "detected"], **kw)

    def recovery(self, detail: str = "", **kw: Any) -> bool:
        return self.annotate(f"Recovery complete: {detail}", tags=["recovery", "complete"], **kw)

    # -- accessors ----------------------------------------------------------

    @property
    def annotations(self) -> List[Dict[str, Any]]:
        return list(self._annotations)

    # -- internals ----------------------------------------------------------

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            import base64
            user = os.environ.get("GRAFANA_USER", "admin")
            pwd = os.environ.get("GRAFANA_PASSWORD", "admin")
            cred = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        return headers

    def _push(self, body: Dict[str, Any]) -> bool:
        url = f"{self.grafana_url}/api/annotations"
        status = _post_json(url, body, self._auth_headers())
        if status in (200, 201):
            logger.info("Annotation pushed: %s", body.get("text", ""))
            return True
        logger.warning("Annotation push returned status %s", status)
        return False


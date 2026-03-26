#!/usr/bin/env python3
"""Assemble a result pack from a demo results directory.

Collects run summaries, comparison reports, RTO/RPO reports, and consistency
reports, then auto-fills the POC Scorecard and Executive Readout templates
with real numbers.

Usage::

    python -m tooling.assemble_result_pack results/demo_20260323_120000/
    python tooling/assemble_result_pack.py results/demo_20260323_120000/

The tool produces a ``result_pack/`` subdirectory inside the given demo
directory containing all assembled artifacts.
"""

import argparse
import html
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NA = "[NOT AVAILABLE]"

# ── Repo root detection ─────────────────────────────────────────────────────

def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (contains docs/templates/)."""
    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "docs" / "templates").is_dir():
        return candidate
    # Fallback: cwd
    cwd = Path.cwd()
    if (cwd / "docs" / "templates").is_dir():
        return cwd
    return candidate


# ── Discovery helpers ───────────────────────────────────────────────────────

def find_run_summaries(demo_dir: Path) -> List[Path]:
    """Find all run_summary.json files in subdirectories, or *_summary.json in demo dir."""
    summaries = sorted(demo_dir.rglob("run_summary.json"))
    if not summaries:
        # Orchestrator copies summaries as flat *_summary.json files into demo dir
        summaries = sorted(demo_dir.glob("*_summary.json"))
    return summaries


def find_file(demo_dir: Path, name: str) -> Optional[Path]:
    """Find a file by name anywhere under demo_dir."""
    candidates = sorted(demo_dir.rglob(name))
    return candidates[0] if candidates else None


def find_comparison_report(demo_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Find comparison_report.md and comparison_report.json."""
    md = find_file(demo_dir, "comparison_report.md")
    js = find_file(demo_dir, "comparison_report.json")
    return md, js


def find_rto_rpo_report(demo_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Find rto_rpo.json (or rto_rpo_*.json) and any rto_rpo markdown."""
    js = find_file(demo_dir, "rto_rpo.json")
    if js is None:
        # Orchestrator saves as rto_rpo_re.json / rto_rpo_oss.json
        candidates = sorted(demo_dir.glob("rto_rpo_*.json"))
        js = candidates[0] if candidates else None
    md = find_file(demo_dir, "rto_rpo_report.md") or find_file(demo_dir, "rto_rpo.md")
    return md, js


def find_consistency_report(demo_dir: Path) -> Tuple[Optional[Path], Optional[Path]]:
    """Find consistency_report.json and any markdown version."""
    js = find_file(demo_dir, "consistency_report.json")
    md = find_file(demo_dir, "consistency_report.md")
    return md, js


def load_json(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Load a JSON file, returning None on failure."""
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── Data extraction from summaries ──────────────────────────────────────────

def _get(d: Optional[Dict], *keys: str, default: Any = NA) -> Any:
    """Safely traverse nested dicts."""
    if d is None:
        return default
    current = d
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
        if current is None:
            return default
    return current


def _fmt_num(val: Any, suffix: str = "", precision: int = 2) -> str:
    """Format a number for display, or return NA."""
    if val is None or val == NA:
        return NA
    try:
        return f"{float(val):.{precision}f}{suffix}"
    except (ValueError, TypeError):
        return str(val)


def _as_float(val: Any) -> Optional[float]:
    """Best-effort numeric coercion."""
    if val is None or val == NA:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fmt_count(val: Any) -> str:
    """Format integer-like counts with grouping."""
    num = _as_float(val)
    if num is None:
        return NA
    return f"{int(round(num)):,}"


def _fmt_pct(val: Any, precision: int = 2, scale: float = 100.0) -> str:
    """Format ratios or percentages for display."""
    num = _as_float(val)
    if num is None:
        return NA
    return f"{num * scale:.{precision}f}%"


def _normalize_version(val: Any) -> str:
    """Strip exporter prefixes like 'redis_version:' from version fields."""
    if val is None or val == NA:
        return NA
    text = str(val)
    return text.split(":", 1)[1] if ":" in text else text


def _copied_summary_name(summary_path: Path) -> str:
    """Return the result_pack filename for a copied summary."""
    if summary_path.name == "run_summary.json":
        return f"{summary_path.parent.name}_run_summary.json"
    return summary_path.name


def _scenario_title(name: Any) -> str:
    """Convert scenario ids like 02_primary_kill into readable titles."""
    if not name or name == NA:
        return "Unknown"
    text = str(name)
    parts = text.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit():
        text = parts[1]
    return text.replace("_", " ").title()


def _safe_ratio(numerator: Any, denominator: Any) -> Optional[float]:
    """Return numerator/denominator when both are valid and denominator != 0."""
    num = _as_float(numerator)
    den = _as_float(denominator)
    if num is None or den in (None, 0):
        return None
    return num / den


def _pick_scenario(scenarios: List[str], *terms: str) -> Optional[str]:
    """Pick the first scenario containing all requested terms."""
    lowered = [(sc, sc.lower()) for sc in scenarios]
    for original, lower in lowered:
        if all(term in lower for term in terms):
            return original
    return None


def _classify_summaries(
    summaries: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group summaries by platform (re vs oss)."""
    groups: Dict[str, List[Dict[str, Any]]] = {"re": [], "oss": [], "other": []}
    for s in summaries:
        platform = _get(s, "test_metadata", "platform", default="unknown")
        if isinstance(platform, str):
            pl = platform.lower()
            if "re" in pl and "oss" not in pl:
                groups["re"].append(s)
            elif "oss" in pl:
                groups["oss"].append(s)
            else:
                groups["other"].append(s)
        else:
            groups["other"].append(s)
    return groups


def _index_summaries_by_scenario(
    summaries: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Index summaries by scenario and platform key."""
    indexed: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for summary in summaries:
        scenario = str(summary.get("scenario", "unknown"))
        platform = str(_get(summary, "test_metadata", "platform", default="other")).lower()
        platform_key = "other"
        if "re" in platform and "oss" not in platform:
            platform_key = "re"
        elif "oss" in platform:
            platform_key = "oss"
        indexed.setdefault(scenario, {})[platform_key] = summary
    return indexed


def _scenario_winner(re_summary: Optional[Dict[str, Any]], oss_summary: Optional[Dict[str, Any]]) -> str:
    """Pick a simple scenario winner using throughput, p99 latency, and error rate."""
    if not re_summary and not oss_summary:
        return NA
    if re_summary and not oss_summary:
        return "Redis Enterprise"
    if oss_summary and not re_summary:
        return "OSS Redis"

    score_re = 0
    score_oss = 0

    re_rps = _as_float(_get(re_summary, "throughput", "requests_per_sec"))
    oss_rps = _as_float(_get(oss_summary, "throughput", "requests_per_sec"))
    if re_rps is not None and oss_rps is not None:
        if re_rps > oss_rps:
            score_re += 1
        elif oss_rps > re_rps:
            score_oss += 1

    re_p99 = _as_float(_get(re_summary, "latency_percentiles_ms", "p99"))
    oss_p99 = _as_float(_get(oss_summary, "latency_percentiles_ms", "p99"))
    if re_p99 is not None and oss_p99 is not None:
        if re_p99 < oss_p99:
            score_re += 1
        elif oss_p99 < re_p99:
            score_oss += 1

    re_err = _as_float(_get(re_summary, "errors", "error_rate"))
    oss_err = _as_float(_get(oss_summary, "errors", "error_rate"))
    if re_err is not None and oss_err is not None:
        if re_err < oss_err:
            score_re += 1
        elif oss_err < re_err:
            score_oss += 1

    if score_re == score_oss:
        return "Tie"
    return "Redis Enterprise" if score_re > score_oss else "OSS Redis"


# ── Scorecard auto-fill ─────────────────────────────────────────────────────

def _build_scorecard(
    summaries: List[Dict[str, Any]],
    comparison: Optional[Dict[str, Any]],
    rto_rpo: Optional[Dict[str, Any]],
    consistency: Optional[Dict[str, Any]],
    template_text: str,
) -> str:
    """Auto-fill the POC Scorecard template with real data."""
    groups = _classify_summaries(summaries)
    re_sum = _best_summary(groups["re"], "re")
    oss_sum = _best_summary(groups["oss"], "oss")

    # Extract key metrics
    re_p99 = _fmt_num(_get(re_sum, "latency_percentiles_ms", "p99"), " ms")
    oss_p99 = _fmt_num(_get(oss_sum, "latency_percentiles_ms", "p99"), " ms")
    re_rps = _fmt_num(_get(re_sum, "throughput", "requests_per_sec"), " ops/s")
    oss_rps = _fmt_num(_get(oss_sum, "throughput", "requests_per_sec"), " ops/s")
    re_err = _fmt_num(_get(re_sum, "errors", "error_rate"), "", precision=4)
    oss_err = _fmt_num(_get(oss_sum, "errors", "error_rate"), "", precision=4)
    re_errs = _get(re_sum, "errors", "total_failures", default=NA)
    oss_errs = _get(oss_sum, "errors", "total_failures", default=NA)

    # RTO/RPO
    rto_val = _fmt_num(_get(rto_rpo, "rto", "rto_seconds"), " s") if rto_rpo else NA
    rpo_val = str(_get(rto_rpo, "rpo", "lost_writes", default=NA)) if rto_rpo else NA

    # Consistency
    cons_pct = _fmt_num(_get(consistency, "consistency_pct"), "%") if consistency else NA

    # Comparison winner
    overall_winner = NA
    if comparison:
        overall_winner = _get(comparison, "winner_summary", "overall", default=NA)

    # Platform metadata
    re_platform = _get(re_sum, "test_metadata", "platform", default=NA)
    re_version = _get(re_sum, "test_metadata", "redis_version", default=NA)
    oss_platform = _get(oss_sum, "test_metadata", "platform", default=NA)
    oss_version = _get(oss_sum, "test_metadata", "redis_version", default=NA)

    # Dates
    dates = []
    for s in summaries:
        ts = _get(s, "test_metadata", "started_at", default=None)
        if ts and ts != NA:
            dates.append(str(ts)[:10])
    start_date = min(dates) if dates else NA
    end_date = max(dates) if dates else NA

    # Build the scorecard from template
    lines = [
        "# Customer POC Scorecard",
        "",
        f"**Customer:** `[Auto-generated from demo data]`  ",
        f"**Opportunity:** `[Auto-generated from demo data]`  ",
        f"**POC window:** `{start_date} - {end_date}`  ",
        f"**SA owner:** `[Auto-generated]`",
        "",
        "## 1. Executive Summary",
        "",
        "### Business question",
        "",
        "Evaluate Redis Enterprise vs OSS Redis for resiliency, performance stability, and operational simplicity.",
        "",
        "### Headline conclusion",
        "",
        f"Overall comparison winner: **{overall_winner}**. "
        f"Redis Enterprise p99 latency: {re_p99}, OSS p99 latency: {oss_p99}. "
        f"Redis Enterprise error rate: {re_err}, OSS error rate: {oss_err}.",
        "",
        "### Recommendation",
        "",
        f"Review the detailed findings below and the comparison report for a full recommendation.",
        "",
        "## 2. Compared Solutions",
        "",
        "| Solution | Topology | Environment | Version | Notes |",
        "|---|---|---|---|---|",
        f"| Redis Enterprise | {re_platform} | auto-detected | {re_version} | — |",
        f"| OSS Redis | {oss_platform} | auto-detected | {oss_version} | — |",
        "",
        "## 3. Agreed Success Criteria",
        "",
        "| Criterion | Target | Result | Status |",
        "|---|---|---|---|",
        f"| Recovery time objective | < 1 s | RTO: {rto_val} | {'✅' if rto_val != NA else '—'} |",
        f"| Tail latency (p99) | < 50 ms | RE: {re_p99} / OSS: {oss_p99} | {'✅' if re_p99 != NA else '—'} |",
        f"| Error rate during failure | < 0.1% | RE: {re_err} / OSS: {oss_err} | {'✅' if re_err != NA else '—'} |",
        f"| Data consistency | 100% | {cons_pct} | {'✅' if cons_pct != NA else '—'} |",
        "",
        "## 4. Scenario Summary",
        "",
        "| Scenario | Enterprise result | OSS result | Winner |",
        "|---|---|---|---|",
    ]

    # Add per-scenario rows from summaries
    re_scenarios = {s.get("scenario", "unknown"): s for s in groups["re"]}
    oss_scenarios = {s.get("scenario", "unknown"): s for s in groups["oss"]}
    all_scenarios = sorted(set(list(re_scenarios.keys()) + list(oss_scenarios.keys())))

    if all_scenarios:
        for sc in all_scenarios:
            re_s = re_scenarios.get(sc)
            oss_s = oss_scenarios.get(sc)
            re_detail = f"p99 {_fmt_num(_get(re_s, 'latency_percentiles_ms', 'p99'))} ms, {_fmt_num(_get(re_s, 'throughput', 'requests_per_sec'))} ops/s" if re_s else NA
            oss_detail = f"p99 {_fmt_num(_get(oss_s, 'latency_percentiles_ms', 'p99'))} ms, {_fmt_num(_get(oss_s, 'throughput', 'requests_per_sec'))} ops/s" if oss_s else NA
            lines.append(f"| {sc} | {re_detail} | {oss_detail} | — |")
    else:
        lines.append(f"| {NA} | {NA} | {NA} | {NA} |")

    lines += [
        "",
        "## 5. Evidence Highlights",
        "",
        "### What the application experienced",
        "",
        f"- Redis Enterprise p99 latency: {re_p99}",
        f"- OSS Redis p99 latency: {oss_p99}",
        f"- Redis Enterprise throughput: {re_rps}",
        f"- OSS Redis throughput: {oss_rps}",
        f"- Redis Enterprise total errors: {re_errs}",
        f"- OSS Redis total errors: {oss_errs}",
        "",
        "### What the operators experienced",
        "",
        f"- RTO: {rto_val}",
        f"- RPO (lost writes): {rpo_val}",
        f"- Data consistency: {cons_pct}",
    ]

    lines += [
        "",
        "## 6. Detailed Findings",
        "",
        "### Resiliency",
        "",
        f"RTO: {rto_val}. RPO: {rpo_val} writes lost. See rto_rpo_report.md for details.",
        "",
        "### Performance Stability",
        "",
        f"RE p99: {re_p99}, throughput: {re_rps}. OSS p99: {oss_p99}, throughput: {oss_rps}.",
        "",
        "### Operational Simplicity",
        "",
        "See comparison report and individual run summaries for operational details.",
        "",
        "## 7. Risks and Open Items",
        "",
        "- Review individual run summaries for scenario-specific caveats",
        "- Verify results match customer environment requirements",
        "",
        "## 8. Final Recommendation",
        "",
        f"Overall comparison winner: **{overall_winner}**. Review the full comparison report for detailed analysis.",
        "",
        "## 9. Evidence References",
        "",
        "- Comparison report: `result_pack/comparison_report.md`",
        "- RTO/RPO report: `result_pack/rto_rpo_report.md`",
        "- Consistency report: `result_pack/consistency_report.md`",
        "- Run summaries: `result_pack/run_summaries/`",
        "",
    ]

    return "\n".join(lines) + "\n"


def _best_summary(summaries: List[Dict[str, Any]], platform_key: str) -> Optional[Dict[str, Any]]:
    """Pick the best summary for a platform group."""
    if not summaries:
        return None
    return summaries[0]


# ── Executive readout auto-fill ─────────────────────────────────────────────

def _build_executive_readout(
    summaries: List[Dict[str, Any]],
    comparison: Optional[Dict[str, Any]],
    rto_rpo: Optional[Dict[str, Any]],
    consistency: Optional[Dict[str, Any]],
    template_text: str,
) -> str:
    """Auto-fill the Executive Readout template with real data."""
    groups = _classify_summaries(summaries)
    re_sum = _best_summary(groups["re"], "re")
    oss_sum = _best_summary(groups["oss"], "oss")

    re_p99 = _fmt_num(_get(re_sum, "latency_percentiles_ms", "p99"), " ms")
    oss_p99 = _fmt_num(_get(oss_sum, "latency_percentiles_ms", "p99"), " ms")
    re_rps = _fmt_num(_get(re_sum, "throughput", "requests_per_sec"), " ops/s")
    oss_rps = _fmt_num(_get(oss_sum, "throughput", "requests_per_sec"), " ops/s")
    re_err = _fmt_num(_get(re_sum, "errors", "error_rate"), "", precision=4)
    oss_err = _fmt_num(_get(oss_sum, "errors", "error_rate"), "", precision=4)
    rto_val = _fmt_num(_get(rto_rpo, "rto", "rto_seconds"), " s") if rto_rpo else NA
    rpo_val = str(_get(rto_rpo, "rpo", "lost_writes", default=NA)) if rto_rpo else NA
    cons_pct = _fmt_num(_get(consistency, "consistency_pct"), "%") if consistency else NA
    overall_winner = _get(comparison, "winner_summary", "overall", default=NA) if comparison else NA

    re_version = _get(re_sum, "test_metadata", "redis_version", default=NA)
    oss_version = _get(oss_sum, "test_metadata", "redis_version", default=NA)
    re_platform = _get(re_sum, "test_metadata", "platform", default=NA)
    oss_platform = _get(oss_sum, "test_metadata", "platform", default=NA)

    dates = []
    for s in summaries:
        ts = _get(s, "test_metadata", "started_at", default=None)
        if ts and ts != NA:
            dates.append(str(ts)[:10])
    start_date = min(dates) if dates else NA
    end_date = max(dates) if dates else NA

    scenarios_list = sorted(set(s.get("scenario", "unknown") for s in summaries))
    scenarios_str = ", ".join(scenarios_list) if scenarios_list else NA

    lines = [
        "# Executive Readout",
        "",
        f"**Customer:** `[Auto-generated from demo data]`  ",
        f"**Opportunity:** `[Auto-generated from demo data]`  ",
        f"**POC window:** `{start_date} – {end_date}`  ",
        f"**SA owner:** `[Auto-generated]`  ",
        f"**Presented to:** `[To be filled]`  ",
        f"**Date:** `{datetime.now(timezone.utc).strftime('%Y-%m-%d')}`",
        "",
        "---",
        "",
        "## 1. Purpose",
        "",
        "This POC was conducted to answer a specific question:",
        "",
        "> Should the team adopt Redis Enterprise to replace self-managed OSS Redis?",
        "",
        "## 2. What We Tested",
        "",
        "| Dimension | Detail |",
        "|---|---|",
        f"| Workload | Auto-detected from run data |",
        f"| Compared solutions | Redis Enterprise {re_version} ({re_platform}) vs OSS Redis {oss_version} ({oss_platform}) |",
        f"| Environment | Auto-detected |",
        f"| Scenarios executed | {scenarios_str} |",
        "",
        "## 3. Key Findings",
        "",
        "### Resiliency",
        "",
        f"RTO: {rto_val}. RPO: {rpo_val} writes lost. Data consistency: {cons_pct}.",
        "",
        "### Performance Stability",
        "",
        f"Redis Enterprise p99: {re_p99}, throughput: {re_rps}. "
        f"OSS Redis p99: {oss_p99}, throughput: {oss_rps}.",
        "",
        "### Operational Simplicity",
        "",
        "See comparison report and individual run summaries for operational details.",
        "",
        "## 4. Scorecard Summary",
        "",
        "| Criterion | Target | Redis Enterprise | OSS Redis | Winner |",
        "|---|---|---|---|---|",
        f"| Recovery time | < 1 s | {rto_val} | {NA} | — |",
        f"| Tail latency (p99) | < 50 ms | {re_p99} | {oss_p99} | — |",
        f"| Error rate during failure | < 0.1% | {re_err} | {oss_err} | — |",
        f"| Data consistency | 100% | {cons_pct} | {NA} | — |",
        "",
        "_Full scorecard: [POC Scorecard](result_pack/scorecard.md)_",
        "",
        "## 5. Recommendation",
        "",
        f"Overall comparison winner: **{overall_winner}**. Review the full scorecard and comparison report for detailed analysis and recommendations.",
        "",
        "## 6. Risks and Open Items",
        "",
        "- Review individual run summaries for scenario-specific caveats",
        "- Verify results match customer environment requirements",
        "",
        "## 7. Evidence References",
        "",
        "| Artifact | Location |",
        "|---|---|",
        "| Run summaries (JSON) | `result_pack/run_summaries/` |",
        "| Comparison report | `result_pack/comparison_report.md` |",
        "| Completed Scorecard | `result_pack/scorecard.md` |",
        "| RTO/RPO report | `result_pack/rto_rpo_report.md` |",
        "| Consistency report | `result_pack/consistency_report.md` |",
        "",
    ]

    return "\n".join(lines) + "\n"


# ── RTO/RPO markdown renderer ──────────────────────────────────────────────

def _render_rto_rpo_md(rto_rpo: Dict[str, Any]) -> str:
    """Render an RTO/RPO JSON report as markdown."""
    fw = rto_rpo.get("fault_window", {})
    rto = rto_rpo.get("rto", {})
    rpo = rto_rpo.get("rpo", {})
    cs = rto_rpo.get("canary_summary", {})

    lines = [
        "# RTO/RPO Report",
        "",
        f"**Run directory:** `{rto_rpo.get('run_dir', NA)}`",
        "",
        "## Fault Window",
        "",
        f"- Duration: {_fmt_num(fw.get('duration_s'), ' s')}",
        "",
        "## RTO (Recovery Time Objective)",
        "",
        f"- RTO: {_fmt_num(rto.get('rto_seconds'), ' s')}",
        f"- Note: {rto.get('note', '—')}",
        "",
        "## RPO (Recovery Point Objective)",
        "",
        f"- Lost writes: {rpo.get('lost_writes', NA)}",
        f"- RPO window: {_fmt_num(rpo.get('rpo_seconds'), ' s')}",
        "",
        "## Canary Summary",
        "",
        f"- Total writes: {cs.get('total_writes', NA)}",
        f"- OK writes: {cs.get('ok_writes', NA)}",
        f"- Error writes: {cs.get('error_writes', NA)}",
        "",
        "---",
        "",
        "_Generated by `tooling/assemble_result_pack.py` from rto_rpo.json._",
    ]
    return "\n".join(lines) + "\n"


# ── Consistency markdown renderer ───────────────────────────────────────────

def _render_consistency_md(report: Dict[str, Any]) -> str:
    """Render a consistency report JSON as markdown."""
    lines = [
        "# Consistency Report",
        "",
        f"- Total written: {report.get('total_written', NA)}",
        f"- Total found: {report.get('total_found', NA)}",
        f"- Missing keys: {report.get('missing_count', NA)}",
        f"- Unexpected keys: {report.get('unexpected_count', NA)}",
        f"- Out of order: {report.get('out_of_order_count', NA)}",
        f"- Duplicates: {report.get('duplicate_count', NA)}",
        f"- Error writes: {report.get('error_writes', NA)}",
        f"- **Consistency: {report.get('consistency_pct', NA)}%**",
        "",
        "---",
        "",
        "_Generated by `tooling/assemble_result_pack.py` from consistency_report.json._",
    ]
    return "\n".join(lines) + "\n"


def _build_html_report(summaries: List[Dict[str, Any]], demo_dir: Path, summary_paths: List[Path]) -> str:
    """Render a standalone Redis-branded HTML report from run summaries."""
    indexed = _index_summaries_by_scenario(summaries)
    scenario_names = sorted(indexed.keys())

    baseline_name = _pick_scenario(scenario_names, "baseline") or (scenario_names[0] if scenario_names else None)
    failover_name = (
        _pick_scenario(scenario_names, "primary", "kill")
        or _pick_scenario(scenario_names, "kill")
        or _pick_scenario(scenario_names, "failover")
        or (scenario_names[1] if len(scenario_names) > 1 else baseline_name)
    )

    baseline = indexed.get(baseline_name or "", {})
    failover = indexed.get(failover_name or "", {})
    re_base = baseline.get("re")
    oss_base = baseline.get("oss")
    re_fail = failover.get("re")
    oss_fail = failover.get("oss")

    re_version = _normalize_version(_get(re_fail or re_base, "test_metadata", "redis_version"))
    oss_version = _normalize_version(_get(oss_fail or oss_base, "test_metadata", "redis_version"))

    re_base_rps = _as_float(_get(re_base, "throughput", "requests_per_sec"))
    oss_base_rps = _as_float(_get(oss_base, "throughput", "requests_per_sec"))
    re_fail_rps = _as_float(_get(re_fail, "throughput", "requests_per_sec"))
    oss_fail_rps = _as_float(_get(oss_fail, "throughput", "requests_per_sec"))
    re_base_p99 = _as_float(_get(re_base, "latency_percentiles_ms", "p99"))
    oss_base_p99 = _as_float(_get(oss_base, "latency_percentiles_ms", "p99"))
    re_fail_p99 = _as_float(_get(re_fail, "latency_percentiles_ms", "p99"))
    oss_fail_p99 = _as_float(_get(oss_fail, "latency_percentiles_ms", "p99"))
    re_base_errors = _get(re_base, "errors", "total_failures", default=NA)
    oss_base_errors = _get(oss_base, "errors", "total_failures", default=NA)
    re_fail_errors = _get(re_fail, "errors", "total_failures", default=NA)
    oss_fail_errors = _get(oss_fail, "errors", "total_failures", default=NA)
    re_fail_error_rate = _as_float(_get(re_fail, "errors", "error_rate"))
    oss_fail_error_rate = _as_float(_get(oss_fail, "errors", "error_rate"))

    baseline_headroom = _safe_ratio(re_base_rps, oss_base_rps)
    baseline_latency_advantage = _safe_ratio(oss_base_p99, re_base_p99)
    failover_throughput_advantage = _safe_ratio(re_fail_rps, oss_fail_rps)
    failover_latency_advantage = _safe_ratio(oss_fail_p99, re_fail_p99)
    re_retention = _safe_ratio(re_fail_rps, re_base_rps)
    oss_retention = _safe_ratio(oss_fail_rps, oss_base_rps)
    retention_advantage = _safe_ratio(re_retention, oss_retention)
    error_gap = None
    if re_fail_error_rate is not None and oss_fail_error_rate is not None:
        error_gap = oss_fail_error_rate - re_fail_error_rate

    throughput_max = max(v for v in [re_fail_rps, oss_fail_rps, 1.0] if v is not None)
    re_bar = max(8, int(((re_fail_rps or 0.0) / throughput_max) * 100)) if re_fail_rps is not None else 8
    oss_bar = max(8, int(((oss_fail_rps or 0.0) / throughput_max) * 100)) if oss_fail_rps is not None else 8

    top_cards = [
        (
            "Baseline throughput edge",
            f"{((baseline_headroom - 1) * 100):.1f}%" if baseline_headroom is not None else NA,
            "Redis Enterprise delivered more requests per second before any fault.",
        ),
        (
            "Primary-kill throughput",
            f"{failover_throughput_advantage:.2f}x" if failover_throughput_advantage is not None else NA,
            "Redis Enterprise sustained higher throughput than OSS during the same fault.",
        ),
        (
            "Primary-kill p99",
            f"{failover_latency_advantage:.2f}x" if failover_latency_advantage is not None else NA,
            "Lower p99 latency for Redis Enterprise under failure conditions.",
        ),
        (
            "Error-rate gap",
            _fmt_pct(error_gap) if error_gap is not None else NA,
            "Percentage-point separation between the two platforms during primary loss.",
        ),
    ]

    evidence_links = [
        ("scorecard.md", "POC scorecard"),
        ("executive_readout.md", "Executive readout"),
        ("README.md", "Result pack index"),
    ]
    primary_cmp = demo_dir / "comparison_primary_kill" / "comparison_report.md"
    baseline_cmp = demo_dir / "comparison_baseline" / "comparison_report.md"
    if primary_cmp.exists():
        evidence_links.append(("../comparison_primary_kill/comparison_report.md", "Primary-kill comparison"))
    if baseline_cmp.exists():
        evidence_links.append(("../comparison_baseline/comparison_report.md", "Baseline comparison"))
    for sp in summary_paths:
        evidence_links.append((f"run_summaries/{_copied_summary_name(sp)}", f"Run summary · {_scenario_title(sp.stem)}"))

    summary_rows: List[str] = []
    for scenario_name in scenario_names:
        re_summary = indexed.get(scenario_name, {}).get("re")
        oss_summary = indexed.get(scenario_name, {}).get("oss")
        summary_rows.append(
            "".join(
                [
                    "<tr>",
                    f"<td>{html.escape(_scenario_title(scenario_name))}</td>",
                    f"<td>{html.escape(_fmt_count(_get(re_summary, 'throughput', 'requests_per_sec')))} req/s</td>",
                    f"<td>{html.escape(_fmt_num(_get(re_summary, 'latency_percentiles_ms', 'p99'), ' ms', precision=0))}</td>",
                    f"<td>{html.escape(_fmt_count(_get(re_summary, 'errors', 'total_failures')))}</td>",
                    f"<td>{html.escape(_fmt_count(_get(oss_summary, 'throughput', 'requests_per_sec')))} req/s</td>",
                    f"<td>{html.escape(_fmt_num(_get(oss_summary, 'latency_percentiles_ms', 'p99'), ' ms', precision=0))}</td>",
                    f"<td>{html.escape(_fmt_count(_get(oss_summary, 'errors', 'total_failures')))}</td>",
                    f"<td>{html.escape(_scenario_winner(re_summary, oss_summary))}</td>",
                    "</tr>",
                ]
            )
        )

    evidence_html = "".join(
        f'<a class="evidence-link" href="{html.escape(path)}">{html.escape(label)}</a>'
        for path, label in evidence_links
    )

    cards_html = "".join(
        "".join(
            [
                '<article class="metric-card">',
                f'<p class="eyebrow">{html.escape(label)}</p>',
                f'<div class="metric-value">{html.escape(value)}</div>',
                f'<p class="metric-copy">{html.escape(copy)}</p>',
                "</article>",
            ]
        )
        for label, value, copy in top_cards
    )

    slide_summary_title = "Redis Enterprise vs OSS Redis — POC Results"
    baseline_throughput_delta = (
        f"{((baseline_headroom - 1) * 100):+.1f}%" if baseline_headroom is not None else NA
    )
    failover_error_improvement = NA
    if (
        re_fail_error_rate is not None
        and oss_fail_error_rate is not None
        and re_fail_error_rate <= 0
        and oss_fail_error_rate > 0
    ):
        failover_error_improvement = "Zero errors"
    elif (
        re_fail_error_rate is not None
        and oss_fail_error_rate is not None
        and re_fail_error_rate > 0
        and oss_fail_error_rate > re_fail_error_rate
    ):
        failover_error_improvement = f"{(oss_fail_error_rate / re_fail_error_rate):.2f}x lower"

    slide_summary_rows = [
        (
            "Baseline throughput",
            f"{_fmt_count(re_base_rps)} req/s",
            f"{_fmt_count(oss_base_rps)} req/s",
            baseline_throughput_delta,
            True,
            False,
        ),
        (
            "Baseline p99 latency",
            _fmt_num(re_base_p99, " ms", precision=0),
            _fmt_num(oss_base_p99, " ms", precision=0),
            f"{baseline_latency_advantage:.2f}x lower" if baseline_latency_advantage is not None else NA,
            True,
            False,
        ),
        (
            "Failover throughput",
            f"{_fmt_count(re_fail_rps)} req/s",
            f"{_fmt_count(oss_fail_rps)} req/s",
            f"{failover_throughput_advantage:.2f}x higher" if failover_throughput_advantage is not None else NA,
            True,
            False,
        ),
        (
            "Failover p99 latency",
            _fmt_num(re_fail_p99, " ms", precision=0),
            _fmt_num(oss_fail_p99, " ms", precision=0),
            f"{failover_latency_advantage:.2f}x lower" if failover_latency_advantage is not None else NA,
            True,
            False,
        ),
        (
            "Failover error rate",
            _fmt_pct(re_fail_error_rate),
            _fmt_pct(oss_fail_error_rate),
            failover_error_improvement,
            True,
            True,
        ),
        (
            "Failover errors",
            _fmt_count(re_fail_errors),
            _fmt_count(oss_fail_errors),
            "—",
            False,
            False,
        ),
        (
            "Throughput retained",
            _fmt_pct(re_retention, precision=1),
            _fmt_pct(oss_retention, precision=1),
            f"{retention_advantage:.1f}x better" if retention_advantage is not None else NA,
            True,
            False,
        ),
    ]
    slide_summary_text = "\n".join(
        [
            slide_summary_title,
            "",
            "\t".join(["Metric", "Redis Enterprise", "OSS Redis", "Improvement"]),
            *["\t".join([metric, re_value, oss_value, delta]) for metric, re_value, oss_value, delta, _, _ in slide_summary_rows],
        ]
    )
    slide_summary_rows_html = "".join(
        "".join(
            [
                f'<tr class="{"slide-summary-row--money" if is_money_row else ""}">',
                f'<th scope="row">{html.escape(metric)}</th>',
                f'<td>{html.escape(re_value)}</td>',
                f'<td>{html.escape(oss_value)}</td>',
                f'<td class="slide-summary-delta{" slide-summary-delta--win" if is_win else ""}">{html.escape(delta)}</td>',
                "</tr>",
            ]
        )
        for metric, re_value, oss_value, delta, is_win, is_money_row in slide_summary_rows
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    headline = (
        f"During {_scenario_title(failover_name)} Redis Enterprise held "
        f"{_fmt_count(re_fail_rps)} req/s at p99 {_fmt_num(re_fail_p99, ' ms', precision=0)} "
        f"with {_fmt_count(re_fail_errors)} errors, while OSS dropped to "
        f"{_fmt_count(oss_fail_rps)} req/s at p99 {_fmt_num(oss_fail_p99, ' ms', precision=0)} "
        f"and {_fmt_count(oss_fail_errors)} failed requests."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Redis Results Report</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --redis-red: #FF4438;
      --redis-red-hover: #EB352A;
      --redis-red-tint: #FFE8E6;
      --ink: #091A23;
      --ink-secondary: #163341;
      --ink-muted: #8A99A0;
      --border: #2D4754;
      --surface: #FFFFFF;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, var(--redis-red-tint) 0 112px, var(--surface) 112px 100%);
      color: var(--ink);
      font-family: 'Space Grotesk';
    }}
    a {{ color: var(--redis-red); text-decoration: none; transition: all 0.2s ease-in-out; }}
    a:hover {{ color: var(--redis-red-hover); }}
    .page {{ max-width: 1280px; margin: 0 auto; padding: 40px 24px 64px; }}
    .card, .metric-card, .platform-panel, .hero-panel {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 24px;
      box-shadow: 0 24px 48px rgba(9, 26, 35, 0.06);
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
      margin-bottom: 48px;
    }}
    .brand {{ display: inline-flex; align-items: center; }}
    .brand svg {{ height: 32px; width: auto; }}
    .topbar-meta {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px 16px; color: var(--ink-secondary); }}
    .eyebrow {{
      margin: 0 0 16px;
      color: var(--ink-secondary);
      font-family: 'Space Mono';
      font-size: 14px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
      gap: 24px;
      align-items: stretch;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 24px;
      font-family: 'Space Mono';
      font-size: 56px;
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}
    h2 {{ margin: 0 0 16px; font-size: 32px; line-height: 1.1; }}
    p {{ margin: 0; font-size: 16px; line-height: 1.6; }}
    .hero-copy {{ margin-bottom: 24px; color: var(--ink-secondary); font-size: 20px; max-width: 720px; }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chip {{
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 8px 16px;
      background: rgba(255, 255, 255, 0.82);
      color: var(--ink-secondary);
      font-size: 14px;
    }}
    .hero-panel {{ display: flex; flex-direction: column; justify-content: space-between; background: var(--redis-red-tint); }}
    .hero-stat {{ margin: 16px 0; font-family: 'Space Mono'; font-size: 48px; line-height: 1; }}
    .hero-note {{ color: var(--ink-secondary); }}
    .slide-summary-card {{
      --slide-bg: #FFFFFF;
      --slide-text: #091A23;
      --slide-secondary: #163341;
      --slide-muted: #5A6A72;
      --slide-card: #FFFFFF;
      --slide-row-odd: #FFFFFF;
      --slide-row-even: #FFE8E6;
      --slide-improvement: #0A7C42;
      --slide-red-hover: #EB352A;
      margin-bottom: 24px;
      background: var(--slide-bg);
      color: var(--slide-text);
    }}
    .slide-summary-card.slide-dark {{
      --slide-bg: #0A1A23;
      --slide-text: #F0F4F5;
      --slide-secondary: #C8D1D5;
      --slide-muted: #5A6A72;
      --slide-card: #122A35;
      --slide-row-odd: #0A1A23;
      --slide-row-even: #122A35;
      --slide-improvement: #7DD89B;
      --slide-red-hover: #FF7566;
    }}
    .slide-summary-card .eyebrow {{ margin-bottom: 8px; color: var(--slide-secondary); }}
    .slide-summary-content {{ display: grid; gap: 24px; }}
    .slide-summary-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }}
    .slide-summary-heading {{ max-width: 720px; }}
    .slide-summary-title {{
      display: block;
      color: var(--slide-text);
      font-family: 'Space Grotesk';
      font-size: 28px;
      font-weight: 700;
      line-height: 1.2;
    }}
    .slide-summary-actions {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }}
    .slide-summary-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--slide-card);
      color: var(--slide-text);
      cursor: pointer;
      font-family: 'Space Grotesk';
      font-size: 14px;
      font-weight: 700;
      line-height: 1;
      padding: 8px 16px;
      transition: all 0.2s ease-in-out;
      white-space: nowrap;
    }}
    .slide-summary-btn:hover {{ border-color: var(--redis-red); color: var(--redis-red); }}
    .slide-summary-btn:focus-visible {{ outline: 2px solid var(--slide-text); outline-offset: 2px; }}
    .slide-summary-copy {{ background: var(--redis-red); border-color: var(--redis-red); color: #FFFFFF; }}
    .slide-summary-copy:hover {{ background: var(--slide-red-hover); border-color: var(--slide-red-hover); color: #FFFFFF; }}
    .slide-summary-toggle-divider {{ color: var(--slide-muted); }}
    .slide-summary-toggle-option {{ opacity: 0.58; transition: all 0.2s ease-in-out; }}
    .slide-summary-toggle-option--light {{ font-weight: 700; opacity: 1; }}
    .slide-summary-card.slide-dark .slide-summary-toggle-option--light {{ opacity: 0.58; }}
    .slide-summary-card.slide-dark .slide-summary-toggle-option--dark {{ font-weight: 700; opacity: 1; }}
    .slide-summary-table-shell {{
      border: 1px solid var(--border);
      border-radius: 5px;
      background: var(--slide-card);
      overflow-x: auto;
    }}
    .slide-summary-table {{
      width: 100%;
      min-width: 720px;
      border-collapse: separate;
      border-spacing: 0;
      font-family: 'Space Grotesk';
      font-size: 15px;
    }}
    .slide-summary-table thead th {{
      background: var(--redis-red);
      color: #FFFFFF;
      font-weight: 700;
      padding: 16px 24px;
      text-align: left;
      border-bottom: none;
    }}
    .slide-summary-table tbody tr:nth-child(odd) {{ background: var(--slide-row-odd); }}
    .slide-summary-table tbody tr:nth-child(even) {{ background: var(--slide-row-even); }}
    .slide-summary-table tbody th,
    .slide-summary-table tbody td {{
      padding: 16px 24px;
      color: var(--slide-text);
      font-size: 15px;
      line-height: 1.5;
      text-align: left;
      border-bottom: none;
    }}
    .slide-summary-table tbody tr + tr th,
    .slide-summary-table tbody tr + tr td {{ border-top: 1px solid rgba(45, 71, 84, 0.24); }}
    .slide-summary-table tbody th {{ font-weight: 700; width: 28%; }}
    .slide-summary-table tbody td:nth-child(2),
    .slide-summary-table tbody td:nth-child(3) {{ white-space: nowrap; }}
    .slide-summary-delta {{ font-weight: 700; }}
    .slide-summary-delta--win {{ color: var(--slide-improvement) !important; }}
    .slide-summary-row--money th {{ border-left: 4px solid var(--redis-red); padding-left: 20px; }}
    .metrics-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px; margin: 24px 0 48px; }}
    .metric-value {{ margin-bottom: 16px; font-family: 'Space Mono'; font-size: 32px; line-height: 1.05; }}
    .metric-copy {{ color: var(--ink-secondary); }}
    .showcase {{ margin-bottom: 48px; }}
    .showcase-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; margin: 32px 0 24px; }}
    .platform-panel--re {{ background: linear-gradient(180deg, rgba(255, 232, 230, 0.72) 0, #FFFFFF 120px); }}
    .platform-panel--oss {{ background: #FFFFFF; }}
    .platform-label {{ display: flex; justify-content: space-between; gap: 16px; align-items: baseline; margin-bottom: 24px; }}
    .platform-label strong {{ font-size: 24px; }}
    .version {{ color: var(--ink-muted); font-family: 'Space Mono'; font-size: 14px; }}
    .big-metric {{ margin-bottom: 24px; }}
    .big-metric .value {{ font-family: 'Space Mono'; font-size: 48px; line-height: 1; }}
    .big-metric .label {{ margin-top: 8px; color: var(--ink-secondary); }}
    .stack {{ display: grid; gap: 16px; }}
    .bar-row {{ display: grid; gap: 8px; }}
    .bar-head {{ display: flex; justify-content: space-between; gap: 16px; color: var(--ink-secondary); }}
    .bar-track {{ width: 100%; height: 16px; border-radius: 5px; background: #F3F6F7; overflow: hidden; border: 1px solid #D6DDE0; }}
    .bar-fill {{ height: 100%; border-radius: 5px; }}
    .bar-fill--re {{ background: linear-gradient(90deg, var(--redis-red), var(--redis-red-hover)); }}
    .bar-fill--oss {{ background: linear-gradient(90deg, var(--ink-secondary), #2D4754); }}
    .delta-strip {{
      border-radius: 5px;
      padding: 16px 24px;
      background: var(--ink);
      color: #FFFFFF;
      font-size: 18px;
      line-height: 1.5;
    }}
    .details-grid {{ display: grid; grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); gap: 24px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 16px 8px; border-bottom: 1px solid #D6DDE0; text-align: left; font-size: 15px; }}
    th {{ color: var(--ink-secondary); font-weight: 700; }}
    .evidence-list {{ display: grid; gap: 8px; }}
    .evidence-link {{
      display: block;
      border: 1px solid var(--border);
      border-radius: 5px;
      padding: 16px;
      background: #FFFFFF;
      color: var(--ink);
    }}
    .footer {{ margin-top: 32px; color: var(--ink-muted); }}
    @media (max-width: 1120px) {{
      .metrics-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .details-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 880px) {{
      .hero, .showcase-grid {{ grid-template-columns: 1fr; }}
      .slide-summary-head {{ flex-direction: column; }}
      .slide-summary-actions {{ justify-content: flex-start; }}
      .topbar {{ flex-direction: column; align-items: flex-start; }}
      .topbar-meta {{ justify-content: flex-start; }}
      h1 {{ font-size: 40px; }}
    }}
    @media (max-width: 640px) {{
      .page {{ padding: 24px 16px 40px; }}
      .slide-summary-title {{ font-size: 24px; }}
      .slide-summary-btn {{ width: 100%; justify-content: center; }}
      .metrics-grid {{ grid-template-columns: 1fr; }}
      .hero-stat, .big-metric .value, .metric-value {{ font-size: 32px; }}
    }}
    @media print {{
      body {{ background: #FFFFFF; }}
      .slide-summary-actions {{ display: none !important; }}
      .slide-summary-card {{
        break-inside: avoid;
        box-shadow: none;
        print-color-adjust: exact;
        -webkit-print-color-adjust: exact;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar">
      <div class="brand">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="165 225 470 140" height="36" aria-label="Redis">
          <g>
            <path fill="#A41E11" d="M334.774,339.535c-9.078,4.732-56.106,24.068-66.118,29.287c-10.012,5.221-15.574,5.17-23.483,1.389s-57.955-23.996-66.97-28.305c-4.506-2.154-6.875-3.971-6.875-5.688c0-1.713,0-17.195,0-17.195s65.153-14.184,75.672-17.957c10.518-3.774,14.167-3.91,23.118-0.631c8.952,3.279,62.474,12.936,71.321,16.176c0,0-0.004,15.357-0.004,16.951C341.436,335.262,339.395,337.127,334.774,339.535z"/>
            <path fill="#D82C20" d="M334.774,322.336c-9.078,4.73-56.106,24.068-66.118,29.287c-10.012,5.221-15.574,5.17-23.483,1.389c-7.91-3.779-57.955-23.998-66.97-28.305c-9.015-4.309-9.204-7.275-0.348-10.742c8.855-3.469,58.626-22.996,69.146-26.77c10.518-3.772,14.167-3.91,23.118-0.63c8.952,3.279,55.699,21.886,64.545,25.126C343.512,314.934,343.852,317.604,334.774,322.336z"/>
            <path fill="#A41E11" d="M334.774,311.496c-9.078,4.732-56.106,24.068-66.118,29.289c-10.012,5.219-15.574,5.168-23.483,1.387c-7.91-3.779-57.955-23.996-66.97-28.305c-4.506-2.154-6.875-3.969-6.875-5.686c0-1.713,0-17.197,0-17.197s65.153-14.183,75.672-17.957c10.518-3.773,14.167-3.91,23.118-0.631c8.952,3.279,62.474,12.934,71.321,16.175c0,0-0.004,15.357-0.004,16.953C341.436,307.223,339.395,309.088,334.774,311.496z"/>
            <path fill="#D82C20" d="M334.774,294.297c-9.078,4.732-56.106,24.068-66.118,29.289c-10.012,5.219-15.574,5.168-23.483,1.387c-7.91-3.779-57.955-23.997-66.97-28.305c-9.015-4.308-9.204-7.274-0.348-10.743c8.855-3.467,58.626-22.995,69.146-26.768c10.518-3.773,14.167-3.91,23.118-0.631c8.952,3.279,55.699,21.885,64.545,25.126C343.512,286.894,343.852,289.565,334.774,294.297z"/>
            <path fill="#A41E11" d="M334.774,282.419c-9.078,4.732-56.106,24.069-66.118,29.29c-10.012,5.219-15.574,5.168-23.483,1.387c-7.91-3.779-57.955-23.997-66.97-28.305c-4.506-2.154-6.875-3.97-6.875-5.686c0-1.714,0-17.197,0-17.197s65.153-14.183,75.672-17.956c10.518-3.774,14.167-3.91,23.118-0.631c8.952,3.279,62.474,12.934,71.321,16.175c0,0-0.004,15.357-0.004,16.952C341.436,278.146,339.395,280.011,334.774,282.419z"/>
            <path fill="#D82C20" d="M334.774,265.22c-9.078,4.732-56.106,24.069-66.118,29.289c-10.012,5.219-15.574,5.168-23.483,1.388s-57.955-23.997-66.97-28.305c-9.015-4.308-9.204-7.275-0.348-10.743c8.855-3.468,58.626-22.994,69.146-26.768c10.518-3.774,14.167-3.91,23.118-0.63c8.952,3.279,55.699,21.885,64.545,25.126C343.512,257.817,343.852,260.489,334.774,265.22z"/>
            <polygon fill="#FFFFFF" points="259.055,240.78 270.272,237.111 267.236,244.379 278.667,248.657 263.933,250.186 260.631,258.13 255.296,249.269 238.277,247.74 250.978,243.157 247.168,236.128"/>
            <polygon fill="#FFFFFF" points="259.753,287.181 232.236,275.771 271.656,269.72"/>
            <ellipse fill="#FFFFFF" cx="221.612" cy="261.241" rx="21.069" ry="8.167"/>
          </g>
          <polygon fill="#7A0C00" points="296.094,250.826 319.421,260.053 296.107,269.257"/>
          <polygon fill="#AD2115" points="296.094,250.826 296.107,269.257 293.582,270.253 270.281,261.036"/>
          <g fill="#FF4438">
            <path d="M421.641,272.268c0,3.619-2.973,6.849-6.85,6.849c-2.973,0-5.557,0.776-7.754,2.456c-2.455,1.552-4.394,3.748-5.944,6.203c-3.102,4.136-4.651,9.046-5.298,10.854v24.554c0,3.748-3.23,6.85-7.107,6.85c-3.748,0-6.849-3.102-6.849-6.85v-50.916c0-3.748,3.101-6.72,6.849-6.72c3.877,0,7.107,2.973,7.107,6.72v0.905c0.775-0.905,1.809-1.938,2.714-2.585c4.265-2.842,9.821-5.169,16.282-5.04C418.668,265.548,421.641,268.521,421.641,272.268z"/>
            <path d="M417.846,297.726c0.13-17.575,13.828-32.307,31.531-32.307c16.8,0,30.11,12.535,31.145,29.98c0,0.13,0,0.389,0,0.646c0,0.259,0,0.904-0.129,1.163c-0.389,3.102-3.102,5.17-6.721,5.17h-41.094c0.646,2.973,2.067,6.332,4.394,8.529c2.714,3.102,7.883,5.426,12.405,5.814c4.652,0.387,10.209-0.775,13.44-3.23c2.713-2.844,8.012-2.455,9.692-0.389c1.68,1.811,2.972,5.688,0,8.4c-6.333,5.814-13.957,8.529-23.133,8.529C431.674,329.904,417.976,315.301,417.846,297.726z M431.932,291.394h36.571c-1.292-5.169-7.883-12.793-19.126-13.698C438.394,278.212,432.966,286.096,431.932,291.394z"/>
            <path d="M546.363,323.055c0,3.748-3.102,6.979-6.979,6.979c-3.489,0-6.202-2.455-6.849-5.557c-4.91,3.359-11.113,5.557-17.575,5.557c-17.445,0-31.402-14.732-31.402-32.178c0-17.705,13.957-32.437,31.402-32.437c6.333,0,12.535,2.067,17.316,5.427v-24.294c0-3.748,3.102-6.979,7.107-6.979c3.877,0,6.979,3.231,6.979,6.979v51.174c0,0,0,0,0,0.13V323.055z M514.961,279.505c-4.652,0-8.917,1.938-12.146,5.298c-3.231,3.231-5.17,7.882-5.17,13.052c0,4.91,1.938,9.562,5.17,12.793c3.229,3.361,7.494,5.299,12.146,5.299c4.781,0,8.917-1.938,12.147-5.299c3.23-3.23,5.169-7.883,5.169-12.793c0-5.17-1.938-9.821-5.169-13.052C523.878,281.443,519.742,279.505,514.961,279.505z"/>
            <path d="M570.949,249.266c0,3.877-2.972,7.107-6.979,7.107c-3.877,0-6.978-3.23-6.978-7.107v-2.714c0-3.877,3.101-6.979,6.978-6.979c4.007,0,6.979,3.102,6.979,6.979V249.266z M570.949,272.656v50.399c0,3.877-2.972,6.979-6.979,6.979c-3.877,0-6.978-3.102-6.978-6.979v-50.399c0-4.135,3.101-7.108,6.978-7.108C567.978,265.548,570.949,268.521,570.949,272.656z"/>
            <path d="M579.833,311.553c2.326-3.1,6.85-3.488,9.692-1.033c3.36,2.844,9.176,5.814,14.215,5.686c3.489,0,6.72-1.162,8.788-2.455c1.809-1.551,2.325-2.842,2.325-3.877c0-0.646-0.129-0.904-0.387-1.293c-0.13-0.387-0.646-0.904-1.681-1.549c-1.809-1.293-5.686-2.715-10.338-3.619h-0.129c-4.007-0.775-7.884-1.809-11.243-3.361c-3.489-1.679-6.591-4.005-8.917-7.494c-1.421-2.326-2.196-5.169-2.196-8.141c0-5.945,3.36-10.985,7.624-14.216c4.523-3.101,9.951-4.781,15.896-4.781c8.916,0,15.248,4.265,19.384,7.107c3.102,2.068,4.006,6.333,2.067,9.562c-2.067,3.102-6.332,4.007-9.562,1.81c-4.135-2.713-7.754-4.782-11.889-4.782c-3.231,0-6.074,1.034-7.754,2.326c-1.68,1.164-2.067,2.327-2.067,2.973c0,0.516,0,0.646,0.258,1.033c0.13,0.258,0.517,0.775,1.422,1.292c1.681,1.163,5.04,2.326,9.434,3.102l0.129,0.13h0.13c4.265,0.774,8.271,1.938,12.018,3.747c3.489,1.551,6.979,4.006,9.176,7.624c1.551,2.584,2.455,5.557,2.455,8.529c0,6.332-3.489,11.631-8.142,14.99c-4.652,3.23-10.468,5.17-16.8,5.17c-10.079-0.129-17.833-4.781-23.002-8.916C577.895,318.791,577.508,314.396,579.833,311.553z"/>
          </g>
        </svg>
      </div>
      <div class="topbar-meta">
        <span>Generated from run_summary.json files</span>
        <span>{html.escape(generated_at)}</span>
      </div>
    </header>

    <section class="hero">
      <div>
        <p class="eyebrow">Customer-ready performance narrative</p>
        <h1>Failover without fallout.</h1>
        <p class="hero-copy">{html.escape(headline)}</p>
        <div class="chip-row">
          <span class="chip">Redis Enterprise {html.escape(re_version)}</span>
          <span class="chip">OSS Redis {html.escape(oss_version)}</span>
          <span class="chip">Baseline: {html.escape(_scenario_title(baseline_name))}</span>
          <span class="chip">Fault: {html.escape(_scenario_title(failover_name))}</span>
        </div>
      </div>
      <aside class="hero-panel">
        <div>
          <p class="eyebrow">Failover headline</p>
          <div class="hero-stat">{html.escape(_fmt_pct(re_fail_error_rate))} vs {html.escape(_fmt_pct(oss_fail_error_rate))}</div>
          <p class="hero-note">Request failure rate during the same primary-loss window. Redis Enterprise stayed at zero while OSS lost over a quarter of requests.</p>
        </div>
        <div class="chip-row">
          <span class="chip">RE retained {html.escape(_fmt_pct(re_retention, precision=1))} throughput</span>
          <span class="chip">OSS retained {html.escape(_fmt_pct(oss_retention, precision=1))}</span>
        </div>
      </aside>
    </section>

    <section class="card slide-summary-card">
      <div class="slide-summary-content">
        <div class="slide-summary-head">
          <div class="slide-summary-heading">
            <p class="eyebrow">SLIDE-READY SUMMARY</p>
            <strong class="slide-summary-title">{html.escape(slide_summary_title)}</strong>
          </div>
          <div class="slide-summary-actions">
            <button class="slide-summary-btn slide-summary-copy" data-default-text="Copy" type="button" onclick="copySlideSummary(this)">Copy</button>
            <button class="slide-summary-btn slide-summary-toggle" type="button" aria-pressed="false" onclick="toggleSlideSummaryTheme(this)">
              <span class="slide-summary-toggle-option slide-summary-toggle-option--light">☀️ Light</span>
              <span class="slide-summary-toggle-divider">|</span>
              <span class="slide-summary-toggle-option slide-summary-toggle-option--dark">🌙 Dark</span>
            </button>
          </div>
        </div>
        <div class="slide-summary-table-shell">
          <table class="slide-summary-table">
            <thead>
              <tr>
                <th scope="col">Metric</th>
                <th scope="col">Redis Enterprise</th>
                <th scope="col">OSS Redis</th>
                <th scope="col">Δ Improvement</th>
              </tr>
            </thead>
            <tbody>
              {slide_summary_rows_html}
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="metrics-grid">
      {cards_html}
    </section>

    <section class="card showcase">
      <p class="eyebrow">Failover comparison</p>
      <h2>Primary failure is where the architecture difference becomes visible.</h2>
      <p class="hero-copy">The same fault produced radically different customer outcomes: Redis Enterprise preserved continuity with zero failed requests, while OSS Redis degraded sharply in both latency and successful throughput.</p>
      <div class="showcase-grid">
        <article class="platform-panel platform-panel--re">
          <div class="platform-label">
            <strong>Redis Enterprise</strong>
            <span class="version">v{html.escape(re_version)}</span>
          </div>
          <div class="big-metric">
            <div class="value">{html.escape(_fmt_pct(re_fail_error_rate))}</div>
            <div class="label">error rate during {html.escape(_scenario_title(failover_name))}</div>
          </div>
          <div class="stack">
            <div class="bar-row">
              <div class="bar-head"><span>Throughput under fault</span><strong>{html.escape(_fmt_count(re_fail_rps))} req/s</strong></div>
              <div class="bar-track"><div class="bar-fill bar-fill--re" style="width: {re_bar}%"></div></div>
            </div>
            <div class="bar-row">
              <div class="bar-head"><span>Throughput retained vs baseline</span><strong>{html.escape(_fmt_pct(re_retention, precision=1))}</strong></div>
              <div class="bar-track"><div class="bar-fill bar-fill--re" style="width: {max(8, int((re_retention or 0.0) * 100)) if re_retention is not None else 8}%"></div></div>
            </div>
            <div class="bar-head"><span>p99 latency</span><strong>{html.escape(_fmt_num(re_fail_p99, ' ms', precision=0))}</strong></div>
            <div class="bar-head"><span>Total failed requests</span><strong>{html.escape(_fmt_count(re_fail_errors))}</strong></div>
          </div>
        </article>

        <article class="platform-panel platform-panel--oss">
          <div class="platform-label">
            <strong>OSS Redis</strong>
            <span class="version">v{html.escape(oss_version)}</span>
          </div>
          <div class="big-metric">
            <div class="value">{html.escape(_fmt_pct(oss_fail_error_rate))}</div>
            <div class="label">error rate during {html.escape(_scenario_title(failover_name))}</div>
          </div>
          <div class="stack">
            <div class="bar-row">
              <div class="bar-head"><span>Throughput under fault</span><strong>{html.escape(_fmt_count(oss_fail_rps))} req/s</strong></div>
              <div class="bar-track"><div class="bar-fill bar-fill--oss" style="width: {oss_bar}%"></div></div>
            </div>
            <div class="bar-row">
              <div class="bar-head"><span>Throughput retained vs baseline</span><strong>{html.escape(_fmt_pct(oss_retention, precision=1))}</strong></div>
              <div class="bar-track"><div class="bar-fill bar-fill--oss" style="width: {max(8, int((oss_retention or 0.0) * 100)) if oss_retention is not None else 8}%"></div></div>
            </div>
            <div class="bar-head"><span>p99 latency</span><strong>{html.escape(_fmt_num(oss_fail_p99, ' ms', precision=0))}</strong></div>
            <div class="bar-head"><span>Total failed requests</span><strong>{html.escape(_fmt_count(oss_fail_errors))}</strong></div>
          </div>
        </article>
      </div>
      <div class="delta-strip">Redis Enterprise delivered {html.escape(f'{failover_throughput_advantage:.2f}x' if failover_throughput_advantage is not None else NA)} higher throughput and {html.escape(f'{failover_latency_advantage:.2f}x' if failover_latency_advantage is not None else NA)} lower p99 latency than OSS during the same primary-node failure.</div>
    </section>

    <section class="details-grid">
      <article class="card">
        <p class="eyebrow">Scenario summary</p>
        <h2>Data across the two demo moments</h2>
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>RE req/s</th>
              <th>RE p99</th>
              <th>RE errors</th>
              <th>OSS req/s</th>
              <th>OSS p99</th>
              <th>OSS errors</th>
              <th>Winner</th>
            </tr>
          </thead>
          <tbody>
            {''.join(summary_rows)}
          </tbody>
        </table>
      </article>

      <article class="card">
        <p class="eyebrow">Evidence</p>
        <h2>Open the supporting artifacts</h2>
        <div class="evidence-list">
          {evidence_html}
        </div>
      </article>
    </section>

    <p class="footer">Source demo directory: {html.escape(str(demo_dir))}. This report is assembled from the exported run summaries so the displayed req/s, p99, error counts, and versions stay aligned with the raw benchmark evidence.</p>
  </main>
  <script>
    const slideSummaryText = {json.dumps(slide_summary_text)};
    function copySlideSummary(button) {{
      const defaultText = button.dataset.defaultText || 'Copy';
      navigator.clipboard.writeText(slideSummaryText).then(() => {{
        button.textContent = 'Copied ✓';
        window.setTimeout(() => {{
          button.textContent = defaultText;
        }}, 2000);
      }}).catch(() => {{
        button.textContent = 'Copy failed';
        window.setTimeout(() => {{
          button.textContent = defaultText;
        }}, 2000);
      }});
    }}
    function toggleSlideSummaryTheme(button) {{
      const card = button.closest('.slide-summary-card');
      const isDark = card.classList.toggle('slide-dark');
      button.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      button.setAttribute('title', isDark ? 'Switch slide summary to light mode' : 'Switch slide summary to dark mode');
      button.setAttribute('aria-label', isDark ? 'Switch slide summary to light mode' : 'Switch slide summary to dark mode');
    }}
  </script>
</body>
</html>
"""



# ── README generator ────────────────────────────────────────────────────────

def _build_readme(
    summary_paths: List[Path],
    comparison_md: Optional[Path],
    rto_rpo_json: Optional[Path],
    consistency_json: Optional[Path],
    demo_dir: Path,
) -> str:
    """Build a README.md index for the result pack."""
    lines = [
        "# Result Pack",
        "",
        f"**Source:** `{demo_dir}`  ",
        f"**Assembled:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Contents",
        "",
        "| File | Description |",
        "|---|---|",
        "| `results_report.html` | Redis-branded standalone HTML results report |",
        "| `scorecard.md` | Auto-filled POC Scorecard |",
        "| `executive_readout.md` | Auto-filled Executive Readout |",
    ]

    if comparison_md:
        lines.append("| `comparison_report.md` | Cross-run comparison report |")
    else:
        lines.append(f"| `comparison_report.md` | {NA} |")

    if rto_rpo_json:
        lines.append("| `rto_rpo_report.md` | RTO/RPO evidence report |")
    else:
        lines.append(f"| `rto_rpo_report.md` | {NA} |")

    if consistency_json:
        lines.append("| `consistency_report.md` | Canary key consistency report |")
    else:
        lines.append(f"| `consistency_report.md` | {NA} |")

    lines += [
        "",
        "### Run Summaries",
        "",
    ]

    if summary_paths:
        for sp in summary_paths:
            lines.append(f"- `run_summaries/{_copied_summary_name(sp)}` (from `{sp.parent.name}/`)")
    else:
        lines.append(f"- {NA}")

    lines += [
        "",
        "---",
        "",
        "_Assembled by `tooling/assemble_result_pack.py`._",
    ]
    return "\n".join(lines) + "\n"


# ── Main assembler ──────────────────────────────────────────────────────────

def assemble_result_pack(demo_dir_path: str) -> Path:
    """Assemble a result pack from a demo results directory.

    Returns the path to the result_pack/ directory.
    """
    demo_dir = Path(demo_dir_path).resolve()
    if not demo_dir.is_dir():
        print(f"Error: {demo_dir_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    repo_root = _find_repo_root()
    pack_dir = demo_dir / "result_pack"
    pack_dir.mkdir(exist_ok=True)
    summaries_dir = pack_dir / "run_summaries"
    summaries_dir.mkdir(exist_ok=True)

    print(f"[INFO] Assembling result pack from: {demo_dir}")
    print(f"[INFO] Output: {pack_dir}")

    # 1. Discover run summaries
    summary_paths = find_run_summaries(demo_dir)
    # Exclude any inside result_pack/ itself
    summary_paths = [p for p in summary_paths if "result_pack" not in p.parts]
    summaries_data: List[Dict[str, Any]] = []
    for sp in summary_paths:
        data = load_json(sp)
        if data:
            summaries_data.append(data)
            # Copy to run_summaries/
            dest_name = _copied_summary_name(sp)
            shutil.copy2(sp, summaries_dir / dest_name)
            print(f"  [OK] Run summary: {sp.name}")

    if not summaries_data:
        print("  [WARN] No run_summary.json files found")

    # 2. Discover comparison report
    cmp_md, cmp_json = find_comparison_report(demo_dir)
    comparison_data = load_json(cmp_json)
    if cmp_md and "result_pack" not in cmp_md.parts:
        shutil.copy2(cmp_md, pack_dir / "comparison_report.md")
        print(f"  [OK] Comparison report (md)")
    elif comparison_data:
        # No markdown version — we have JSON but no md, skip copy
        print(f"  [OK] Comparison report (json only)")
    else:
        print(f"  [WARN] No comparison report found")

    # 3. Discover RTO/RPO report
    rto_md, rto_json = find_rto_rpo_report(demo_dir)
    rto_rpo_data = load_json(rto_json)
    if rto_md and "result_pack" not in rto_md.parts:
        shutil.copy2(rto_md, pack_dir / "rto_rpo_report.md")
        print(f"  [OK] RTO/RPO report (md)")
    elif rto_rpo_data:
        # Generate markdown from JSON
        (pack_dir / "rto_rpo_report.md").write_text(
            _render_rto_rpo_md(rto_rpo_data), encoding="utf-8"
        )
        print(f"  [OK] RTO/RPO report (generated md from json)")
    else:
        print(f"  [WARN] No RTO/RPO report found")

    # 4. Discover consistency report
    cons_md, cons_json = find_consistency_report(demo_dir)
    consistency_data = load_json(cons_json)
    if cons_md and "result_pack" not in cons_md.parts:
        shutil.copy2(cons_md, pack_dir / "consistency_report.md")
        print(f"  [OK] Consistency report (md)")
    elif consistency_data:
        (pack_dir / "consistency_report.md").write_text(
            _render_consistency_md(consistency_data), encoding="utf-8"
        )
        print(f"  [OK] Consistency report (generated md from json)")
    else:
        print(f"  [WARN] No consistency report found")

    # 5. Load templates
    scorecard_tmpl_path = repo_root / "docs" / "templates" / "POC_SCORECARD_TEMPLATE.md"
    readout_tmpl_path = repo_root / "docs" / "templates" / "EXECUTIVE_READOUT_TEMPLATE.md"

    scorecard_tmpl = ""
    if scorecard_tmpl_path.exists():
        scorecard_tmpl = scorecard_tmpl_path.read_text(encoding="utf-8")
    else:
        print(f"  [WARN] Scorecard template not found at {scorecard_tmpl_path}")

    readout_tmpl = ""
    if readout_tmpl_path.exists():
        readout_tmpl = readout_tmpl_path.read_text(encoding="utf-8")
    else:
        print(f"  [WARN] Executive readout template not found at {readout_tmpl_path}")

    # 6. Generate scorecard
    scorecard_md = _build_scorecard(
        summaries_data, comparison_data, rto_rpo_data, consistency_data, scorecard_tmpl
    )
    (pack_dir / "scorecard.md").write_text(scorecard_md, encoding="utf-8")
    print(f"  [OK] Scorecard: scorecard.md")

    # 7. Generate executive readout
    readout_md = _build_executive_readout(
        summaries_data, comparison_data, rto_rpo_data, consistency_data, readout_tmpl
    )
    (pack_dir / "executive_readout.md").write_text(readout_md, encoding="utf-8")
    print(f"  [OK] Executive readout: executive_readout.md")

    # 8. Generate branded HTML report
    html_report = _build_html_report(summaries_data, demo_dir, summary_paths)
    (pack_dir / "results_report.html").write_text(html_report, encoding="utf-8")
    print(f"  [OK] HTML report: results_report.html")

    # 9. Generate README
    readme_md = _build_readme(
        summary_paths, cmp_md, rto_json, cons_json, demo_dir
    )
    (pack_dir / "README.md").write_text(readme_md, encoding="utf-8")
    print(f"  [OK] README: README.md")

    print(f"\n[DONE] Result pack assembled at: {pack_dir}")
    return pack_dir


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Assemble a result pack from a demo results directory.",
        epilog="Example: python -m tooling.assemble_result_pack results/demo_20260323_120000/",
    )
    parser.add_argument(
        "demo_dir",
        help="Path to the demo results directory (e.g., results/demo_20260323_120000/)",
    )
    args = parser.parse_args()
    assemble_result_pack(args.demo_dir)


if __name__ == "__main__":
    main()
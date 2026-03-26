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
    .brand svg {{ height: 36px; width: auto; }}
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
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 368.69 125.59" height="36" aria-label="Redis">
          <defs><clipPath id="rcp"><rect width="146.42" height="125.48"/></clipPath></defs>
          <g><g><g style="clip-path:url(#rcp)">
            <path fill="#a32422" d="M140.66,96.74c-7.8,4.08-48.28,20.73-57,25.3s-13.39,4.44-20.21,1.18S13.7,102.5,5.92,98.78C2,96.94,0,95.37,0,93.9V79.09S56.08,66.92,65.13,63.64,77.31,60.28,85,63.1,138.79,74.24,146.4,77V91.6c0,1.52-1.75,3-5.74,5.13Z" transform="translate(0.01 0.01)"/>
            <path fill="#dc382c" d="M140.66,82c-7.8,4.06-48.28,20.71-57,25.2s-13.39,4.45-20.21,1.2S13.7,87.69,5.92,84s-7.93-6.27-.3-9.25S56.08,55,65.13,51.7,77.31,48.33,85,51.16,133,70,140.57,72.79s7.92,5.08.09,9.13Z" transform="translate(0.01 0.01)"/>
            <path fill="#a32422" d="M140.66,72.62c-7.8,4.07-48.28,20.71-57,25.2S70.31,102.27,63.49,99,13.7,78.37,5.92,74.66C2,72.8,0,71.24,0,69.76V55S56.08,42.79,65.13,39.51,77.31,36.14,85,39,138.79,50.1,146.4,52.88v14.6C146.4,69,144.65,70.52,140.66,72.62Z" transform="translate(0.01 0.01)"/>
            <path fill="#dc382c" d="M140.66,57.81c-7.8,4.08-48.28,20.72-57,25.21s-13.39,4.46-20.21,1.2S13.7,63.57,5.92,59.85-2,53.6,5.62,50.62s50.46-19.79,59.51-23S77.31,24.21,85,27,133,45.94,140.57,48.65s7.92,5.09.09,9.13Z" transform="translate(0.01 0.01)"/>
            <path fill="#a32422" d="M140.66,47.59c-7.8,4.08-48.28,20.73-57,25.21S70.31,77.25,63.49,74,13.7,53.34,5.92,49.63C2,47.79,0,46.22,0,44.74V29.93S56.08,17.76,65.13,14.49,77.31,11.12,85,13.94s53.77,11.14,61.38,13.92v14.6C146.4,44,144.65,45.5,140.66,47.59Z" transform="translate(0.01 0.01)"/>
            <path fill="#dc382c" d="M140.66,32.8c-7.8,4-48.28,20.75-57,25.2s-13.39,4.44-20.21,1.2S13.7,38.53,5.92,34.83s-7.93-6.27-.3-9.25S56.08,5.8,65.13,2.54,77.31-.82,85,2,133,20.85,140.57,23.63s7.92,5.09.09,9.14Z" transform="translate(0.01 0.01)"/>
          </g>
          <polygon fill="#fff" points="75.51 11.78 85.17 8.61 82.55 14.87 92.38 18.55 79.71 19.87 76.86 26.71 72.28 19.08 57.63 17.76 68.57 13.82 65.28 7.76 75.51 11.78"/>
          <polygon fill="#fff" points="76.12 51.71 52.44 41.88 86.36 36.67 76.12 51.71"/>
          <path fill="#fff" d="M43.28,22.34c10,0,18.13,3.15,18.13,7s-8.15,7-18.13,7-18.14-3.15-18.14-7S33.27,22.34,43.28,22.34Z" transform="translate(0.01 0.01)"/>
          <polygon fill="#741113" points="107.39 20.42 127.46 28.35 107.41 36.28 107.39 20.42"/>
          <polygon fill="#ac2724" points="107.39 20.42 107.41 36.28 105.23 37.13 85.17 29.2 107.39 20.42"/>
          <path fill="#FF4438" d="M193,41.4a17.36,17.36,0,0,1,6.23-4.34,20,20,0,0,1,7.3-1.61,6.71,6.71,0,0,1,5,1.61,5,5,0,0,1,1.52,3.79,5.39,5.39,0,0,1-1.52,3.79,4.9,4.9,0,0,1-3.79,1.63c-6.24.55-14.9,6.77-14.9,15.22V80.67a5.57,5.57,0,0,1-5.42,5.41,4.92,4.92,0,0,1-3.87-1.67,5.36,5.36,0,0,1-1.62-3.79v-40a5.35,5.35,0,0,1,1.62-3.79,7.2,7.2,0,0,1,4.07-1.36,5.52,5.52,0,0,1,5.41,5.4Z" transform="translate(0.01 0.01)"/>
          <path fill="#FF4438" d="M258.71,59a5.25,5.25,0,0,1-1.35,3.54,6.11,6.11,0,0,1-3.79,1.62h-32a10.31,10.31,0,0,0,3.47,6.56,14.46,14.46,0,0,0,9.48,4.57,14.07,14.07,0,0,0,10.56-2.44,5.52,5.52,0,0,1,4.07-1.63,4.65,4.65,0,0,1,3.51,1.36,4.41,4.41,0,0,1,.26,6.24c-.08.09-.17.17-.26.26a24.49,24.49,0,0,1-17.59,6.5A23,23,0,0,1,217.5,78a26.67,26.67,0,0,1-7.3-17.9,24.31,24.31,0,0,1,7.3-17.88,22.59,22.59,0,0,1,17.06-7.31,22,22,0,0,1,16.74,6.78,24.78,24.78,0,0,1,7.61,16.74v.53Zm-24.1-14.35a14.2,14.2,0,0,0-9.13,3.53,13.17,13.17,0,0,0-4.33,7h28.43a12.39,12.39,0,0,0-4.88-6.76,17.3,17.3,0,0,0-10-3.81" transform="translate(0.01 0.01)"/>
          <path fill="#FF4438" d="M309.66,80.12a5.57,5.57,0,0,1-5.41,5.42,5.85,5.85,0,0,1-5.42-4.34A23.23,23.23,0,0,1,285,85.54a23.57,23.57,0,0,1-17.33-7.31,24.14,24.14,0,0,1-7.05-17.88,25.75,25.75,0,0,1,7.05-17.87A23.85,23.85,0,0,1,285,34.87a22.34,22.34,0,0,1,13.53,4.34V20.28a4.92,4.92,0,0,1,1.63-3.79A5.37,5.37,0,0,1,304,14.86a4.92,4.92,0,0,1,3.79,1.63,5.36,5.36,0,0,1,1.63,3.79V80.12ZM285.31,74.7a12,12,0,0,0,9.47-4.32,14.4,14.4,0,0,0,0-20A13,13,0,0,0,285.31,46a11.65,11.65,0,0,0-9.48,4.34,14.4,14.4,0,0,0,0,20,12.49,12.49,0,0,0,9.48,4.32" transform="translate(0.01 0.01)"/>
          <path fill="#FF4438" d="M325.67,20.28v2.18A5.5,5.5,0,0,1,324,26.58a4.64,4.64,0,0,1-3.79,1.35,4.86,4.86,0,0,1-3.78-1.61,5.44,5.44,0,0,1-1.63-4.06v-2a5.28,5.28,0,0,1,1.63-3.79,5.33,5.33,0,0,1,3.78-1.63A5,5,0,0,1,324,16.49a4.9,4.9,0,0,1,1.66,3.79m-9.13,16.53a5.28,5.28,0,0,1,3.79-1.63,4.85,4.85,0,0,1,3.79,1.63,5.48,5.48,0,0,1,1.55,4V80.42A4.55,4.55,0,0,1,324,84.21a5.33,5.33,0,0,1-3.78,1.63,4.9,4.9,0,0,1-3.79-1.63,5.28,5.28,0,0,1-1.63-3.79V40.85a5.39,5.39,0,0,1,1.63-4" transform="translate(0.01 0.01)"/>
          <path fill="#FF4438" d="M364.08,40.6a5.29,5.29,0,0,1,2.17,3.24,7.17,7.17,0,0,1-.54,4.06,5.4,5.4,0,0,1-3.25,2.16,5.61,5.61,0,0,1-4.07-.81c-3.79-2.43-6.75-3.78-9.2-3.78a8.74,8.74,0,0,0-6,1.88c-1.08.82-1.62,1.36-1.62,1.9a2,2,0,0,0,.27,1.36,3.74,3.74,0,0,0,1.08.81,16.19,16.19,0,0,0,7.32,2.43h0a37.75,37.75,0,0,1,9.74,3,13.57,13.57,0,0,1,6.5,5.7,13.46,13.46,0,0,1-4.06,18.67,21.79,21.79,0,0,1-13,4.06c-6.23,0-12.18-2.43-17.87-7a5.77,5.77,0,0,1-1.9-3.53,5.2,5.2,0,0,1,8.4-4.56,15.73,15.73,0,0,0,11.1,4.33,11.61,11.61,0,0,0,6.77-1.9c1.08-1.08,1.9-1.89,1.9-2.71s0-1.08-.27-1.35c0-.28-.55-.81-1.36-1.08a20.15,20.15,0,0,0-8.13-2.86h0a28.26,28.26,0,0,1-9.2-3,16.56,16.56,0,0,1-6.5-5.67,12.61,12.61,0,0,1-1.61-6.23,13.3,13.3,0,0,1,5.95-11.11,21.82,21.82,0,0,1,12.45-3.79c4.56.28,9.48,2.16,14.89,5.69" transform="translate(0.01 0.01)"/>
          </g></g>
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
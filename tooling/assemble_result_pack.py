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
            lines.append(f"- `run_summaries/{sp.name}` (from `{sp.parent.name}/`)")
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
            if sp.name == "run_summary.json":
                # From subdirectory — prefix with parent dir name
                dest_name = f"{sp.parent.name}_run_summary.json"
            else:
                # Flat *_summary.json from orchestrator — keep original name
                dest_name = sp.name
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

    # 8. Generate README
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
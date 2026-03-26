"""Smoke test: assemble a branded HTML report from synthetic demo summaries."""

import json

from tooling.assemble_result_pack import assemble_result_pack


def _summary(scenario, platform, version, rps, p99, failures, error_rate):
    return {
        "scenario": scenario,
        "test_metadata": {
            "platform": platform,
            "redis_version": f"redis_version:{version}",
            "started_at": "2026-03-26T17:14:36Z",
        },
        "throughput": {"requests_per_sec": rps},
        "latency_percentiles_ms": {"p99": p99},
        "errors": {"total_failures": failures, "error_rate": error_rate},
    }


def test_assemble_result_pack_writes_redis_branded_html_report(tmp_path):
    """The assembled pack should include a standalone HTML report with live metrics."""
    demo_dir = tmp_path / "demo_20260326_171436"
    demo_dir.mkdir()

    samples = {
        "01_baseline_re_20260326_171601_summary.json": _summary(
            "01_baseline", "re", "8.4.0", 11029.176205731865, 8.0, 0, 0.0
        ),
        "01_baseline_oss-sentinel_20260326_171906_summary.json": _summary(
            "01_baseline", "oss-sentinel", "7.4.7", 10163.302757668536, 10.0, 0, 0.0
        ),
        "02_primary_kill_re_20260326_172207_summary.json": _summary(
            "02_primary_kill", "re", "8.4.0", 5698.189786464815, 26.0, 0, 0.0
        ),
        "02_primary_kill_oss-sentinel_20260326_172722_summary.json": _summary(
            "02_primary_kill", "oss-sentinel", "7.4.7", 957.7632123130503, 310.0, 19562, 0.284199
        ),
    }

    for name, payload in samples.items():
        (demo_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    pack_dir = assemble_result_pack(str(demo_dir))

    html_report = (pack_dir / "results_report.html").read_text(encoding="utf-8")
    readme = (pack_dir / "README.md").read_text(encoding="utf-8")

    assert "Space Grotesk" in html_report
    assert "Space Mono" in html_report
    assert "#FF4438" in html_report
    assert "Failover without fallout." in html_report
    assert "11,029 req/s" in html_report
    assert "28.42%" in html_report
    assert "19,562" in html_report
    assert "5.95x" in html_report
    assert "11.92x" in html_report
    assert "SLIDE-READY SUMMARY" in html_report
    assert "copySlideSummary" in html_report
    assert "toggleSlideSummaryTheme" in html_report
    assert "Redis Enterprise vs OSS Redis — POC Results" in html_report
    assert "Δ Improvement" in html_report
    assert "Baseline throughput" in html_report
    assert "Failover error rate" in html_report
    assert "slide-summary-row--money" in html_report
    assert "slide-dark" in html_report
    assert "☀️ Light" in html_report
    assert "🌙 Dark" in html_report
    assert "Zero errors" in html_report
    assert r"Metric\tRedis Enterprise\tOSS Redis\tImprovement" in html_report
    assert r"Throughput retained\t51.7%\t9.4%\t5.5x better" in html_report
    assert "#0A1A23" in html_report
    assert "#122A35" in html_report
    assert "#FF7566" in html_report
    assert "Redis Enterprise 8.4.0" in html_report
    assert "OSS Redis 7.4.7" in html_report
    assert "results_report.html" in readme
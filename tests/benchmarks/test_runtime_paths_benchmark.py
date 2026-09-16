"""The runtime-paths benchmark must emit the record the budget gate reads."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "runtime_paths.py"
BUDGETS = ROOT / "docs" / "performance" / "budgets.json"

SCENARIOS = {
    "direct_async_handler",
    "compiled_invoke",
    "dependency_injection_one",
    "dependency_injection_ten",
    "policy_evaluation_one",
    "policy_evaluation_three",
    "execution_identity",
    "idempotency_miss",
    "idempotency_hit",
    "nested_depth_one",
    "nested_depth_three",
    "streaming_unit",
}


def _record() -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--iterations",
            "2",
            "--samples",
            "2",
            "--warmups",
            "1",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_benchmark_emits_reproducible_json_contract() -> None:
    record = _record()

    assert set(record) == {
        "schema_version",
        "benchmark",
        "recorded_at_utc",
        "git",
        "environment",
        "config",
        "results",
        "median_ratio_to_reference",
        "median_ratio_to_compiled_invoke",
        "startup",
        "startup_scaling_ratio",
    }
    assert record["schema_version"] == 1
    assert record["benchmark"] == "agnara.runtime.paths"
    assert set(record["results"]) == SCENARIOS
    assert set(record["median_ratio_to_reference"]) == SCENARIOS - {"direct_async_handler"}
    assert set(record["median_ratio_to_compiled_invoke"]) == SCENARIOS - {
        "direct_async_handler",
        "compiled_invoke",
    }
    assert record["config"]["reference_scenario"] == "direct_async_handler"
    assert record["config"]["garbage_collector_disabled_during_samples"] is True


def test_every_result_retains_its_raw_samples() -> None:
    """Summaries alone cannot be re-analysed; the raw measurements must survive."""
    record = _record()
    for name, result in record["results"].items():
        assert len(result["elapsed_ns"]) == 2, name
        assert len(result["ns_per_operation"]) == 2, name
        assert set(result["summary_ns_per_operation"]) == {
            "minimum",
            "median",
            "mean",
            "maximum",
            "stdev",
        }
        assert result["summary_ns_per_operation"]["median"] > 0, name


def test_streaming_is_reported_per_emitted_unit() -> None:
    """A per-stream number would not be comparable with per-invocation paths."""
    record = _record()
    units = record["config"]["stream_units_per_iteration"]
    assert units > 1
    assert record["results"]["streaming_unit"]["operations_per_iteration"] == units
    assert record["results"]["compiled_invoke"]["operations_per_iteration"] == 1


def test_startup_reports_time_and_memory_for_each_size() -> None:
    record = _record()
    startup = record["startup"]
    assert set(startup) == {"100", "1000"}
    for size, entry in startup.items():
        assert entry["capabilities"] == int(size)
        assert entry["median_ns_per_capability"] > 0
        assert entry["peak_bytes_per_capability"] > 0
    assert record["startup_scaling_ratio"] > 0


def test_every_budgeted_metric_is_present_in_the_record() -> None:
    """The gate reads these names; a rename here must not silently skip a budget."""
    record = _record()
    metrics = json.loads(BUDGETS.read_text(encoding="utf-8"))["benchmarks"]["agnara.runtime.paths"][
        "metrics"
    ]

    for metric, specification in metrics.items():
        if metric == "startup_peak_bytes_per_capability":
            assert all("peak_bytes_per_capability" in entry for entry in record["startup"].values())
            continue
        if metric == "startup_scaling_ratio":
            assert metric in record
            continue
        for scenario in specification:
            assert scenario in record[metric], f"{metric}.{scenario} missing from the record"


def test_benchmark_rejects_non_positive_sampling_controls() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--samples", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "must be at least 1" in completed.stderr

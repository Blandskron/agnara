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
    "embedded_runtime_invoke",
    "stream_open",
    "stream_per_item",
    "stream_completion",
    "streaming_unit",
}

RATIO_TO_COMPILED_INVOKE = {
    "dependency_injection_one",
    "dependency_injection_ten",
    "policy_evaluation_one",
    "policy_evaluation_three",
    "execution_identity",
    "idempotency_miss",
    "idempotency_hit",
    "nested_depth_one",
    "nested_depth_three",
    "embedded_runtime_invoke",
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
        "execution_dimensions",
        "config",
        "results",
        "median_ratio_to_reference",
        "median_ratio_to_compiled_invoke",
        "startup",
        "startup_scaling_ratio",
        "registration",
        "registration_scaling_ratio",
    }
    assert record["schema_version"] == 2
    assert record["benchmark"] == "agnara.runtime.paths"
    assert set(record["results"]) == SCENARIOS
    assert set(record["median_ratio_to_reference"]) == RATIO_TO_COMPILED_INVOKE | {
        "compiled_invoke"
    }
    assert set(record["median_ratio_to_compiled_invoke"]) == RATIO_TO_COMPILED_INVOKE
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
        assert isinstance(result["measurement_scope"], str)
        assert isinstance(result["ratio_to_compiled_invoke"], bool)


def test_streaming_is_reported_per_emitted_unit() -> None:
    """A per-stream number would not be comparable with per-invocation paths."""
    record = _record()
    units = record["config"]["stream_units_per_iteration"]
    assert units > 1
    assert record["results"]["streaming_unit"]["operations_per_iteration"] == units
    assert record["results"]["compiled_invoke"]["operations_per_iteration"] == 1


def test_streaming_phases_are_measured_without_no_op_shortcuts() -> None:
    record = _record()
    results = record["results"]
    assert results["stream_open"]["measurement_scope"] == "stream pre-output opening only"
    assert results["stream_per_item"]["measurement_scope"] == (
        "one consumer pull from an already-open stream"
    )
    assert results["stream_completion"]["measurement_scope"] == (
        "normal terminal pull from an already-drained stream"
    )
    for name in ("stream_open", "stream_per_item", "stream_completion"):
        assert results[name]["ratio_to_compiled_invoke"] is False


def test_startup_reports_time_and_memory_for_each_size() -> None:
    record = _record()
    startup = record["startup"]
    assert set(startup) == {"100", "1000"}
    for size, entry in startup.items():
        assert entry["capabilities"] == int(size)
        assert entry["median_ns_per_capability"] > 0
        assert entry["peak_bytes_per_capability"] > 0
    assert record["startup_scaling_ratio"] > 0
    registration = record["registration"]
    assert set(registration) == {"100", "1000"}
    assert record["registration_scaling_ratio"] > 0
    for size, entry in registration.items():
        assert entry["capabilities"] == int(size)
        assert entry["median_ns_per_capability"] > 0


def test_record_declares_the_execution_dimensions_needed_to_reproduce_it() -> None:
    dimensions = _record()["execution_dimensions"]
    assert dimensions == {
        "server": "none (in-process core runtime)",
        "serializer": "standard-library JSON only for idempotency result codec",
        "payload": "one integer field (value=41)",
        "concurrency": 1,
        "handler_modes": ["async"],
        "schema_sizes": ["one scalar input", "no output schema"],
        "command": "benchmarks/runtime_paths.py --json",
    }


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

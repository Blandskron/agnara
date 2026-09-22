"""The performance regression gate must fail on a regression and pass without one.

A gate nobody has seen fail is not evidence. These tests pin both directions
using small synthetic records, so they stay deterministic and fast: the real
benchmark is far too slow and too machine-dependent to run inside the unit
suite, and a gate whose test depended on a quiet machine would be exactly the
noise-driven failure the ratio design exists to avoid.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_performance_budgets.py"
BUDGETS = ROOT / "docs" / "performance" / "budgets.json"
BENCHMARK = "agnara.runtime.paths"


def _budgets() -> dict[str, Any]:
    return json.loads(BUDGETS.read_text(encoding="utf-8"))


def _metrics() -> dict[str, Any]:
    return _budgets()["benchmarks"][BENCHMARK]["metrics"]


def _record_at_budget(scale: float) -> dict[str, Any]:
    """Build a record whose every metric sits at ``scale`` times its budget."""
    metrics = _metrics()
    record: dict[str, Any] = {"benchmark": BENCHMARK, "startup": {}}
    for metric, specification in metrics.items():
        if metric == "startup_peak_bytes_per_capability":
            record["startup"]["100"] = {
                "peak_bytes_per_capability": specification["maximum"] * scale
            }
        elif metric in {"registration_scaling_ratio", "startup_scaling_ratio"}:
            record[metric] = specification["maximum"] * scale
        else:
            record[metric] = {
                scenario: entry["maximum"] * scale for scenario, entry in specification.items()
            }
    return record


def _run(record: dict[str, Any], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--record", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_passes_when_every_metric_is_within_budget(tmp_path: Path) -> None:
    completed = _run(_record_at_budget(0.5), tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert "performance budgets satisfied" in completed.stdout


def test_gate_accepts_a_value_exactly_at_its_budget(tmp_path: Path) -> None:
    # The budget is a ceiling, not an exclusive bound: a run that lands exactly
    # on it is not a regression.
    completed = _run(_record_at_budget(1.0), tmp_path)
    assert completed.returncode == 0, completed.stderr


def test_gate_fails_and_names_every_breached_metric(tmp_path: Path) -> None:
    completed = _run(_record_at_budget(1.5), tmp_path)

    assert completed.returncode == 1
    assert "performance budget exceeded" in completed.stderr
    for metric, specification in _metrics().items():
        if metric in {"registration_scaling_ratio", "startup_scaling_ratio", "startup_peak_bytes_per_capability"}:
            assert metric in completed.stderr
            continue
        for scenario in specification:
            assert f"{metric}.{scenario}" in completed.stderr


def test_gate_refuses_to_suggest_widening_the_budget(tmp_path: Path) -> None:
    """The failure message must not read as an invitation to edit the limit."""
    completed = _run(_record_at_budget(1.5), tmp_path)
    assert "do not widen it to make this run pass" in completed.stderr


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("idempotency_miss", "median_ratio_to_compiled_invoke.idempotency_miss"),
        ("nested_depth_three", "median_ratio_to_compiled_invoke.nested_depth_three"),
    ],
)
def test_gate_isolates_a_single_regressed_path(
    scenario: str, expected: str, tmp_path: Path
) -> None:
    """One slow path must be reported without dragging the others in.

    `idempotency_miss` is the metric that actually caught the quadratic
    in-memory store sweep, so it is pinned by name here.
    """
    record = _record_at_budget(0.5)
    budget = _metrics()["median_ratio_to_compiled_invoke"][scenario]["maximum"]
    record["median_ratio_to_compiled_invoke"][scenario] = budget * 2

    completed = _run(record, tmp_path)

    assert completed.returncode == 1
    assert expected in completed.stderr
    assert completed.stderr.count("measured") == 1


def test_gate_rejects_a_record_for_a_different_benchmark(tmp_path: Path) -> None:
    record = _record_at_budget(0.5)
    record["benchmark"] = "agnara.runtime.invocation"
    completed = _run(record, tmp_path)
    assert completed.returncode != 0
    assert "no record supplied" in completed.stderr or "reports benchmark" in completed.stderr


def test_gate_rejects_a_record_missing_a_budgeted_metric(tmp_path: Path) -> None:
    """A silently absent measurement must not read as a pass."""
    record = _record_at_budget(0.5)
    del record["median_ratio_to_compiled_invoke"]["nested_depth_three"]
    completed = _run(record, tmp_path)
    assert completed.returncode != 0
    assert "nested_depth_three" in completed.stderr


def test_gate_rejects_an_unknown_budget_metric(tmp_path: Path) -> None:
    budgets = _budgets()
    budgets["benchmarks"][BENCHMARK]["metrics"]["made_up_metric"] = {"maximum": 1.0}
    path = tmp_path / "budgets.json"
    path.write_text(json.dumps(budgets), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--budgets", str(path), "--record", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "unknown metrics: made_up_metric" in completed.stderr


def test_gate_rejects_an_unknown_budget_schema_version(tmp_path: Path) -> None:
    budgets = _budgets()
    budgets["schema_version"] = 999
    path = tmp_path / "budgets.json"
    path.write_text(json.dumps(budgets), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--budgets", str(path), "--record", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "unsupported budget schema version" in completed.stderr


def test_every_budget_records_the_value_it_was_calibrated_against() -> None:
    """A limit with no observed measurement behind it is a guess."""
    for metric, specification in _metrics().items():
        if metric in {"registration_scaling_ratio", "startup_scaling_ratio", "startup_peak_bytes_per_capability"}:
            entries = {metric: specification}
        else:
            entries = specification
        for name, entry in entries.items():
            assert "observed_maximum" in entry, f"{name} has no calibration evidence"
            assert entry["maximum"] > entry["observed_maximum"], (
                f"{name} budget {entry['maximum']} leaves no headroom over "
                f"observed {entry['observed_maximum']}"
            )
            assert entry.get("note"), f"{name} does not say what it protects"

"""Enforce the performance budgets in `docs/performance/budgets.json`.

This is the regression gate. It reads one budget file, obtains a benchmark
record for each benchmark named there -- either by running the benchmark or
from a previously emitted record -- and fails when a measured value exceeds its
limit.

Budgets are ratios between two scenarios measured in the same process and run,
not absolute nanoseconds, so a slow or busy runner does not by itself fail the
gate. See the `methodology` block in the budget file.

The script never edits the budget file. A limit that needs to move is a
reviewed decision with rationale, not something a failing run rewrites.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGETS = ROOT / "docs" / "performance" / "budgets.json"
BUDGET_SCHEMA_VERSION = 2

#: Metrics whose value is a bare number rather than a mapping of scenario names.
SCALAR_METRICS = frozenset(
    {"registration_scaling_ratio", "startup_scaling_ratio", "startup_peak_bytes_per_capability"}
)
SUPPORTED_METRICS = frozenset(
    {
        "median_ratio_to_compiled_invoke",
        "median_ratio_to_reference",
        "registration_scaling_ratio",
        "startup_scaling_ratio",
        "startup_peak_bytes_per_capability",
    }
)


@dataclass(frozen=True, slots=True)
class Breach:
    """One measured value that exceeded its budget."""

    benchmark: str
    metric: str
    scenario: str
    measured: float
    maximum: float

    @property
    def overage(self) -> float:
        return self.measured / self.maximum

    def __str__(self) -> str:
        where = self.metric if self.scenario == "" else f"{self.metric}.{self.scenario}"
        return (
            f"{self.benchmark}: {where} measured {self.measured:,.3f}, "
            f"budget {self.maximum:,.3f} ({self.overage:.2f}x over)"
        )


def _load(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"budget file not found: {path}") from None
    except json.JSONDecodeError as error:
        raise SystemExit(f"{path} is not valid JSON: {error}") from None
    if not isinstance(loaded, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return loaded


def _validate_budget_schema(budgets: dict[str, object]) -> None:
    """Reject an unreviewed budget format or metric before it reaches CI."""
    if budgets.get("schema_version") != BUDGET_SCHEMA_VERSION:
        raise SystemExit(
            f"unsupported budget schema version {budgets.get('schema_version')!r}; "
            f"expected {BUDGET_SCHEMA_VERSION}"
        )
    benchmarks = budgets.get("benchmarks")
    if not isinstance(benchmarks, dict) or not benchmarks:
        raise SystemExit("budget file declares no benchmarks")
    for name, specification in benchmarks.items():
        if not isinstance(specification, dict):
            raise SystemExit(f"budget for {name} must be an object")
        metrics = specification.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            raise SystemExit(f"budget for {name} declares no metrics")
        unknown = sorted(set(metrics) - SUPPORTED_METRICS)
        if unknown:
            raise SystemExit(f"budget for {name} declares unknown metrics: {', '.join(unknown)}")


def _run_benchmark(command: Sequence[str]) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"benchmark {' '.join(command)} failed:\n{completed.stderr}")
    try:
        record = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(f"benchmark {' '.join(command)} did not emit JSON: {error}") from None
    if not isinstance(record, dict):
        raise SystemExit(f"benchmark {' '.join(command)} did not emit a JSON object")
    return record


def _startup_peak(record: dict[str, object]) -> float:
    """Return the highest peak bytes per capability across the startup sizes."""
    startup = record.get("startup")
    if not isinstance(startup, dict) or not startup:
        raise SystemExit("benchmark record has no startup measurements")
    peaks = []
    for entry in startup.values():
        if not isinstance(entry, dict):
            raise SystemExit("benchmark record has a malformed startup entry")
        peaks.append(float(entry["peak_bytes_per_capability"]))
    return max(peaks)


def _measured(record: dict[str, object], metric: str, scenario: str) -> float:
    if metric == "startup_peak_bytes_per_capability":
        return _startup_peak(record)
    if metric in SCALAR_METRICS:
        value = record.get(metric)
        if value is None:
            raise SystemExit(f"benchmark record has no {metric}")
        return float(value)  # ty: ignore[invalid-argument-type]
    section = record.get(metric)
    if not isinstance(section, dict):
        raise SystemExit(f"benchmark record has no {metric} section")
    if scenario not in section:
        raise SystemExit(f"benchmark record has no {metric}.{scenario}")
    return float(section[scenario])  # ty: ignore[invalid-argument-type]


def _limits(metric: str, specification: object) -> list[tuple[str, float]]:
    """Return (scenario, maximum) pairs for one metric's budget specification."""
    if not isinstance(specification, dict):
        raise SystemExit(f"budget for {metric} must be an object")
    if metric in SCALAR_METRICS:
        return [("", float(specification["maximum"]))]  # ty: ignore[invalid-argument-type]
    limits = []
    for scenario, entry in specification.items():
        if not isinstance(entry, dict) or "maximum" not in entry:
            raise SystemExit(f"budget for {metric}.{scenario} needs a maximum")
        limits.append((scenario, float(entry["maximum"])))  # ty: ignore[invalid-argument-type]
    return limits


def evaluate(budgets: dict[str, object], records: dict[str, dict[str, object]]) -> list[Breach]:
    """Compare every budgeted metric against its measured value."""
    benchmarks = budgets.get("benchmarks")
    if not isinstance(benchmarks, dict) or not benchmarks:
        raise SystemExit("budget file declares no benchmarks")

    breaches: list[Breach] = []
    for name, specification in benchmarks.items():
        if not isinstance(specification, dict):
            raise SystemExit(f"budget for {name} must be an object")
        record = records[name]
        recorded = record.get("benchmark")
        if recorded != name:
            raise SystemExit(f"record for {name} reports benchmark {recorded!r}")
        metrics = specification.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            raise SystemExit(f"budget for {name} declares no metrics")
        for metric, entry in metrics.items():
            for scenario, maximum in _limits(metric, entry):
                measured = _measured(record, metric, scenario)
                if measured > maximum:
                    breaches.append(Breach(name, metric, scenario, measured, maximum))
    return breaches


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument(
        "--record",
        action="append",
        type=Path,
        default=None,
        help="check an existing benchmark JSON record instead of running the benchmark",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    budgets = _load(args.budgets)
    _validate_budget_schema(budgets)

    benchmarks = budgets.get("benchmarks")
    if not isinstance(benchmarks, dict):
        raise SystemExit("budget file declares no benchmarks")

    records: dict[str, dict[str, object]] = {}
    if args.record:
        for path in args.record:
            record = _load(path)
            name = record.get("benchmark")
            if not isinstance(name, str):
                raise SystemExit(f"{path} does not name a benchmark")
            records[name] = record
        missing = sorted(set(benchmarks) - set(records))
        if missing:
            raise SystemExit(f"no record supplied for: {', '.join(missing)}")
    else:
        for name, specification in benchmarks.items():
            if not isinstance(specification, dict):
                raise SystemExit(f"budget for {name} must be an object")
            command = specification.get("command")
            if not isinstance(command, list) or not command:
                raise SystemExit(f"budget for {name} declares no command")
            records[name] = _run_benchmark([str(part) for part in command])

    breaches = evaluate(budgets, records)
    if breaches:
        print("performance budget exceeded:", file=sys.stderr)
        for breach in sorted(breaches, key=lambda item: item.overage, reverse=True):
            print(f"  {breach}", file=sys.stderr)
        print(
            "\nA budget is a reviewed decision. If this change is an intended and "
            "justified cost, edit docs/performance/budgets.json deliberately with "
            "rationale and evidence; do not widen it to make this run pass.",
            file=sys.stderr,
        )
        return 1

    checked = sum(
        len(_limits(metric, entry))
        for specification in benchmarks.values()
        for metric, entry in specification["metrics"].items()  # type: ignore[index]
    )
    print(f"all {checked} performance budgets satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

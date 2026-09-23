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
import math
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGETS = ROOT / "docs" / "performance" / "budgets.json"
BUDGET_SCHEMA_VERSION = 2
RECORD_SCHEMA_VERSION = 2

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
PROFILE_ENVIRONMENT_FIELDS = frozenset({"implementation", "python_major_minor", "gil_enabled"})


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
            f"{self.benchmark}: {where} observed {self.measured:,.3f}, "
            f"allowed threshold {self.maximum:,.3f}, "
            f"overage +{self.measured - self.maximum:,.3f} ({self.overage:.2f}x limit)"
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
        _validate_profile_spec(name, specification.get("environment_profile"))


def _validate_profile_spec(name: str, profile: object) -> None:
    """Reject an incomplete or ambiguous execution profile in a budget file."""
    if not isinstance(profile, dict):
        raise SystemExit(f"budget for {name} declares no environment profile")
    environment = profile.get("environment")
    dimensions = profile.get("execution_dimensions")
    if not isinstance(environment, dict) or set(environment) != PROFILE_ENVIRONMENT_FIELDS:
        expected = ", ".join(sorted(PROFILE_ENVIRONMENT_FIELDS))
        raise SystemExit(f"environment profile for {name} must declare exactly: {expected}")
    if not isinstance(environment["implementation"], str):
        raise SystemExit(f"environment profile for {name} has a malformed implementation")
    if not isinstance(environment["python_major_minor"], str):
        raise SystemExit(f"environment profile for {name} has a malformed python_major_minor")
    if not isinstance(environment["gil_enabled"], bool):
        raise SystemExit(f"environment profile for {name} has a malformed gil_enabled")
    if not isinstance(dimensions, dict) or not dimensions:
        raise SystemExit(f"environment profile for {name} declares no execution dimensions")


def _validate_record_profile(
    name: str, specification: dict[str, object], record: dict[str, object]
) -> None:
    """Fail closed when a result was recorded under another benchmark contract."""
    profile = specification["environment_profile"]
    if not isinstance(profile, dict):  # Guarded by _validate_budget_schema.
        raise SystemExit(f"budget for {name} declares no environment profile")
    expected_environment = profile.get("environment")
    expected_dimensions = profile.get("execution_dimensions")
    if not isinstance(expected_environment, dict) or not isinstance(expected_dimensions, dict):
        raise SystemExit(f"budget for {name} declares a malformed environment profile")
    environment = record.get("environment")
    dimensions = record.get("execution_dimensions")
    if not isinstance(environment, dict):
        raise SystemExit(f"benchmark record for {name} has no environment object")
    if not isinstance(dimensions, dict):
        raise SystemExit(f"benchmark record for {name} has no execution_dimensions object")

    for field in ("implementation", "gil_enabled"):
        if environment.get(field) != expected_environment[field]:
            raise SystemExit(
                f"benchmark record for {name} environment-profile mismatch: "
                f"{field} is {environment.get(field)!r}, expected {expected_environment[field]!r}"
            )

    python_version = environment.get("python_version")
    if (
        not isinstance(python_version, str)
        or ".".join(python_version.split(".")[:2]) != expected_environment["python_major_minor"]
    ):
        raise SystemExit(
            f"benchmark record for {name} environment-profile mismatch: python_version "
            f"is {python_version!r}, expected {expected_environment['python_major_minor']!r}.x"
        )

    for field, expected in expected_dimensions.items():
        if dimensions.get(field) != expected:
            raise SystemExit(
                f"benchmark record for {name} environment-profile mismatch: "
                f"execution_dimensions.{field} is {dimensions.get(field)!r}, expected {expected!r}"
            )


def _number(value: object, description: str) -> float:
    """Return a finite measurement or reject a malformed artifact deterministically."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise SystemExit(f"{description} must be a finite number")
    try:
        number = float(value)
    except TypeError, ValueError:
        raise SystemExit(f"{description} must be a finite number") from None
    if not math.isfinite(number):
        raise SystemExit(f"{description} must be a finite number")
    return number


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
        try:
            value = entry["peak_bytes_per_capability"]
        except KeyError:
            raise SystemExit(
                "benchmark record has a startup entry without peak_bytes_per_capability"
            ) from None
        peaks.append(_number(value, "benchmark startup peak_bytes_per_capability"))
    return max(peaks)


def _measured(record: dict[str, object], metric: str, scenario: str) -> float:
    if metric == "startup_peak_bytes_per_capability":
        return _startup_peak(record)
    if metric in SCALAR_METRICS:
        value = record.get(metric)
        if value is None:
            raise SystemExit(f"benchmark record has no {metric}")
        return _number(value, f"benchmark record {metric}")
    section = record.get(metric)
    if not isinstance(section, dict):
        raise SystemExit(f"benchmark record has no {metric} section")
    if scenario not in section:
        raise SystemExit(f"benchmark record has no {metric}.{scenario}")
    return _number(section[scenario], f"benchmark record {metric}.{scenario}")


def _limits(metric: str, specification: object) -> list[tuple[str, float]]:
    """Return (scenario, maximum) pairs for one metric's budget specification."""
    if not isinstance(specification, dict):
        raise SystemExit(f"budget for {metric} must be an object")
    if metric in SCALAR_METRICS:
        try:
            maximum = specification["maximum"]
        except KeyError:
            raise SystemExit(f"budget for {metric} needs a maximum") from None
        maximum_number = _number(maximum, f"budget for {metric}.maximum")
        if maximum_number <= 0:
            raise SystemExit(f"budget for {metric}.maximum must be greater than zero")
        return [("", maximum_number)]
    limits = []
    for scenario, entry in specification.items():
        if not isinstance(entry, dict) or "maximum" not in entry:
            raise SystemExit(f"budget for {metric}.{scenario} needs a maximum")
        maximum = _number(entry["maximum"], f"budget for {metric}.{scenario}")
        if maximum <= 0:
            raise SystemExit(f"budget for {metric}.{scenario} must be greater than zero")
        limits.append((scenario, maximum))
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
        if record.get("schema_version") != RECORD_SCHEMA_VERSION:
            raise SystemExit(
                f"benchmark record for {name} has unsupported schema version "
                f"{record.get('schema_version')!r}; expected {RECORD_SCHEMA_VERSION}"
            )
        metrics = specification.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            raise SystemExit(f"budget for {name} declares no metrics")
        unbudgeted = sorted((set(record) & SUPPORTED_METRICS) - set(metrics))
        if unbudgeted:
            raise SystemExit(
                f"benchmark record for {name} contains enforceable metrics without budgets: "
                f"{', '.join(unbudgeted)}"
            )
        _validate_record_profile(name, specification, record)
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
            if name in records:
                raise SystemExit(f"more than one record supplied for {name}")
            records[name] = record
        missing = sorted(set(benchmarks) - set(records))
        if missing:
            raise SystemExit(f"no record supplied for: {', '.join(missing)}")
        extra = sorted(set(records) - set(benchmarks))
        if extra:
            raise SystemExit(f"record supplied for an unbudgeted benchmark: {', '.join(extra)}")
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

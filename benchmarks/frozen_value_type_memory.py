"""Compare frozen slotted and dict-backed value-type memory.

Run from the repository root with the Python build under evaluation:

    python benchmarks/frozen_value_type_memory.py

The synthetic seven-field shape matches ``CapabilityDefinition``'s field
count while avoiding unrelated normalization allocations. Results include the
holding list in both measurements, so the delta remains comparable.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import subprocess
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SlottedValue:
    first: object
    second: object
    third: object
    fourth: object
    fifth: object
    sixth: object
    seventh: object


@dataclass(frozen=True)
class DictBackedValue:
    first: object
    second: object
    third: object
    fourth: object
    fifth: object
    sixth: object
    seventh: object


_SHARED = object()


def _slotted() -> SlottedValue:
    return SlottedValue(*([_SHARED] * 7))


def _dict_backed() -> DictBackedValue:
    return DictBackedValue(*([_SHARED] * 7))


def _measure(factory: Callable[[], object], count: int) -> int:
    gc.collect()
    tracemalloc.start()
    instances = [factory() for _ in range(count)]
    current_bytes, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(instances) == count
    return current_bytes


def _median(factory: Callable[[], object], count: int, trials: int) -> int:
    return int(statistics.median(_measure(factory, count) for _ in range(trials)))


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run(*, count: int, trials: int) -> dict[str, Any]:
    slotted_bytes = _median(_slotted, count, trials)
    dict_backed_bytes = _median(_dict_backed, count, trials)
    return {
        "commit": _git_commit(),
        "count": count,
        "trials": trials,
        "python": platform.python_version(),
        "python_build": platform.python_build(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "slotted_bytes": slotted_bytes,
        "dict_backed_bytes": dict_backed_bytes,
        "saved_bytes": dict_backed_bytes - slotted_bytes,
        "slotted_bytes_per_instance_including_list": slotted_bytes / count,
        "dict_backed_bytes_per_instance_including_list": dict_backed_bytes / count,
        "slotted_fraction": slotted_bytes / dict_backed_bytes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()
    if args.count <= 0 or args.trials <= 0:
        parser.error("--count and --trials must be positive")
    print(json.dumps(run(count=args.count, trials=args.trials), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

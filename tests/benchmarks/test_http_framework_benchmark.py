"""Contract tests for the E6.10 comparative HTTP benchmark."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "http_frameworks.py"


def test_http_framework_benchmark_emits_reproducible_json_contract() -> None:
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
        timeout=60,
    )
    record = json.loads(completed.stdout)

    assert set(record) == {
        "schema_version",
        "benchmark",
        "recorded_at_utc",
        "git",
        "environment",
        "versions",
        "config",
        "measurement_boundary",
        "sample_order",
        "results",
        "median_ratio_to_direct_asgi",
    }
    assert record["schema_version"] == 1
    assert record["benchmark"] == "agnara.http.frameworks"
    assert record["versions"] == {
        "agnara-http": importlib.metadata.version("agnara-http"),
        "fastapi": "0.141.1",
        "litestar": "2.24.0",
        "starlette": "1.6.0",
    }
    assert record["config"] == {
        "garbage_collector_disabled_during_samples": True,
        "iterations_per_sample": 2,
        "samples": 2,
        "scenario_order": "deterministic rotation",
        "warmup_rounds": 1,
    }
    assert record["measurement_boundary"]["excluded"] == [
        "application construction and startup",
        "ASGI server",
        "socket and HTTP protocol parsing",
        "network",
    ]
    names = {"direct_asgi", "starlette", "fastapi", "litestar", "agnara_http"}
    assert set(record["results"]) == names
    assert set(record["median_ratio_to_direct_asgi"]) == names - {"direct_asgi"}
    assert record["sample_order"] == [
        ["direct_asgi", "starlette", "fastapi", "litestar", "agnara_http"],
        ["starlette", "fastapi", "litestar", "agnara_http", "direct_asgi"],
    ]
    for result in record["results"].values():
        assert len(result["elapsed_ns"]) == 2
        assert len(result["ns_per_request"]) == 2
        assert result["summary_ns_per_request"]["median"] > 0
        assert result["semantics"]


def test_http_framework_benchmark_human_output_names_the_boundary() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--iterations", "1", "--samples", "1", "--warmups", "1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert "in-process ASGI, no server" in completed.stdout
    for name in ("direct_asgi", "starlette", "fastapi", "litestar", "agnara_http"):
        assert f"{name}:" in completed.stdout


def test_http_framework_benchmark_rejects_non_positive_sampling_controls() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--iterations", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 2
    assert "must be at least 1" in completed.stderr

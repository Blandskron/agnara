import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "runtime_invocation.py"


def test_runtime_benchmark_emits_reproducible_json_contract() -> None:
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

    record = json.loads(completed.stdout)

    assert set(record) == {
        "schema_version",
        "benchmark",
        "recorded_at_utc",
        "git",
        "environment",
        "config",
        "results",
        "median_ratio_to_direct",
    }
    assert record["schema_version"] == 1
    assert record["benchmark"] == "agnara.runtime.invocation"
    assert record["config"] == {
        "garbage_collector_disabled_during_samples": True,
        "iterations_per_sample": 2,
        "samples": 2,
        "warmup_batches": 1,
    }
    assert set(record["results"]) == {
        "direct_async_handler",
        "compiled_invoke",
        "canonical_invoke_result",
    }
    assert set(record["median_ratio_to_direct"]) == {
        "compiled_invoke",
        "canonical_invoke_result",
    }
    assert set(record["git"]) == {"commit", "dirty"}
    assert record["git"]["commit"]
    assert isinstance(record["git"]["dirty"], bool)
    assert set(record["environment"]) == {
        "implementation",
        "python_version",
        "python_build",
        "python_executable",
        "gil_enabled",
        "platform",
        "machine",
        "processor",
        "cpu_count",
        "timer",
    }
    assert record["environment"]["python_version"]

    for result in record["results"].values():
        assert set(result) == {
            "elapsed_ns",
            "ns_per_operation",
            "summary_ns_per_operation",
        }
        assert len(result["elapsed_ns"]) == 2
        assert len(result["ns_per_operation"]) == 2
        assert set(result["summary_ns_per_operation"]) == {
            "minimum",
            "median",
            "mean",
            "maximum",
            "stdev",
        }
        assert result["summary_ns_per_operation"]["median"] > 0

    assert all(ratio > 0 for ratio in record["median_ratio_to_direct"].values())


def test_runtime_benchmark_rejects_non_positive_sampling_controls() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--samples", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "must be at least 1" in completed.stderr

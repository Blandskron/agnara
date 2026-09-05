"""Contract tests for the E7.9 comparative MCP tool-invocation benchmark."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "mcp_tool_invocation.py"
ORDER = (
    "direct_sdk",
    "mcpserver_sync",
    "mcpserver_async",
    "agnara_mcp_sync",
    "agnara_mcp_async",
)
NAMES = set(ORDER)


def test_mcp_tool_invocation_benchmark_emits_reproducible_json_contract() -> None:
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
        timeout=120,
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
        "measurement_boundaries",
        "sample_order",
        "results",
        "median_ratio_to_direct_sdk",
    }
    assert record["schema_version"] == 1
    assert record["benchmark"] == "agnara.mcp.tool_invocation"
    assert record["versions"] == {
        "agnara": importlib.metadata.version("agnara"),
        "agnara-mcp": importlib.metadata.version("agnara-mcp"),
        "mcp": "2.1.1",
        "mcp-types": "2.1.1",
    }
    assert record["config"] == {
        "garbage_collector_disabled_during_samples": True,
        "iterations_per_sample": 2,
        "reference_scenario": "direct_sdk",
        "samples": 2,
        "scenario_order": "deterministic rotation",
        "warmup_rounds": 1,
    }
    assert set(record["measurement_boundaries"]) == {"handler", "client"}
    assert "server middleware" in record["measurement_boundaries"]["handler"]["excluded"]
    assert "outputSchema" in record["measurement_boundaries"]["client"]["semantic_difference"]

    for boundary in ("handler", "client"):
        results = record["results"][boundary]
        assert set(results) == NAMES
        assert set(record["median_ratio_to_direct_sdk"][boundary]) == NAMES - {"direct_sdk"}
        assert record["sample_order"][boundary] == [
            list(ORDER),
            [*ORDER[1:], ORDER[0]],
        ]
        for result in results.values():
            assert len(result["elapsed_ns"]) == 2
            assert len(result["ns_per_call"]) == 2
            assert result["summary_ns_per_call"]["median"] > 0
            assert result["semantics"]

    handler = record["results"]["handler"]
    assert handler["agnara_mcp_sync"]["text_content"] == '{"result":41}'
    assert handler["agnara_mcp_sync"]["declares_output_schema"] is False
    assert handler["mcpserver_sync"]["declares_output_schema"] is True
    # The sync/async split is what keeps MCPServer's worker-thread policy from
    # being reported as dispatch cost.
    assert {name: handler[name]["handler_kind"] for name in ORDER} == {
        "direct_sdk": "async",
        "mcpserver_sync": "sync",
        "mcpserver_async": "async",
        "agnara_mcp_sync": "sync",
        "agnara_mcp_async": "async",
    }
    assert "worker thread" in handler["mcpserver_sync"]["semantics"]


def test_mcp_tool_invocation_benchmark_human_output_names_both_boundaries() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--iterations", "1", "--samples", "1", "--warmups", "1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert "in-process MCP, no network" in completed.stdout
    assert "[handler boundary]" in completed.stdout
    assert "[client boundary]" in completed.stdout
    for name in NAMES:
        assert f"{name}:" in completed.stdout


def test_mcp_tool_invocation_benchmark_rejects_non_positive_sampling_controls() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--samples", "0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 2
    assert "must be at least 1" in completed.stderr

"""Exercise the provisional inbound events example and its resource lifecycle."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from examples.events_inbound import demonstrate
from jsonschema import Draft7Validator


def test_events_inbound_example_outcomes_and_cleanup() -> None:
    async def run() -> dict:
        before = asyncio.all_tasks()
        result = await demonstrate()
        assert asyncio.all_tasks() == before
        return result

    outcome = asyncio.run(run())
    assert outcome["surface_count"] == 1
    assert outcome["asyncapi"] == "3.1.0"
    assert outcome["diagnostics"] == [
        ("success", "acknowledge"),
        ("conflict", "reject"),
        ("invalid_input", "reject"),
        ("type_mismatch", "reject"),
        ("internal_failure", "release"),
        ("cancelled", "release"),
    ]
    assert outcome["events"][-3:] == [
        "ledger.close",
        "delivery.release",
        "container.close",
    ]
    assert "private-broker-diagnostic-must-be-redacted" not in json.dumps(outcome)

    schema = outcome["doc"]["components"]["messages"]["inventory-applyMessage"]["payload"]["schema"]
    Draft7Validator.check_schema(schema)
    assert "servers" not in outcome["doc"]
    assert "ledger" not in schema["properties"]["data"]["properties"]


def test_events_inbound_example_runs_outside_checkout(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "examples" / "events_inbound.py"
    completed = subprocess.run(
        [sys.executable, str(source)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines()[:8] == [
        "asyncapi: 3.1.0",
        "surfaces: 1",
        "success: acknowledge",
        "conflict: reject",
        "invalid_input: reject",
        "type_mismatch: reject",
        "internal_failure: release",
        "cancelled: release",
    ]

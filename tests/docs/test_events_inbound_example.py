"""Exercise the provisional inbound events example and its resource lifecycle."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from examples.events_inbound import demonstrate
from jsonschema import Draft7Validator

from tests.reference_apps.events_guide import validate


@pytest.fixture(scope="module")
def outcome():
    async def run() -> dict:
        before = asyncio.all_tasks()
        result = await demonstrate()
        assert asyncio.all_tasks() == before
        return result

    return asyncio.run(run())


def test_events_inbound_example_outcomes_and_cleanup(outcome) -> None:
    validate(outcome)
    schema = outcome["doc"]["components"]["messages"]["inventory-applyMessage"]["payload"]["schema"]
    Draft7Validator.check_schema(schema)


@pytest.mark.parametrize(
    "corruption",
    ["diagnostics", "events", "redaction", "servers", "protected_param"],
)
def test_artifact_validator_rejects_incorrect_evidence(outcome, corruption: str) -> None:
    changed = deepcopy(outcome)
    if corruption == "diagnostics":
        changed["diagnostics"][0] = ("success", "reject")
    elif corruption == "events":
        changed["events"][-2:] = reversed(changed["events"][-2:])
    elif corruption == "redaction":
        changed["diagnostics"].append(("private-broker-diagnostic-must-be-redacted", "release"))
    elif corruption == "servers":
        changed["doc"]["servers"] = {"prod": {"host": "amqp://secret"}}
    else:
        schema = changed["doc"]["components"]["messages"]["inventory-applyMessage"]["payload"][
            "schema"
        ]
        schema["properties"]["data"]["properties"]["ledger"] = {"type": "string"}
    with pytest.raises(AssertionError):
        validate(changed)


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

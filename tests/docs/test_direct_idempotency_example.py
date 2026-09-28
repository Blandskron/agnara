"""The public direct-idempotency example keeps authority and effects separate."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from examples.direct_idempotency import demonstrate

from agnara.execution import Failure, FailureCode, Success


def test_direct_idempotency_example_reuses_only_authorized_matching_success() -> None:
    outcomes, effects = asyncio.run(demonstrate())

    first = outcomes["first"]
    duplicate = outcomes["duplicate"]
    other_principal = outcomes["other_principal"]
    assert isinstance(first, Success)
    assert isinstance(duplicate, Success)
    assert isinstance(other_principal, Success)
    assert first.value == duplicate.value == "receipt-1"
    assert first.execution_id == duplicate.execution_id
    assert other_principal.value == "receipt-2"
    assert other_principal.execution_id != first.execution_id
    changed = outcomes["changed_input"]
    denied = outcomes["permission_lost"]
    assert isinstance(changed, Failure) and changed.code is FailureCode.CONFLICT
    assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
    assert effects == [("A-1", 2500), ("A-1", 2500)]


def test_direct_idempotency_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "direct_idempotency.py"
    completed = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "first: receipt-1",
        "duplicate: receipt-1",
        "changed_input: conflict",
        "permission_lost: forbidden",
        "other_principal: receipt-2",
        "effects: [('A-1', 2500), ('A-1', 2500)]",
    ]

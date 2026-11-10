"""Runnable schema guide verifies both Python and JSON boundaries."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples import schema_contracts

from agnara.di import DIContainer
from agnara.execution import Failure, FailureCode, Success
from agnara.schema import serialize_json


def test_schema_guide_outcomes_identity_paths_and_policy_order(monkeypatch, caplog) -> None:
    materialized: list[object] = []
    original_materialize = schema_contracts.materialize_json
    original_close = DIContainer.aclose
    closed: list[DIContainer] = []

    def record_materialize(schema, value):
        materialized.append(value)
        return original_materialize(schema, value)

    async def record_close(self: DIContainer) -> None:
        await original_close(self)
        closed.append(self)

    original_invoke = schema_contracts.invoke_result

    async def assert_denial_precedes_materialization(plan, context, **kwargs):
        result = await original_invoke(plan, context, **kwargs)
        if not context.principal.scopes:
            assert isinstance(result, Failure) and result.code is FailureCode.FORBIDDEN
            assert materialized == []
        return result

    monkeypatch.setattr(schema_contracts, "materialize_json", record_materialize)
    monkeypatch.setattr(schema_contracts, "invoke_result", assert_denial_precedes_materialization)
    monkeypatch.setattr(DIContainer, "aclose", record_close)

    async def run() -> None:
        before = asyncio.all_tasks()
        demo = await schema_contracts.demonstrate()
        expected = schema_contracts.Receipt(250, schema_contracts.Currency.CLP)
        for name in ("direct", "json", "json_defaults"):
            assert demo.results[name] == Success(expected)
        assert demo.results["annotation_only"] == Success("annotation alone is unconstrained")
        for name, path in (
            ("mapping", ("order",)),
            ("bad_quantity", ("order", "lines", 0, "quantity")),
            ("bool_quantity", ("order", "lines", 0, "quantity")),
            ("extra_field", ("order", "undeclared")),
            ("bad_currency", ("order", "currency")),
        ):
            result = demo.results[name]
            assert isinstance(result, Failure) and result.code is FailureCode.INVALID_INPUT
            assert result.details["path"] == path
            assert "private" not in result.message
        assert isinstance(demo.results["denied"], Failure)
        broken = demo.results["bad_output"]
        assert isinstance(broken, Failure) and broken.code is FailureCode.INTERNAL_FAILURE
        assert broken.message == "capability invocation failed" and not broken.details
        assert demo.events == ["quote.enter"] * 3 + ["broken.enter", "annotated.enter"]
        assert len(demo.handled) == 3
        assert demo.handled[0] is demo.direct_order
        assert demo.handled[1] is not demo.direct_order
        assert demo.handled[2] is not demo.handled[1]
        assert demo.handled == [demo.direct_order] * 3
        assert all(order.note is None for order in demo.handled)
        assert all(type(order.lines[0]) is schema_contracts.Line for order in demo.handled)
        assert demo.wire_order == {"lines": [{"quantity": 2, "unit_cents": 125}], "currency": "CLP"}
        assert len(materialized) == 6
        assert len(closed) == 1 and asyncio.all_tasks() == before
        assert serialize_json(expected) == {"total_cents": 250, "currency": "CLP"}
        input_schema = demo.schemas["input"]
        assert isinstance(input_schema, dict)
        assert input_schema["required"] == ["lines"]
        assert input_schema["additionalProperties"] is False
        assert input_schema["properties"]["currency"]["enum"] == ["CLP", "USD"]
        assert demo.schemas["annotation_only"] == {}

    asyncio.run(run())
    assert "private producer value" not in caplog.text


def test_schema_guide_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "schema_contracts.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "denied: forbidden",
        'direct: {"currency": "CLP", "total_cents": 250}',
        "mapping: invalid_input",
        'json: {"currency": "CLP", "total_cents": 250}',
        'json_defaults: {"currency": "CLP", "total_cents": 250}',
        "bad_quantity: invalid_input",
        "bool_quantity: invalid_input",
        "extra_field: invalid_input",
        "bad_currency: invalid_input",
        "bad_output: internal_failure",
        'annotation_only: "annotation alone is unconstrained"',
        "events: " + repr(["quote.enter"] * 3 + ["broken.enter", "annotated.enter"]),
    ]
    assert "private" not in completed.stdout + completed.stderr


def test_schema_guide_propagates_cancellation_and_closes_container(monkeypatch) -> None:
    original_close = DIContainer.aclose
    closed: list[DIContainer] = []

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    async def record_close(self: DIContainer) -> None:
        await original_close(self)
        closed.append(self)

    monkeypatch.setattr(schema_contracts, "invoke_result", cancel)
    monkeypatch.setattr(DIContainer, "aclose", record_close)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(schema_contracts.demonstrate())
    assert len(closed) == 1

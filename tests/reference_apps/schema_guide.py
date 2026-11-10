"""Check the exact schema guide with installed distributions under Python -I."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from dataclasses import is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, Success
from agnara.schema import serialize_json


def validate(demo: Any) -> None:
    assert isinstance(demo.direct_order.currency, Enum)
    failures = {
        "mapping": ("order",),
        "bad_quantity": ("order", "lines", 0, "quantity"),
        "bool_quantity": ("order", "lines", 0, "quantity"),
        "extra_field": ("order", "undeclared"),
        "bad_currency": ("order", "currency"),
    }
    assert demo.results.keys() == failures.keys() | {
        "denied",
        "direct",
        "json",
        "json_defaults",
        "bad_output",
        "annotation_only",
    }
    for name in ("direct", "json", "json_defaults"):
        result = demo.results[name]
        assert isinstance(result, Success) and is_dataclass(result.value)
        assert type(result.value.total_cents) is int and result.value.total_cents == 250
        assert result.value.currency is demo.direct_order.currency
        assert serialize_json(result.value) == {"total_cents": 250, "currency": "CLP"}
    assert demo.results["annotation_only"] == Success("annotation alone is unconstrained")
    denied = demo.results["denied"]
    assert isinstance(denied, Failure) and denied.code is FailureCode.FORBIDDEN
    for name, path in failures.items():
        result = demo.results[name]
        assert isinstance(result, Failure) and result.code is FailureCode.INVALID_INPUT
        assert result.details["path"] == path, name
    broken = demo.results["bad_output"]
    assert isinstance(broken, Failure) and broken.code is FailureCode.INTERNAL_FAILURE
    assert broken.message == "capability invocation failed" and not broken.details
    for result in demo.results.values():
        if isinstance(result, Failure):
            assert "private" not in result.message + repr(result.details)

    assert demo.events == ["quote.enter"] * 3 + ["broken.enter", "annotated.enter"]
    assert len(demo.handled) == 3 and demo.handled[0] is demo.direct_order
    assert all(order is not demo.direct_order for order in demo.handled[1:])
    assert demo.handled[2] is not demo.handled[1]
    for order in demo.handled:
        assert type(order) is type(demo.direct_order)
        assert order == demo.direct_order and order.note is None
        assert len(order.lines) == 1 and type(order.lines[0]) is type(demo.direct_order.lines[0])
        assert type(order.lines[0].quantity) is int and order.lines[0].quantity == 2
        assert type(order.lines[0].unit_cents) is int and order.lines[0].unit_cents == 125
        assert order.currency is demo.direct_order.currency
    assert demo.wire_order == {"lines": [{"quantity": 2, "unit_cents": 125}], "currency": "CLP"}

    currency = {"type": "string", "enum": ["CLP", "USD"]}
    expected_schemas = {
        "input": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quantity": {"type": "integer"},
                            "unit_cents": {"type": "integer"},
                        },
                        "required": ["quantity", "unit_cents"],
                        "additionalProperties": False,
                    },
                },
                "currency": currency,
                "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            "required": ["lines"],
            "additionalProperties": False,
        },
        "output": {
            "type": "object",
            "properties": {"total_cents": {"type": "integer"}, "currency": currency},
            "required": ["total_cents", "currency"],
            "additionalProperties": False,
        },
        "annotation_only": {},
    }
    assert json.dumps(demo.schemas, sort_keys=True) == json.dumps(expected_schemas, sort_keys=True)


async def run_guide(path: Path) -> Any:
    # Keep the real module registered while deferred dataclass annotations are
    # resolved. No source/annotation rewriting or checkout imports are needed.
    name = "_agnara_schema_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        async with asyncio.timeout(20):
            demo = await module.demonstrate()
        assert asyncio.all_tasks() == {asyncio.current_task()}, "guide tasks survived"
        return demo
    finally:
        del sys.modules[name]


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("SCHEMA_GUIDE_ARTIFACT_OK")

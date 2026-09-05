"""E7.8a canonical result projection through the pinned SDK serializer."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from mcp_types import CallToolResult, InputRequiredResult
from mcp_types.methods import serialize_server_result

from agnara import CapabilityDefinition, CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
)
from agnara_mcp import (
    MCP_PROTOCOL_VERSION,
    McpInteractionProjectionError,
    McpResultProjectionError,
    project_mcp_interaction_required,
    project_mcp_result,
)


def wire(result: CallToolResult | InputRequiredResult) -> dict[str, Any]:
    return serialize_server_result(
        "tools/call",
        MCP_PROTOCOL_VERSION,
        result.model_dump(by_alias=True, mode="json", exclude_none=True),
    )


@pytest.mark.parametrize("value", [None, True, 7, 1.5, "á\n", [], {}, [1, None], (1, 2)])
def test_json_success_has_equivalent_text_and_structured_content(value: object) -> None:
    result = project_mcp_result(Success(value))
    expected = json.loads(json.dumps({"result": value}))
    document = wire(result)
    assert document == {
        "resultType": "complete",
        "isError": False,
        "structuredContent": expected,
        "content": [
            {"type": "text", "text": json.dumps(expected, sort_keys=True, separators=(",", ":"))}
        ],
    }


def test_results_are_deterministic_and_detached_from_all_other_projections() -> None:
    shared = [1]
    source = {"b": shared, "a": shared}
    first = project_mcp_result(Success(source))
    second = project_mcp_result(Success({"a": [1], "b": [1]}))
    assert wire(first) == wire(second)
    assert isinstance(first, CallToolResult)
    source["a"].append(2)
    assert first.structured_content == {"result": {"a": [1], "b": [1]}}
    first.structured_content["result"]["a"].append(3)
    assert first.structured_content["result"]["b"] == [1]
    assert wire(second)["structuredContent"] == {"result": {"a": [1], "b": [1]}}


@pytest.mark.parametrize(
    "code", [code for code in FailureCode if code is not FailureCode.INTERACTION_REQUIRED]
)
def test_canonical_failure_exposes_only_its_safe_message_and_code(code: FailureCode) -> None:
    document = wire(project_mcp_result(Failure(code, "Safe message", {"token": "private-secret"})))
    assert document == {
        "resultType": "complete",
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {"code": code.value, "message": "Safe message"},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        ],
    }
    assert "private-secret" not in json.dumps(document)


def test_interaction_uses_the_existing_strict_projection() -> None:
    failure = Failure(
        FailureCode.INTERACTION_REQUIRED,
        "Please confirm",
        {"kind": "confirmation", "title": "Confirm", "capability_id": "demo.run", "hints": ()},
    )
    result = project_mcp_result(failure)
    assert isinstance(result, InputRequiredResult)
    assert wire(result) == wire(project_mcp_interaction_required(failure))
    with pytest.raises(McpInteractionProjectionError):
        project_mcp_result(Failure(FailureCode.INTERACTION_REQUIRED, "Missing details"))


class PrivateObject:
    def __repr__(self) -> str:
        raise AssertionError("repr must never be called")


class CustomDict(dict):
    pass


@pytest.mark.parametrize(
    "value",
    [
        PrivateObject(),
        CustomDict(secret="hidden"),
        b"secret",
        {1: "secret"},
        {"set"},
        float("nan"),
        float("inf"),
        float("-inf"),
        {"nested": [PrivateObject()]},
    ],
)
def test_non_json_success_fails_without_serializing_values(value: object) -> None:
    with pytest.raises(McpResultProjectionError) as captured:
        project_mcp_result(Success(value))
    assert str(captured.value) == (
        "MCP success value must be finite, acyclic JSON data within 64 nesting levels"
    )


def test_cycles_and_excessive_depth_are_rejected_but_shared_values_are_valid() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(McpResultProjectionError):
        project_mcp_result(Success(cycle))
    mapping: dict[str, object] = {}
    mapping["self"] = mapping
    with pytest.raises(McpResultProjectionError):
        project_mcp_result(Success(mapping))
    deep: object = None
    for _ in range(64):
        deep = [deep]
    assert isinstance(project_mcp_result(Success(deep)), CallToolResult)
    with pytest.raises(McpResultProjectionError):
        project_mcp_result(Success([deep]))


@pytest.mark.parametrize("value", [None, "secret", {}, PrivateObject()])
def test_only_canonical_outcomes_are_accepted(value: Any) -> None:
    with pytest.raises(McpResultProjectionError, match="requires Success or Failure"):
        project_mcp_result(value)


def test_real_runtime_success_input_failure_and_internal_redaction() -> None:
    async def scenario() -> None:
        calls: list[int] = []

        def handler(value: int) -> int:
            calls.append(value)
            if value < 0:
                raise RuntimeError("private-password")
            return value * 2

        registry = DIRegistry()
        plan = ExecutionPlan.compile(
            CapabilityDefinition(CapabilityId("demo", "run"), handler), registry
        )
        container = DIContainer(registry)
        try:
            for value, expected in [(2, None), ("bad", "invalid_input"), (-1, "internal_failure")]:
                outcome = await invoke_result(
                    plan,
                    ExecutionContext(
                        Invocation(plan.definition.id, {"value": value}, {}), container
                    ),
                )
                document = wire(project_mcp_result(outcome))
                if expected is None:
                    assert document["structuredContent"] == {"result": 4}
                else:
                    assert document["isError"] is True
                    assert json.loads(document["content"][0]["text"])["code"] == expected
                assert "private-password" not in json.dumps(document)
            assert calls == [2, -1]
        finally:
            await container.aclose()

    asyncio.run(scenario())


def test_external_cancellation_never_becomes_a_tool_result() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        cleaned = asyncio.Event()
        projected: list[object] = []

        async def handler() -> None:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        registry = DIRegistry()
        plan = ExecutionPlan.compile(
            CapabilityDefinition(CapabilityId("demo", "wait"), handler), registry
        )
        container = DIContainer(registry)

        async def invoke_and_project() -> None:
            outcome = await invoke_result(
                plan, ExecutionContext(Invocation(plan.definition.id, {}, {}), container)
            )
            projected.append(project_mcp_result(outcome))

        try:
            async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
                task = tasks.create_task(invoke_and_project())
                await started.wait()
                task.cancel()
            assert task.cancelled()
            assert cleaned.is_set()
            assert projected == []
        finally:
            await container.aclose()

    asyncio.run(scenario())

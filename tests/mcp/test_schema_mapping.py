"""E7.3 projection of compiled capability inputs to MCP Tool schemas."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from mcp_types import Tool

from agnara import Agnara, CapabilityDefinition, SchemaAdapter, TypeSchema
from agnara.core.di import DIRegistry, provider
from agnara.execution import ExecutionContext, ExecutionPlan
from agnara_mcp import Mcp, McpToolDefinitionError, project_mcp_tools


class _Repository: ...


def plan(definition: CapabilityDefinition, registry: DIRegistry | None = None) -> ExecutionPlan:
    return ExecutionPlan.compile(definition, registry or DIRegistry())


def test_projects_official_sdk_tool_with_ordered_required_inputs() -> None:
    app = Agnara("math")

    @app.capability(description="Add two numbers")
    def add(a: int, b: int = 1) -> int:
        return a + b

    mcp = Mcp(app)
    mcp.tool(add)
    definition = app.capabilities["math.add"]

    tools = project_mcp_tools(mcp.compile(), [plan(definition)])

    assert len(tools) == 1
    assert isinstance(tools[0], Tool)
    assert tools[0].model_dump(by_alias=True, exclude_none=True) == {
        "name": "math.add",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a"],
            "additionalProperties": False,
        },
    }


def test_zero_input_tool_is_an_explicit_closed_object() -> None:
    app = Agnara("clock")

    @app.capability
    def now() -> str:
        return "now"

    mcp = Mcp(app)
    mcp.tool(now)
    tool = project_mcp_tools(mcp.compile(), [plan(app.capabilities["clock.now"])])[0]

    assert tool.input_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert "required" not in tool.input_schema


def test_dependency_and_context_parameters_are_not_wire_inputs() -> None:
    @provider()
    def repository() -> _Repository:
        return _Repository()

    registry = DIRegistry()
    registry.bind(_Repository, repository)
    app = Agnara("users")

    @app.capability
    def get_user(user_id: str, repo: _Repository, context: ExecutionContext) -> str:
        del repo, context
        return user_id

    mcp = Mcp(app)
    mcp.tool(get_user)
    definition = app.capabilities["users.get_user"]
    tool = project_mcp_tools(mcp.compile(), [plan(definition, registry)])[0]

    assert tool.input_schema["properties"] == {"user_id": {"type": "string"}}
    assert tool.input_schema["required"] == ["user_id"]


def test_projection_preserves_exposure_order_and_allows_extra_plans() -> None:
    app = Agnara("jobs")

    @app.capability
    def first(value: str) -> str:
        return value

    @app.capability
    def second(value: int) -> int:
        return value

    @app.capability
    def hidden() -> None: ...

    mcp = Mcp(app)
    mcp.tool(second)
    mcp.tool(first)
    plans = [plan(app.capabilities[capability_id]) for capability_id in app.capabilities]

    assert [tool.name for tool in project_mcp_tools(mcp.compile(), plans)] == [
        "jobs.second",
        "jobs.first",
    ]


def test_projection_is_detached_from_schema_state_and_prior_results() -> None:
    schema_fragment = {"type": "array", "items": {"type": "string"}}

    class Schema:
        def validate(self, value: object) -> Any:
            return value

        def json_schema(self) -> Mapping[str, Any]:
            return schema_fragment

    class Adapter:
        def compile(self, annotation: Any) -> TypeSchema:
            del annotation
            return Schema()

        def supports(self, annotation: Any) -> bool:
            del annotation
            return True

    adapter: SchemaAdapter = Adapter()
    app = Agnara("data")

    @app.capability
    def echo(value: list[str]) -> list[str]:
        return value

    mcp = Mcp(app)
    mcp.tool(echo)
    execution_plan = ExecutionPlan.compile(
        app.capabilities["data.echo"], DIRegistry(), schema_adapter=adapter
    )
    first = project_mcp_tools(mcp.compile(), [execution_plan])[0]
    first.input_schema["properties"]["value"]["items"]["type"] = "integer"

    second = project_mcp_tools(mcp.compile(), [execution_plan])[0]
    assert schema_fragment["items"]["type"] == "string"
    assert second.input_schema["properties"]["value"]["items"]["type"] == "string"


@pytest.mark.parametrize(
    "bad_value", [{"bad": object()}, {1: "bad"}, {"bad": float("nan")}, ["not-an-object"]]
)
def test_non_json_schema_fragments_fail_at_startup(bad_value: Any) -> None:
    class BadSchema:
        def validate(self, value: object) -> Any:
            return value

        def json_schema(self) -> Mapping[str, Any]:
            return bad_value

    class BadAdapter:
        def compile(self, annotation: Any) -> TypeSchema:
            del annotation
            return BadSchema()

        def supports(self, annotation: Any) -> bool:
            del annotation
            return True

    app = Agnara("bad")

    @app.capability
    def capability(value: str) -> str:
        return value

    mcp = Mcp(app)
    mcp.tool(capability)
    execution_plan = ExecutionPlan.compile(
        app.capabilities["bad.capability"], DIRegistry(), schema_adapter=BadAdapter()
    )
    with pytest.raises(McpToolDefinitionError, match="MCP schema"):
        project_mcp_tools(mcp.compile(), [execution_plan])


def test_missing_duplicate_mismatched_and_invalid_plans_fail() -> None:
    app = Agnara("users")

    @app.capability
    def get_user(user_id: str) -> str:
        return user_id

    mcp = Mcp(app)
    mcp.tool(get_user)
    exposures = mcp.compile()
    definition = app.capabilities["users.get_user"]
    execution_plan = plan(definition)

    with pytest.raises(McpToolDefinitionError, match="has no execution plan"):
        project_mcp_tools(exposures, [])
    with pytest.raises(McpToolDefinitionError, match="duplicate execution plan"):
        project_mcp_tools(exposures, [execution_plan, execution_plan])
    with pytest.raises(McpToolDefinitionError, match="ExecutionPlan values"):
        project_mcp_tools(exposures, [object()])  # ty: ignore[invalid-argument-type]

    replacement = CapabilityDefinition.declare(id=definition.id, handler=get_user)
    with pytest.raises(McpToolDefinitionError, match="does not retain"):
        project_mcp_tools(exposures, [plan(replacement)])


def test_projection_requires_a_compiled_exposure_snapshot() -> None:
    with pytest.raises(TypeError, match="FrozenMcpTools"):
        project_mcp_tools(object(), [])  # ty: ignore[invalid-argument-type]

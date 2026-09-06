"""Project compiled Agnara input schemas into official MCP tool definitions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any

from mcp_types import Tool

from agnara import CapabilityId
from agnara.execution import ExecutionPlan

from .tools import FrozenMcpTools, McpToolDefinitionError, McpToolExposure

__all__ = ["project_mcp_tools"]


def _json_value(value: object, *, path: str) -> Any:
    """Return detached JSON data or fail before it reaches the protocol SDK."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise McpToolDefinitionError(f"MCP schema {path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise McpToolDefinitionError(
                    f"MCP schema {path} contains non-string object key {key!r}"
                )
            copied[key] = _json_value(item, path=f"{path}.{key}")
        return copied
    if isinstance(value, list | tuple):
        return [_json_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise McpToolDefinitionError(
        f"MCP schema {path} contains non-JSON value of type {type(value).__name__}"
    )


def _input_schema(exposure: McpToolExposure, plan: ExecutionPlan) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name, schema in plan.input_schemas.items():
        fragment = schema.json_schema()
        if not isinstance(fragment, Mapping):
            raise McpToolDefinitionError(
                f"MCP schema {exposure.name}.properties.{name} must be a JSON Schema object, "
                f"got {type(fragment).__name__}"
            )
        properties[name] = _json_value(fragment, path=f"{exposure.name}.properties.{name}")
    document: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    required = [name for name in plan.input_schemas if name in plan.required_inputs]
    if required:
        document["required"] = required
    return document


def _resolve_plans(
    exposures: FrozenMcpTools,
    plans: Iterable[ExecutionPlan],
) -> tuple[tuple[McpToolExposure, ExecutionPlan], ...]:
    """Pair every exposure with the compiled plan that still owns its capability.

    Plans are indexed once at startup. Extra plans are permitted so a caller
    can pass the application's complete compiled plan set while exposing only
    a selected subset through MCP.
    """
    if not isinstance(exposures, FrozenMcpTools):
        raise TypeError(f"exposures must be FrozenMcpTools, got {type(exposures).__name__}")
    by_id: dict[CapabilityId, ExecutionPlan] = {}
    for plan in plans:
        if not isinstance(plan, ExecutionPlan):
            raise McpToolDefinitionError(
                f"MCP plans must contain ExecutionPlan values, got {type(plan).__name__}"
            )
        capability_id = plan.definition.id
        if capability_id in by_id:
            raise McpToolDefinitionError(f"duplicate execution plan for {capability_id}")
        by_id[capability_id] = plan

    resolved: list[tuple[McpToolExposure, ExecutionPlan]] = []
    for exposure in exposures.exposures:
        plan = by_id.get(exposure.definition.id)
        if plan is None:
            raise McpToolDefinitionError(
                f"MCP tool {exposure.name!r} has no execution plan for {exposure.definition.id}"
            )
        if plan.definition is not exposure.definition:
            raise McpToolDefinitionError(
                f"MCP tool {exposure.name!r} plan does not retain its declared capability "
                f"{exposure.definition.id}"
            )
        resolved.append((exposure, plan))
    return tuple(resolved)


def project_mcp_tools(
    exposures: FrozenMcpTools,
    plans: Iterable[ExecutionPlan],
) -> tuple[Tool, ...]:
    """Create detached SDK tools from immutable exposures and execution plans."""
    projected: list[Tool] = []
    for exposure, plan in _resolve_plans(exposures, plans):
        projected.append(
            Tool(
                name=exposure.name,
                description=exposure.definition.description,
                input_schema=_input_schema(exposure, plan),
            )
        )
    return tuple(projected)

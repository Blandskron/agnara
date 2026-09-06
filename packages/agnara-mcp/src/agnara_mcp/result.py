"""Explicit JSON projection of protocol-neutral capability outcomes."""

from __future__ import annotations

import json
from math import isfinite
from typing import Any

from mcp_types import CallToolResult, InputRequiredResult, TextContent

from agnara import DefinitionError
from agnara.execution import CanonicalResult, Failure, FailureCode, Success

from .interaction import project_mcp_interaction_required

__all__ = ["McpResultProjectionError", "project_mcp_result"]

_INVALID_VALUE = "MCP success value must be finite, acyclic JSON data within 64 nesting levels"


class McpResultProjectionError(DefinitionError):
    """A canonical outcome cannot be safely represented as an MCP tool result."""


def _copy_json(value: object, ancestors: set[int], depth: int = 0) -> Any:
    if depth > 64:
        raise McpResultProjectionError(_INVALID_VALUE)
    kind = type(value)
    if value is None or kind in (bool, int, str):
        return value
    if kind is float and isinstance(value, float) and isfinite(value):
        return value
    if kind not in (dict, list, tuple) or id(value) in ancestors:
        raise McpResultProjectionError(_INVALID_VALUE)
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise McpResultProjectionError(_INVALID_VALUE)
            return {key: _copy_json(item, ancestors, depth + 1) for key, item in value.items()}
        assert isinstance(value, list | tuple)
        return [_copy_json(item, ancestors, depth + 1) for item in value]
    finally:
        ancestors.remove(id(value))


def _text(value: object) -> TextContent:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError, OverflowError:
        raise McpResultProjectionError("MCP result cannot be encoded as JSON") from None
    return TextContent(type="text", text=encoded)


def project_mcp_result(outcome: CanonicalResult[object]) -> CallToolResult | InputRequiredResult:
    """Map an invocation outcome; no dispatch, model coercion or resumption.

    Successful data is copied into a ``result`` envelope and mirrored in JSON
    text. Failure details are omitted; canonical messages must be caller-safe.
    Source values must not be mutated concurrently during projection.
    """
    if isinstance(outcome, Success):
        content = {"result": _copy_json(outcome.value, set())}
        return CallToolResult(content=[_text(content)], structured_content=content, is_error=False)
    if not isinstance(outcome, Failure):
        raise McpResultProjectionError("MCP result projection requires Success or Failure")
    if outcome.code is FailureCode.INTERACTION_REQUIRED:
        return project_mcp_interaction_required(outcome)
    return CallToolResult(
        content=[_text({"code": outcome.code.value, "message": outcome.message})],
        is_error=True,
    )

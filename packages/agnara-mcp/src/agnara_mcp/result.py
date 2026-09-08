"""Explicit JSON projection of protocol-neutral capability outcomes."""

from __future__ import annotations

import json
from typing import Any

from mcp_types import CallToolResult, InputRequiredResult, TextContent

from agnara import DefinitionError, ValidationError
from agnara.execution import CanonicalResult, Failure, FailureCode, Success
from agnara.schema import serialize_json

from .interaction import project_mcp_interaction_required

__all__ = ["McpResultProjectionError", "project_mcp_result"]

_INVALID_VALUE = "MCP success value must be finite, acyclic JSON data within 128 nesting levels"


class McpResultProjectionError(DefinitionError):
    """A canonical outcome cannot be safely represented as an MCP tool result."""


def _copy_json(value: object) -> Any:
    """Project through the shared core rule, so MCP and HTTP accept the same values.

    The failure is reported without the value or its location: a success value
    that cannot be represented is a server-side defect, and describing it to
    the caller would publish what the capability tried to return.
    """
    try:
        return serialize_json(value)
    except ValidationError:
        raise McpResultProjectionError(_INVALID_VALUE) from None


def _text(value: object) -> TextContent:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except ValueError, OverflowError:
        raise McpResultProjectionError("MCP result cannot be encoded as JSON") from None
    return TextContent(type="text", text=encoded)


def project_mcp_result(outcome: CanonicalResult[object]) -> CallToolResult | InputRequiredResult:
    """Map an invocation outcome; no dispatch, model coercion or resumption.

    Successful data is copied into a ``result`` envelope and mirrored in JSON
    text. A failure carries its code, its caller-safe message and, as the HTTP
    problem document does, its details -- immutable scalars and tuples by
    construction of `Failure`, so ``invalid_input`` can name the offending
    argument. An internal failure is redacted to its code alone.
    Source values must not be mutated concurrently during projection.
    """
    if isinstance(outcome, Success):
        content = {"result": _copy_json(outcome.value)}
        return CallToolResult(content=[_text(content)], structured_content=content, is_error=False)
    if not isinstance(outcome, Failure):
        raise McpResultProjectionError("MCP result projection requires Success or Failure")
    if outcome.code is FailureCode.INTERACTION_REQUIRED:
        return project_mcp_interaction_required(outcome)
    envelope: dict[str, Any] = {"code": outcome.code.value}
    if outcome.code is FailureCode.INTERNAL_FAILURE:
        envelope["message"] = "capability invocation failed"
    else:
        envelope["message"] = outcome.message
        if outcome.details:
            envelope["details"] = _copy_json(dict(outcome.details))
    return CallToolResult(content=[_text(envelope)], is_error=True)

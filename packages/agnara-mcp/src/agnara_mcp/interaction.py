"""Projection of canonical interaction requirements into MCP elicitation."""

from __future__ import annotations

from typing import Final

from mcp_types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult

from agnara import DefinitionError
from agnara.capability import CapabilityId
from agnara.execution import Failure, FailureCode
from agnara.policy import InteractionKind

__all__ = ["McpInteractionProjectionError", "project_mcp_interaction_required"]

_DETAIL_KEYS: Final = frozenset({"kind", "title", "capability_id", "hints"})
_REQUEST_KEY: Final = "confirmation"
_CONFIRMATION_FIELD: Final = "confirmed"


class McpInteractionProjectionError(DefinitionError):
    """A canonical interaction failure cannot be projected safely to MCP."""


def project_mcp_interaction_required(failure: Failure) -> InputRequiredResult:
    """Project one canonical confirmation requirement to MCP form elicitation.

    The returned form response is only caller input. It is not confirmation
    evidence and this projection does not implement MRTR resumption.
    """
    title = _validated_confirmation(failure)
    return InputRequiredResult(
        input_requests={
            _REQUEST_KEY: ElicitRequest(
                params=ElicitRequestFormParams(
                    message=f"{title}\n\n{failure.message}",
                    requested_schema={
                        "type": "object",
                        "properties": {
                            _CONFIRMATION_FIELD: {
                                "type": "boolean",
                                "title": "Confirm",
                                "description": "Confirm the requested operation.",
                            }
                        },
                        "required": [_CONFIRMATION_FIELD],
                    },
                )
            )
        }
    )


def _validated_confirmation(failure: object) -> str:
    if not isinstance(failure, Failure):
        raise McpInteractionProjectionError(
            f"MCP interaction projection requires Failure, got {type(failure).__name__}"
        )
    if failure.code is not FailureCode.INTERACTION_REQUIRED:
        raise McpInteractionProjectionError(
            "MCP interaction projection requires an interaction_required failure"
        )
    details = failure.details
    if frozenset(details) != _DETAIL_KEYS:
        raise McpInteractionProjectionError(
            "MCP interaction failure details must exactly match the canonical runtime shape"
        )
    if details["kind"] != InteractionKind.CONFIRMATION.value:
        raise McpInteractionProjectionError("unsupported MCP interaction kind")
    title = details["title"]
    if not isinstance(title, str) or not title:
        raise McpInteractionProjectionError(
            "MCP interaction failure title must be a non-empty string"
        )
    _validate_capability_id(details["capability_id"])
    _validate_hints(details["hints"])
    return title


def _validate_capability_id(value: object) -> None:
    if not isinstance(value, str):
        raise McpInteractionProjectionError(
            "MCP interaction failure capability_id must be a string"
        )
    try:
        CapabilityId.parse(value)
    except DefinitionError as error:
        raise McpInteractionProjectionError(
            "MCP interaction failure capability_id must be a valid capability identity"
        ) from error


def _validate_hints(value: object) -> None:
    if not isinstance(value, tuple):
        raise McpInteractionProjectionError("MCP interaction failure hints must be a tuple")
    keys: list[str] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise McpInteractionProjectionError(
                "MCP interaction failure hints must contain key-value pairs"
            )
        key, hint = item
        if not isinstance(key, str) or not _is_hint(hint):
            raise McpInteractionProjectionError(
                "MCP interaction failure hints must match the canonical immutable shape"
            )
        keys.append(key)
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        raise McpInteractionProjectionError(
            "MCP interaction failure hint keys must be unique and sorted"
        )


def _is_hint(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int | float):
        return True
    return isinstance(value, tuple) and all(_is_hint(item) for item in value)

"""E7.6 canonical interaction-required projection to MCP."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable

import pytest
from mcp_types import ElicitRequest, ElicitRequestFormParams, InputRequiredResult
from mcp_types.methods import serialize_server_result

from agnara.capability import CapabilityDefinition, CapabilityId, Confirmation
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    invoke_result,
)
from agnara.policy import ConfirmationEvidence, ConfirmationVerdict, Principal
from agnara_mcp import McpInteractionProjectionError, project_mcp_interaction_required
from agnara_mcp.protocol import MCP_PROTOCOL_VERSION


def run[T](awaitable: Awaitable[T]) -> T:
    return asyncio.run(awaitable)


def interaction_failure(
    *,
    kind: str = "confirmation",
    title: object = "Confirmation required",
    capability_id: object = "payments.refund",
    hints: object = (),
    extra: bool = False,
) -> Failure:
    details = {
        "kind": kind,
        "title": title,
        "capability_id": capability_id,
        "hints": hints,
    }
    if extra:
        details["private"] = "must-not-cross"
    return Failure(
        FailureCode.INTERACTION_REQUIRED,
        "Confirm this capability invocation before continuing.",
        details,  # ty: ignore[invalid-argument-type]
    )


def test_confirmation_projects_to_exact_official_sdk_wire_shape() -> None:
    result = project_mcp_interaction_required(interaction_failure())

    assert isinstance(result, InputRequiredResult)
    assert result.input_requests is not None
    request = result.input_requests["confirmation"]
    assert isinstance(request, ElicitRequest)
    assert isinstance(request.params, ElicitRequestFormParams)
    expected = {
        "resultType": "input_required",
        "inputRequests": {
            "confirmation": {
                "method": "elicitation/create",
                "params": {
                    "mode": "form",
                    "message": (
                        "Confirmation required\n\n"
                        "Confirm this capability invocation before continuing."
                    ),
                    "requestedSchema": {
                        "type": "object",
                        "properties": {
                            "confirmed": {
                                "type": "boolean",
                                "title": "Confirm",
                                "description": "Confirm the requested operation.",
                            }
                        },
                        "required": ["confirmed"],
                    },
                },
            }
        },
    }
    document = result.model_dump(by_alias=True, exclude_none=True)
    assert document == expected
    assert serialize_server_result("tools/call", MCP_PROTOCOL_VERSION, document) == expected


def test_projection_omits_capability_identity_hints_and_private_details() -> None:
    failure = interaction_failure(hints=(("secret", "credential-value"),))
    document = json.dumps(
        project_mcp_interaction_required(failure).model_dump(
            by_alias=True,
            exclude_none=True,
        )
    )

    assert "payments.refund" not in document
    assert "secret" not in document
    assert "credential-value" not in document


def test_each_projection_is_detached_and_deterministic() -> None:
    failure = interaction_failure()
    first = project_mcp_interaction_required(failure)
    second = project_mcp_interaction_required(failure)
    assert first == second

    assert first.input_requests is not None
    first_request = first.input_requests["confirmation"]
    assert isinstance(first_request.params, ElicitRequestFormParams)
    first_request.params.requested_schema["properties"]["confirmed"]["type"] = "string"
    third = project_mcp_interaction_required(failure)
    assert third.input_requests is not None
    third_request = third.input_requests["confirmation"]
    assert isinstance(third_request.params, ElicitRequestFormParams)
    assert third_request.params.requested_schema["properties"]["confirmed"]["type"] == "boolean"


class ValidVerifier:
    async def verify(
        self,
        evidence: ConfirmationEvidence,
        *,
        capability_id,
        invocation,
        principal,
    ) -> ConfirmationVerdict:
        return ConfirmationVerdict.VALID


def test_real_runtime_interaction_projects_before_handler_effects() -> None:
    async def inspect() -> None:
        calls = 0

        def refund() -> None:
            nonlocal calls
            calls += 1

        capability_id = CapabilityId("payments", "refund")
        registry = DIRegistry()
        plan = ExecutionPlan.compile(
            CapabilityDefinition(
                id=capability_id,
                handler=refund,
                confirmation=Confirmation.REQUIRED,
            ),
            registry,
            confirmation_verifier=ValidVerifier(),
        )
        outcome = await invoke_result(
            plan,
            ExecutionContext(
                Invocation(capability_id, {}, {}),
                DIContainer(registry),
                principal=Principal("user-123"),
            ),
        )

        assert isinstance(outcome, Failure)
        projected = project_mcp_interaction_required(outcome)
        assert projected.result_type == "input_required"
        assert calls == 0

    run(inspect())


@pytest.mark.parametrize(
    "value, message",
    [
        (object(), "requires Failure"),
        (Failure(FailureCode.FORBIDDEN, "denied"), "interaction_required"),
        (interaction_failure(kind="future-kind"), "unsupported MCP interaction kind"),
        (interaction_failure(title=""), "title"),
        (interaction_failure(capability_id="invalid"), "capability_id"),
        (interaction_failure(hints="invalid"), "hints"),
        (interaction_failure(hints=(("z", 1), ("a", 2))), "unique and sorted"),
        (interaction_failure(extra=True), "exactly match"),
    ],
)
def test_invalid_or_unsupported_canonical_outcomes_fail_closed(value, message: str) -> None:
    with pytest.raises(McpInteractionProjectionError, match=message):
        project_mcp_interaction_required(value)

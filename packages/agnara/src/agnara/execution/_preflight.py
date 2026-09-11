"""The phase every invocation runs before a handler can produce anything.

Policy evaluation, wire materialization and strict input validation happen in
this order for a complete result and for a stream alike. RFC 0009 constraint 4
requires it of streaming specifically: policy, validation and dependency
construction must complete before a producer emits its first unit, so a stream
cannot become a policy-bypass path.

Keeping the phase here rather than duplicating it in the streaming boundary is
what makes that guarantee checkable: there is one order, not two that are
meant to agree.

Nothing here is public. See ``agnara.execution.runtime`` and
``agnara.execution.streaming``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agnara.errors import (
    InteractionRequiredError,
    PolicyDeniedError,
    ValidationError,
)
from agnara.policy import PolicyFailure, PolicyInteractionRequired, PolicySuccess

if TYPE_CHECKING:
    from agnara.execution.context import ExecutionContext
    from agnara.execution.plan import ExecutionPlan
    from agnara.schema import TypeSchema

__all__: list[str] = []


def tracking_id(context: ExecutionContext) -> str | None:
    """Resolve the operator-facing correlation ID reported to observers.

    Two channels carry this concept. ``ExecutionContext(tracking_id=...)`` is
    an explicit parameter a transport sets deliberately -- ``agnara-mcp`` fills
    it from the JSON-RPC request id -- while ``Invocation.metadata`` is a
    free-form mapping any caller may populate. The explicit parameter wins.

    Only a string is accepted from either source. Metadata is untyped and may
    hold values that must never be exported, so an unusable one is dropped
    rather than stringified into telemetry. This is a correlation label for
    operators, never a pairing key: pair events by ``invocation_id``.
    """
    explicit = context.tracking_id
    if isinstance(explicit, str):
        return explicit
    supplied = context.invocation.metadata.get("tracking_id")
    return supplied if isinstance(supplied, str) else None


async def enforce_policies(plan: ExecutionPlan, context: ExecutionContext) -> None:
    """Evaluate every compiled policy, in declared order, before any effect."""
    for policy in plan.policies:
        result = await policy.evaluate(context)
        if isinstance(result, PolicySuccess):
            continue
        if isinstance(result, PolicyFailure):
            raise PolicyDeniedError(result.reason)
        if isinstance(result, PolicyInteractionRequired):
            raise InteractionRequiredError(result.request)
        raise TypeError(f"policy returned an invalid result: {type(result).__name__}")


def bind_inputs(
    plan: ExecutionPlan,
    context: ExecutionContext,
    input_materializer: Callable[[TypeSchema, object], object] | None,
) -> dict[str, Any]:
    """Materialize and validate the invocation payload into handler arguments."""
    payload = context.invocation.payload
    if input_materializer is not None:
        payload = materialize_inputs(plan, payload, input_materializer)
    return validate_inputs(plan, payload)


def validate_inputs(plan: ExecutionPlan, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a payload against precompiled schemas without mutating it.

    A runtime-owned parameter -- one bound to a dependency or to the execution
    context -- is not an input, so a payload naming one is "unexpected input"
    like any other undeclared key. It is deliberately not told apart: the
    check runs after policies, and answering differently would let a caller
    who is not even authorized to invoke the capability enumerate the names of
    its dependency and context parameters.
    """
    unexpected = sorted(set(payload).difference(plan.input_schemas))
    if unexpected:
        raise ValidationError("unexpected input", path=(unexpected[0],))

    missing = sorted(plan.required_inputs.difference(payload))
    if missing:
        raise ValidationError("required input is missing", path=(missing[0],))

    arguments: dict[str, Any] = {}
    for name, schema in plan.input_schemas.items():
        if name not in payload:
            continue
        try:
            arguments[name] = schema.validate(payload[name])
        except ValidationError as error:
            raise error.at(name) from error
    return arguments


def materialize_inputs(
    plan: ExecutionPlan,
    payload: dict[str, Any],
    materializer: Callable[[TypeSchema, object], object],
) -> dict[str, Any]:
    """Apply one explicit wire conversion after policy and before validation."""
    materialized: dict[str, Any] = {}
    for name, value in payload.items():
        schema = plan.input_schemas.get(name)
        if schema is None:
            materialized[name] = value
            continue
        try:
            materialized[name] = materializer(schema, value)
        except ValidationError as error:
            raise error.at(name) from error
    return materialized

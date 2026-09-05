"""Regression: a transport-supplied tracking ID must reach an observer.

`ExecutionContext` takes `tracking_id` as an explicit parameter, and
`agnara-mcp` fills it from the JSON-RPC request id, but the runtime built its
lifecycle events from `Invocation.metadata` alone. The two channels were never
connected, so an MCP tool call produced events carrying `None`. See Issue #221.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agnara.capability.definition import CapabilityDefinition
from agnara.capability.identity import CapabilityId
from agnara.core.di import DIContainer, DIRegistry
from agnara.execution.context import ExecutionContext
from agnara.execution.invocation import Invocation
from agnara.execution.plan import ExecutionPlan
from agnara.execution.runtime import invoke
from agnara.execution.telemetry import (
    InvocationStartEvent,
    InvocationTerminalEvent,
    TelemetryHook,
)

CAPABILITY = CapabilityId.parse("tests.tracked_cap")


#: A metadata value whose repr would be informative to an attacker and must
#: therefore never be coerced into a telemetry field.
class _Sensitive:
    def __repr__(self) -> str:  # pragma: no cover - only reached on a failure
        return "SENSITIVE-REPR"

    def __str__(self) -> str:  # pragma: no cover - only reached on a failure
        return "SENSITIVE-STR"


class RecordingHook(TelemetryHook):
    def __init__(self) -> None:
        self.starts: list[InvocationStartEvent] = []
        self.terminals: list[InvocationTerminalEvent] = []

    def on_invocation_start(self, event: InvocationStartEvent) -> None:
        self.starts.append(event)

    def on_invocation_terminal(self, event: InvocationTerminalEvent) -> None:
        self.terminals.append(event)


def observed(
    *,
    metadata: dict[str, Any] | None = None,
    tracking_id: str | None = None,
) -> tuple[Any, Any]:
    """Invoke once and return the tracking ID seen on both events."""
    registry = DIRegistry()
    hook = RecordingHook()
    definition = CapabilityDefinition.declare(id=CAPABILITY, handler=lambda: "ok")
    plan = ExecutionPlan.compile(definition, registry, hooks=[hook])
    context = ExecutionContext(
        Invocation(
            capability_id=plan.definition.id,
            payload={},
            metadata=dict(metadata or {}),
        ),
        DIContainer(registry),
        tracking_id=tracking_id,
    )

    asyncio.run(invoke(plan, context))

    return hook.starts[0].tracking_id, hook.terminals[0].tracking_id


def test_an_explicit_context_tracking_id_reaches_both_events() -> None:
    """The defect: this channel was silently dropped."""
    assert observed(tracking_id="req-7", metadata={"transport": "mcp"}) == ("req-7", "req-7")


def test_a_metadata_tracking_id_still_reaches_both_events() -> None:
    """ADR 0023's original source must keep working."""
    assert observed(metadata={"tracking_id": "from-metadata"}) == (
        "from-metadata",
        "from-metadata",
    )


def test_the_explicit_parameter_wins_over_metadata() -> None:
    """A transport sets the parameter deliberately; metadata is free-form."""
    assert observed(
        tracking_id="explicit",
        metadata={"tracking_id": "from-metadata"},
    ) == ("explicit", "explicit")


def test_no_tracking_id_from_either_channel_stays_none() -> None:
    assert observed() == (None, None)


@pytest.mark.parametrize(
    "supplied",
    [17, 1.5, True, None, ["req-7"], {"id": "req-7"}, object(), _Sensitive()],
)
def test_an_unusable_metadata_value_is_dropped_rather_than_stringified(supplied: Any) -> None:
    """Metadata is untyped and may hold values that must not be exported.

    Coercing one would both mistype the event field and leak whatever its
    ``str`` or ``repr`` happens to reveal.
    """
    start, terminal = observed(metadata={"tracking_id": supplied})

    assert start is None
    assert terminal is None


def test_a_tracking_id_set_after_construction_is_read_at_invocation() -> None:
    """Handlers and policies may attach it later; the runtime reads it late."""
    registry = DIRegistry()
    hook = RecordingHook()
    definition = CapabilityDefinition.declare(id=CAPABILITY, handler=lambda: "ok")
    plan = ExecutionPlan.compile(definition, registry, hooks=[hook])
    context = ExecutionContext(
        Invocation(capability_id=plan.definition.id, payload={}, metadata={}),
        DIContainer(registry),
    )
    context.tracking_id = "attached-later"

    asyncio.run(invoke(plan, context))

    assert hook.starts[0].tracking_id == "attached-later"


def test_a_repeated_tracking_id_does_not_merge_invocation_identities() -> None:
    """Fixing the label must not make it look like a pairing key."""
    registry = DIRegistry()
    hook = RecordingHook()
    definition = CapabilityDefinition.declare(id=CAPABILITY, handler=lambda: "ok")
    plan = ExecutionPlan.compile(definition, registry, hooks=[hook])

    async def run() -> None:
        for _ in range(3):
            context = ExecutionContext(
                Invocation(capability_id=plan.definition.id, payload={}, metadata={}),
                DIContainer(registry),
                tracking_id="shared",
            )
            await invoke(plan, context)

    asyncio.run(run())

    assert [event.tracking_id for event in hook.starts] == ["shared"] * 3
    assert len({event.invocation_id for event in hook.starts}) == 3

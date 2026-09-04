"""E7.7 Task and multi-round-trip boundary recorded by ADR 0042."""

from __future__ import annotations

from pathlib import Path

from mcp_types.methods import (
    CLIENT_REQUESTS,
    INPUT_REQUIRED_METHODS,
    MONOLITH_NOTIFICATIONS,
    MONOLITH_REQUESTS,
)

import agnara_mcp
from agnara import Agnara
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_mcp import MCP_PROTOCOL_VERSION, Mcp, project_mcp_tools

PACKAGE_SOURCE = Path(agnara_mcp.__file__).parent


def test_the_pinned_sdk_never_dispatches_the_tasks_extension() -> None:
    """The ADR 0042 premise: task methods are types only in `mcp` 2.1.1."""
    assert [method for method, _ in CLIENT_REQUESTS if method.startswith("tasks/")] == []
    assert [method for method in MONOLITH_REQUESTS if method.startswith("tasks/")] == []
    assert [method for method in MONOLITH_NOTIFICATIONS if "tasks" in method] == []


def test_the_pinned_revision_closes_the_multi_round_trip_carrier_set() -> None:
    assert frozenset({"tools/call", "prompts/get", "resources/read"}) == INPUT_REQUIRED_METHODS
    assert MCP_PROTOCOL_VERSION == "2026-07-28"


def test_projected_tools_never_claim_task_augmented_execution() -> None:
    app = Agnara("math")

    @app.capability(description="Add two integers")
    def add(left: int, right: int) -> int:
        return left + right

    mcp = Mcp(app)
    mcp.tool(add)
    plan = ExecutionPlan.compile(app.capabilities["math.add"], DIRegistry())
    projected = project_mcp_tools(mcp.compile(), [plan])

    assert [definition.execution for definition in projected] == [None]
    for definition in projected:
        assert "execution" not in definition.model_dump(by_alias=True, exclude_none=True)


def test_the_adapter_publishes_no_resumption_or_request_state_surface() -> None:
    """Nothing in this package mints, seals or accepts `requestState` yet."""
    exported = set(agnara_mcp.__all__)
    assert not {name for name in exported if "task" in name.lower()}
    assert not {name for name in exported if "resume" in name.lower()}
    assert not {name for name in exported if "state" in name.lower()}

    sources = sorted(PACKAGE_SOURCE.glob("*.py"))
    assert sources
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert "requestState" not in text
        assert "request_state" not in text
        assert "RequestStateSecurity" not in text
        assert "RequestStateBoundary" not in text

"""Serve one MCP ``tools/call`` from a compiled Agnara capability plan.

Everything reflective happens at construction: exposures are paired with their
compiled plans, declared scopes become one core ``ScopePolicy`` per tool, and
the resulting route table is immutable. Dispatch does a mapping lookup, one
authorization evaluation, one core invocation and one result projection.

The dispatcher owns no protocol semantics of its own. It never validates
inputs, never formats a value and never decides a failure category: core
returns a canonical outcome and ``project_mcp_result`` maps it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp_types import INVALID_PARAMS, CallToolRequestParams, CallToolResult, InputRequiredResult

from agnara import DefinitionError
from agnara.core.di import DIContainer
from agnara.execution import (
    CanonicalResult,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    invoke_result,
)
from agnara.policy import AnonymousPrincipal, PolicyFailure, Principal, ScopePolicy
from mcp import MCPError

from .authorization import McpAuthorization
from .discovery import _build_server
from .result import McpResultProjectionError, project_mcp_result
from .schema import _resolve_plans, project_mcp_tools
from .tools import FrozenMcpTools

__all__ = ["McpInvocationDefinitionError", "McpToolInvoker", "build_mcp_server"]

#: Longest client request id copied into invocation telemetry. A request id is
#: caller-controlled, so an unbounded one must not reach every telemetry sink.
_MAX_TRACKING_ID = 128

#: Core's message for an input that no compiled schema declares. Reused so a
#: runtime-owned parameter is indistinguishable from an unknown one, and the
#: names of dependency and context parameters stay unpublished.
_UNEXPECTED_INPUT = "unexpected input"


class McpInvocationDefinitionError(DefinitionError):
    """An MCP invocation surface is configured inconsistently."""


@dataclass(frozen=True, slots=True)
class _InvocationRoute:
    """One tool name resolved to everything dispatch needs, compiled once."""

    plan: ExecutionPlan
    scopes: ScopePolicy


def _timeout_seconds(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise McpInvocationDefinitionError(
            "MCP invocation timeout must be a positive number of seconds or None"
        )
    return float(value)


def _tracking_id(request_id: object) -> str | None:
    if isinstance(request_id, bool) or not isinstance(request_id, int | str):
        return None
    rendered = str(request_id)
    return rendered if len(rendered) <= _MAX_TRACKING_ID else None


def _project(outcome: CanonicalResult[object]) -> CallToolResult | InputRequiredResult:
    """Project a canonical outcome, degrading a projection defect to a tool error.

    A capability that returns data MCP cannot represent is a server-side
    defect, not a protocol error, and the caller must still receive a result
    that says so without echoing the offending value.
    """
    try:
        return project_mcp_result(outcome)
    except McpResultProjectionError:
        return project_mcp_result(
            Failure(FailureCode.INTERNAL_FAILURE, "capability result cannot be represented")
        )


class McpToolInvoker:
    """Dispatch ``tools/call`` to compiled plans behind one immutable table.

    Declared capability scopes are enforced here with the same core policy the
    runtime applies, because ``scopes`` metadata authorizes nothing on its own
    (ADR 0008) and discovery filtering is visibility rather than authorization.
    A capability that also attaches its own policies keeps them: this guard
    runs first and never replaces core policy evaluation.

    The invoker holds no per-request state. One instance serves every
    concurrent request on a connection, and each request builds its own
    invocation, context and dependency scope over the shared container.
    """

    __slots__ = ("_authorization", "_container", "_routes", "_timeout")

    def __init__(
        self,
        exposures: FrozenMcpTools,
        plans: Iterable[ExecutionPlan],
        di_container: DIContainer,
        *,
        authorization: McpAuthorization | None = None,
        timeout: float | None = None,
    ) -> None:
        if not isinstance(di_container, DIContainer):
            raise TypeError(
                f"di_container must be a DIContainer, got {type(di_container).__name__}"
            )
        if authorization is not None and not isinstance(authorization, McpAuthorization):
            raise TypeError(
                "authorization must be McpAuthorization or None, got "
                f"{type(authorization).__name__}"
            )
        routes = {
            exposure.name: _InvocationRoute(plan, ScopePolicy(exposure.definition.scopes))
            for exposure, plan in _resolve_plans(exposures, plans)
        }
        if authorization is not None and tuple(routes) != authorization.tool_names:
            raise McpInvocationDefinitionError(
                "MCP invocation exposures must exactly match the authorized tool names "
                f"in declaration order: exposures={tuple(routes)!r}, "
                f"authorized={authorization.tool_names!r}"
            )
        self._routes = MappingProxyType(routes)
        self._container = di_container
        self._authorization = authorization
        self._timeout = _timeout_seconds(timeout)

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Invocable tool names in deterministic declaration order."""
        return tuple(self._routes)

    async def __call__(
        self,
        ctx: ServerRequestContext[Any],
        params: CallToolRequestParams,
    ) -> CallToolResult | InputRequiredResult:
        """Answer one tool call, or raise ``MCPError`` when there is no call to make.

        Cancellation is never converted into a result: an abandoned request
        propagates so the SDK can drop it and core can unwind dependency
        cleanup.
        """
        route = self._route(params)
        context = ExecutionContext(
            Invocation(
                capability_id=route.plan.definition.id,
                payload=dict(params.arguments or {}),
                metadata={"transport": "mcp", "tool": params.name},
                deadline=self._deadline(),
            ),
            self._container,
            tracking_id=_tracking_id(ctx.request_id),
            principal=self._principal(),
        )
        denial = await self._denied(route, context)
        if denial is not None:
            return _project(denial)
        if route.plan.protected_parameters.intersection(context.invocation.payload):
            return _project(Failure(FailureCode.INVALID_INPUT, _UNEXPECTED_INPUT))
        return _project(await invoke_result(route.plan, context))

    def _route(self, params: CallToolRequestParams) -> _InvocationRoute:
        """Resolve the requested tool, rejecting surfaces this server does not serve."""
        if not isinstance(params, CallToolRequestParams):
            raise MCPError(code=INVALID_PARAMS, message="Invalid tools/call params")
        if params.task is not None:
            raise MCPError(
                code=INVALID_PARAMS,
                message="Task-augmented tool execution is not supported",
            )
        if params.input_responses is not None or params.request_state is not None:
            # ADR 0042: no resumption path exists, so accepting echoed state
            # would be accepting unverified confirmation evidence.
            raise MCPError(
                code=INVALID_PARAMS,
                message="Resuming a tool call is not supported",
            )
        route = self._routes.get(params.name)
        if route is None:
            raise MCPError(code=INVALID_PARAMS, message="Unknown tool", data=params.name)
        return route

    def _principal(self) -> Principal:
        if self._authorization is None:
            return AnonymousPrincipal(metadata={"transport": "mcp"})
        return self._authorization.principal()

    async def _denied(self, route: _InvocationRoute, context: ExecutionContext) -> Failure | None:
        """Evaluate declared scopes before any dependency or handler effect."""
        result = await route.scopes.evaluate(context)
        if isinstance(result, PolicyFailure):
            return Failure(FailureCode.FORBIDDEN, result.reason)
        return None

    def _deadline(self) -> float | None:
        if self._timeout is None:
            return None
        return asyncio.get_running_loop().time() + self._timeout

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self._routes)} tools)"


def build_mcp_server(
    exposures: FrozenMcpTools,
    plans: Iterable[ExecutionPlan],
    di_container: DIContainer,
    *,
    name: str,
    version: str,
    instructions: str | None = None,
    authorization: McpAuthorization | None = None,
    timeout: float | None = None,
) -> Server[Any]:
    """Build an official SDK server that both discovers and invokes tools.

    Discovery keeps the contract ``build_mcp_discovery_server`` established:
    one frozen startup snapshot, private zero-TTL results, no pagination and
    no list-changed notifications. Invocation is added over the same snapshot,
    so a name can never be discoverable through one surface and unknown to the
    other.
    """
    materialized = tuple(plans)
    invoker = McpToolInvoker(
        exposures,
        materialized,
        di_container,
        authorization=authorization,
        timeout=timeout,
    )
    return _build_server(
        project_mcp_tools(exposures, materialized),
        name=name,
        version=version,
        instructions=instructions,
        authorization=authorization,
        on_call_tool=invoker,
    )

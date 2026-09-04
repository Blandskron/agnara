"""Deterministic MCP tool exposure declarations for Agnara capabilities."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from agnara import Agnara, CapabilityDefinition, DefinitionError, UnknownCapabilityError

__all__ = [
    "FrozenMcpTools",
    "Mcp",
    "McpToolDefinitionError",
    "McpToolExposure",
]

_TOOL_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class McpToolDefinitionError(DefinitionError):
    """An MCP tool exposure is invalid or ambiguous."""


def _validate_name(name: object) -> str:
    if not isinstance(name, str):
        raise McpToolDefinitionError(f"MCP tool name must be a string, got {type(name).__name__}")
    if _TOOL_NAME.fullmatch(name) is None:
        raise McpToolDefinitionError(
            "MCP tool name must contain 1 to 128 ASCII letters, digits, dots, "
            f"hyphens, or underscores: {name!r}"
        )
    return name


@dataclass(frozen=True, slots=True)
class McpToolExposure:
    """One validated MCP name attached to a protocol-neutral capability."""

    name: str
    definition: CapabilityDefinition

    def __post_init__(self) -> None:
        _validate_name(self.name)
        if not isinstance(self.definition, CapabilityDefinition):
            raise McpToolDefinitionError(
                "MCP tool definition must be a CapabilityDefinition, got "
                f"{type(self.definition).__name__}"
            )


class FrozenMcpTools(Mapping[str, McpToolExposure]):
    """Immutable, registration-ordered MCP tool exposure snapshot."""

    __slots__ = ("_by_name", "_ordered")

    def __init__(self, exposures: tuple[McpToolExposure, ...]) -> None:
        self._ordered = exposures
        self._by_name = MappingProxyType({exposure.name: exposure for exposure in exposures})

    def __getitem__(self, name: str) -> McpToolExposure:
        return self._by_name[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_name)

    def __len__(self) -> int:
        return len(self._ordered)

    @property
    def exposures(self) -> tuple[McpToolExposure, ...]:
        """Exposures in deterministic registration order."""
        return self._ordered

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self)} tools)"


class Mcp:
    """Declare MCP tool exposures for capabilities owned by one application."""

    __slots__ = ("_app", "_by_name", "_frozen", "_lock", "_snapshot")

    def __init__(self, app: Agnara) -> None:
        if not isinstance(app, Agnara):
            raise TypeError(f"app must be an Agnara application, got {type(app).__name__}")
        self._app = app
        self._by_name: dict[str, McpToolExposure] = {}
        self._frozen = False
        self._lock = threading.Lock()
        self._snapshot: FrozenMcpTools | None = None

    @property
    def is_compiled(self) -> bool:
        """Whether tool registration has been closed."""
        return self._frozen

    def tool(
        self,
        capability: CapabilityDefinition | Callable[..., Any],
        /,
        *,
        name: str | None = None,
    ) -> McpToolExposure:
        """Expose one declared capability as an MCP tool.

        The callable form matches the golden API: ``mcp.tool(get_user)``.
        Passing a definition is also supported for composition code that
        already resolved the capability registry.
        """
        definition = self._resolve(capability)
        tool_name = _validate_name(str(definition.id) if name is None else name)
        exposure = McpToolExposure(tool_name, definition)
        with self._lock:
            if self._frozen:
                raise McpToolDefinitionError(
                    f"cannot register MCP tool {tool_name!r} after MCP compilation"
                )
            existing = self._by_name.get(tool_name)
            if existing is not None:
                raise McpToolDefinitionError(
                    f"MCP tool name {tool_name!r} already exposes {existing.definition.id}"
                )
            self._by_name[tool_name] = exposure
        return exposure

    def compile(self) -> FrozenMcpTools:
        """Close registration and return an idempotently reusable snapshot."""
        with self._lock:
            if self._snapshot is None:
                self._snapshot = FrozenMcpTools(tuple(self._by_name.values()))
                self._frozen = True
            return self._snapshot

    def _resolve(
        self, capability: CapabilityDefinition | Callable[..., Any]
    ) -> CapabilityDefinition:
        if isinstance(capability, CapabilityDefinition):
            try:
                registered = self._app.capabilities[capability.id]
            except UnknownCapabilityError:
                registered = None
            if registered is not capability:
                raise McpToolDefinitionError(
                    f"capability {capability.id} is not declared on application {self._app.name!r}"
                )
            return capability
        if not callable(capability):
            raise McpToolDefinitionError(
                "mcp.tool expects a declared capability callable or CapabilityDefinition, got "
                f"{type(capability).__name__}"
            )
        matches = tuple(
            definition
            for capability_id in self._app.capabilities
            if (definition := self._app.capabilities[capability_id]).handler is capability
        )
        if not matches:
            raise McpToolDefinitionError(
                f"callable {getattr(capability, '__name__', repr(capability))!r} is not declared "
                f"on application {self._app.name!r}"
            )
        if len(matches) > 1:
            ids = ", ".join(str(definition.id) for definition in matches)
            raise McpToolDefinitionError(
                f"callable is declared as multiple capabilities ({ids}); pass a "
                "CapabilityDefinition to select one explicitly"
            )
        return matches[0]

    def __len__(self) -> int:
        return len(self._by_name)

    def __repr__(self) -> str:
        state = "compiled" if self._frozen else "open"
        return f"Mcp({self._app.name!r}, {len(self)} tools, {state})"

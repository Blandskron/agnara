"""Fail-closed bridge from verified MCP authentication to Agnara principals."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, principal_components
from mcp_types import INTERNAL_ERROR, Tool

from agnara import DefinitionError
from agnara.policy import AnonymousPrincipal, Principal
from mcp import MCPError

from .tools import FrozenMcpTools

__all__ = [
    "McpAuthenticatedIdentity",
    "McpAuthorization",
    "McpAuthorizationDefinitionError",
    "McpPrincipalMapper",
]


class McpAuthorizationDefinitionError(DefinitionError):
    """MCP authorization configuration is invalid or inconsistent."""


@dataclass(frozen=True, slots=True)
class McpAuthenticatedIdentity:
    """Credential-free identity facts emitted by the configured token verifier."""

    client_id: str
    issuer: str | None
    subject: str | None
    resource: str | None
    scopes: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.client_id, str) or not self.client_id.strip():
            raise McpAuthorizationDefinitionError("MCP authenticated client_id must not be empty")
        for field_name in ("issuer", "subject", "resource"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise McpAuthorizationDefinitionError(
                    f"MCP authenticated {field_name} must be a string or None"
                )
        if not isinstance(self.scopes, frozenset):
            raise McpAuthorizationDefinitionError("MCP authenticated scopes must be a frozenset")
        for scope in self.scopes:
            if not isinstance(scope, str) or not scope.strip():
                raise McpAuthorizationDefinitionError(
                    "MCP authenticated scopes must contain non-empty strings"
                )


class McpPrincipalMapper(Protocol):
    """Map sanitized verified MCP identity facts to application identity semantics."""

    def __call__(self, identity: McpAuthenticatedIdentity, /) -> Principal: ...


def _identity_from_token(token: AccessToken) -> McpAuthenticatedIdentity:
    client_id, issuer, subject = principal_components(token)
    return McpAuthenticatedIdentity(
        client_id=client_id,
        issuer=issuer,
        subject=subject,
        resource=token.resource,
        scopes=frozenset(token.scopes),
    )


class McpAuthorization:
    """Resolve one request principal and scope-filter one frozen exposure set.

    The mapper is a trusted application boundary and may choose how client,
    issuer, and subject facts define the core principal. It is invoked for
    every authenticated request; this object keeps no principal or token cache.
    """

    __slots__ = ("_mapper", "_required_scopes", "_tool_names")

    def __init__(
        self,
        exposures: FrozenMcpTools,
        mapper: McpPrincipalMapper,
    ) -> None:
        if not isinstance(exposures, FrozenMcpTools):
            raise TypeError(f"exposures must be FrozenMcpTools, got {type(exposures).__name__}")
        if not isinstance(mapper, Callable):
            raise McpAuthorizationDefinitionError("MCP principal mapper must be callable")
        required_scopes = {
            exposure.name: exposure.definition.scopes for exposure in exposures.exposures
        }
        self._mapper = mapper
        self._required_scopes = MappingProxyType(required_scopes)
        self._tool_names = tuple(required_scopes)

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Authorized exposure names in deterministic declaration order."""
        return self._tool_names

    def principal(self) -> Principal:
        """Resolve the active request's verified token into a neutral principal."""
        token = get_access_token()
        if token is None:
            return AnonymousPrincipal(metadata={"transport": "mcp"})
        try:
            identity = _identity_from_token(token)
            principal = self._mapper(identity)
            if not isinstance(principal, Principal) or isinstance(principal, AnonymousPrincipal):
                raise TypeError("authenticated MCP mapper must return a non-anonymous Principal")
            if not isinstance(principal.identity, str) or not principal.identity.strip():
                raise TypeError("authenticated MCP mapper returned an invalid principal identity")
            return principal
        except Exception as error:
            raise MCPError(
                code=INTERNAL_ERROR,
                message="MCP authorization failed",
            ) from error

    def discoverable_tool_names(self) -> frozenset[str]:
        """Return statically scope-visible tool names for the active request."""
        granted = self.principal().scopes
        return frozenset(
            name for name, required in self._required_scopes.items() if required.issubset(granted)
        )

    def _validate_tools(self, tools: tuple[Tool, ...]) -> None:
        projected_names = tuple(tool.name for tool in tools)
        if projected_names != self._tool_names:
            mismatch = f"exposures={self._tool_names!r}, projected={projected_names!r}"
            raise McpAuthorizationDefinitionError(
                "MCP authorization exposures must exactly match projected discovery tools "
                f"in declaration order: {mismatch}"
            )

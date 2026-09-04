"""Dependency-free ASGI boundary for the HTTP adapter.

The module is internal until the HTTP exposure/composition API is reviewed.
It follows the ASGI 3 single-callable shape and recognizes HTTP scopes, plus
lifespan scopes when an application lifecycle is configured. Routing, request
binding, response mapping and WebSockets belong to other adapter modules.

A lifespan scope with no configured dispatcher is refused rather than silently
completed. Raising is how an ASGI application tells a server it has no
lifespan, and a server running `lifespan="auto"` handles that itself.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

type _Scope = dict[str, Any]
type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]
type _Send = Callable[[_Message], Awaitable[None]]
type _HTTPDispatch = Callable[[_Scope, _Receive, _Send], Awaitable[None]]
type _LifespanDispatch = Callable[[_Scope, _Receive, _Send], Awaitable[None]]


class _UnsupportedScopeError(RuntimeError):
    """Raised when an ASGI server offers a protocol this adapter does not support."""


class _ASGIBoundary:
    """ASGI 3 callable that validates and delegates one connection scope."""

    __slots__ = ("_dispatch", "_lifespan")

    def __init__(
        self,
        dispatch: _HTTPDispatch,
        lifespan: _LifespanDispatch | None = None,
    ) -> None:
        if not callable(dispatch):
            raise TypeError(f"dispatch must be callable, got {type(dispatch).__name__}")
        if lifespan is not None and not callable(lifespan):
            raise TypeError(f"lifespan must be callable, got {type(lifespan).__name__}")
        self._dispatch = dispatch
        self._lifespan = lifespan

    async def __call__(
        self,
        scope: _Scope,
        receive: _Receive,
        send: _Send,
    ) -> None:
        if not isinstance(scope, dict):
            raise TypeError(f"ASGI scope must be a dictionary, got {type(scope).__name__}")

        scope_type = scope.get("type")
        if not isinstance(scope_type, str):
            raise TypeError("ASGI scope 'type' must be a string")
        if scope_type == "http":
            handler = self._dispatch
        elif scope_type == "lifespan" and self._lifespan is not None:
            handler = self._lifespan
        else:
            raise _UnsupportedScopeError(f"unsupported ASGI scope type: {scope_type!r}")

        if not callable(receive):
            raise TypeError(f"ASGI receive must be callable, got {type(receive).__name__}")
        if not callable(send):
            raise TypeError(f"ASGI send must be callable, got {type(send).__name__}")

        return await handler(scope, receive, send)

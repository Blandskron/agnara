"""Protocol-neutral errors raised by the Agnara core.

Core errors never carry HTTP status codes, MCP error objects or any other
transport representation. Adapters map these onto their own protocols; see
``AGENTS.md`` "Error discipline" and RFC 0001.
"""

from __future__ import annotations

__all__ = [
    "AgnaraError",
    "DefinitionError",
]


class AgnaraError(Exception):
    """Base class for every error raised by Agnara.

    Applications can catch this to distinguish framework failures from
    their own, without depending on any transport package.
    """


class DefinitionError(AgnaraError):
    """A capability was declared in a way the runtime cannot accept.

    Raised during declaration or startup compilation, never on the
    invocation hot path. ADR 0005 requires these failures to be explicit
    and to happen as early as possible.
    """

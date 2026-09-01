"""Protocol-neutral errors raised by the Agnara core.

Core errors never carry HTTP status codes, MCP error objects or any other
transport representation. Adapters map these onto their own protocols; see
``AGENTS.md`` "Error discipline" and RFC 0001.
"""

from __future__ import annotations

__all__ = [
    "AgnaraError",
    "DefinitionError",
    "DuplicateCapabilityError",
    "RegistryError",
    "RegistryFrozenError",
    "UnknownCapabilityError",
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


class RegistryError(AgnaraError):
    """The capability registry was used in a way its contract forbids."""


class DuplicateCapabilityError(RegistryError):
    """Two capabilities claimed the same identity.

    Capability ids appear in policy rules, audit records and agent-facing
    manifests, so a silent overwrite would make those references ambiguous.
    Registration fails instead.
    """


class RegistryFrozenError(RegistryError):
    """The registry was modified after compilation froze it.

    ADR 0005 freezes the registry at the end of startup compilation so the
    hot path can read it without locking. A late registration would break
    that guarantee, so it is refused.
    """


class UnknownCapabilityError(RegistryError, KeyError):
    """No capability is registered under the requested id.

    Also a `KeyError`, so ordinary mapping-shaped code keeps working.
    """

    def __str__(self) -> str:
        # KeyError.__str__ reprs its argument, which would double-quote the
        # message. Use the plain text instead.
        return self.args[0] if self.args else ""

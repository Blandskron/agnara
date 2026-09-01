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
    "SchemaError",
    "UnknownCapabilityError",
    "ValidationError",
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


class SchemaError(AgnaraError):
    """A schema could not be compiled from a Python annotation.

    Raised during startup compilation, so an unsupported annotation is a
    startup failure rather than a surprise on the first invocation
    (ADR 0005).
    """


class ValidationError(AgnaraError):
    """A value did not satisfy its compiled schema.

    Protocol-neutral by construction: no status code, no HTTP problem
    document, no JSON-RPC error object. Adapters map this onto their own
    protocol, which is what lets one capability report the same failure
    consistently over HTTP, MCP and a direct call.

    ``path`` locates the offending value inside a nested structure, as a
    sequence of field names and indices. It is empty when the top-level
    value itself is wrong.
    """

    def __init__(self, message: str, *, path: tuple[str | int, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.path = path

    def at(self, segment: str | int) -> ValidationError:
        """Return the same failure, reported one level further out.

        A nested validator raises against the value it was handed; the
        caller knows which field or index that value came from and pushes
        that segment on as the error travels outward.
        """
        return ValidationError(self.message, path=(segment, *self.path))

    @property
    def location(self) -> str:
        """The path rendered for humans, or ``<value>`` at the top level."""
        if not self.path:
            return "<value>"
        rendered = ""
        for segment in self.path:
            if isinstance(segment, int):
                rendered += f"[{segment}]"
            else:
                rendered += f".{segment}" if rendered else segment
        return rendered

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"

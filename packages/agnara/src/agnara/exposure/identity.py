"""Neutral identity for one protocol exposure of one capability.

An exposure is identified by three parts (RFC 0006 section 7)::

    adapter kind + surface name + adapter-local name

``adapter`` says which protocol reaches the capability. ``name`` on the
surface distinguishes two deployments of the same protocol — a public HTTP
API and an admin one, or a customer-facing MCP server and an internal one.
The adapter-local name is opaque to the kernel: HTTP uses a method and path,
MCP uses its tool-name grammar, and the kernel learns neither.

The kernel validates only what it owns: that the adapter and surface
identifiers are well formed, and that a full identity is unique in a compiled
project. Parsing an HTTP path or applying MCP naming rules here would make the
kernel understand every present and future protocol, which is exactly the
coupling ADR 0003 forbids.
"""

from __future__ import annotations

from typing import Final

from agnara._frozen import frozen_slots_dataclass
from agnara.errors import DefinitionError

#: Longest adapter-local name the kernel will carry. Adapters validate the
#: grammar; this is only a bound on what an unbounded caller can push into a
#: frozen registry, a diagnostic message and an introspection document.
_MAX_LOCAL_NAME: Final = 512


class ExposureError(DefinitionError):
    """An exposure declaration or compiled exposure set is invalid.

    A `DefinitionError`, because it is a startup-compilation failure like
    every other declaration mistake, and never something an invocation can
    raise (ADR 0005).
    """


def _identifier(value: object, *, field: str) -> str:
    """Validate one kernel-owned identifier: lowercase, ASCII, dot-free."""
    if not isinstance(value, str):
        raise ExposureError(f"exposure {field} must be a string, got {type(value).__name__}")
    if not value:
        raise ExposureError(f"exposure {field} must not be empty")
    if not value.isascii() or not value.replace("_", "a").replace("-", "a").isalnum():
        raise ExposureError(
            f"invalid exposure {field} {value!r}: use ASCII letters, digits, "
            "hyphens and underscores"
        )
    if value != value.lower():
        raise ExposureError(
            f"invalid exposure {field} {value!r}: identifiers are lowercase, so two "
            "spellings of one surface cannot both exist"
        )
    if not value[0].isalpha():
        raise ExposureError(f"invalid exposure {field} {value!r}: must start with a letter")
    return value


@frozen_slots_dataclass
class SurfaceId:
    """One named runtime surface of one protocol adapter.

    ``adapter`` is the stable lowercase kind — ``http``, ``mcp`` — and is the
    value that reaches introspection as the exposure's transport. ``name`` is
    project-local, so ``SurfaceId("http", "public")`` and
    ``SurfaceId("http", "admin")`` are two surfaces whose exposures may reuse
    adapter-local names without colliding.
    """

    adapter: str
    name: str

    def __post_init__(self) -> None:
        _identifier(self.adapter, field="adapter")
        _identifier(self.name, field="surface name")

    def __str__(self) -> str:
        return f"{self.adapter}:{self.name}"


@frozen_slots_dataclass
class ExposureId:
    """The full identity of one reachable adapter target.

    A dedicated value rather than the structural key of a compiled record,
    so a duplicate can be *named* in a diagnostic before its record exists,
    and so a lookup does not require constructing the thing being looked up.
    """

    surface: SurfaceId
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.surface, SurfaceId):
            raise ExposureError(
                f"exposure surface must be a SurfaceId, got {type(self.surface).__name__}"
            )
        if not isinstance(self.name, str) or not self.name:
            raise ExposureError("exposure name must be a non-empty string")
        if len(self.name) > _MAX_LOCAL_NAME:
            raise ExposureError(
                f"exposure name is longer than {_MAX_LOCAL_NAME} characters: {self.name[:40]!r}..."
            )
        if not self.name.isprintable():
            raise ExposureError(
                f"invalid exposure name {self.name!r}: control characters would corrupt "
                "diagnostics and published documents"
            )

    @property
    def adapter(self) -> str:
        """The protocol kind this exposure belongs to."""
        return self.surface.adapter

    def __str__(self) -> str:
        return f"{self.surface} {self.name}"

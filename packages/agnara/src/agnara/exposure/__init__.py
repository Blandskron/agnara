"""One exposure model for every protocol adapter.

Before this package, each adapter answered "which surfaces reach this
capability?" its own way: `agnara-http` compiled a private route registry,
`agnara-mcp` froze an independent tool table, and introspection was handed a
third answer written by hand. A third adapter would have invented a fourth.

The model has two layers (RFC 0006):

1. an adapter owns typed declaration, protocol validation and its runtime
   artifact -- a route table, a tool table -- and the kernel never names one;
2. the same adapter compilation emits immutable neutral records, which the
   project aggregates into one frozen availability registry.

The kernel therefore knows *that* a capability is reachable through a named
adapter surface, and never *how*. It parses no path, applies no tool grammar,
and imports no adapter (ADR 0003).

Declaration belongs to project composition, not to the capability and not to
the app. A capability says what an operation means; an `App` says which
bounded context owns it; the composition root says which deployment surfaces
expose it. That is what lets one app run unchanged in an internal worker, a
public service and an agent-facing service.

    surface = SurfaceId("http", "public")
    compilation = SurfaceCompilation(surface, route_table, records)
    exposures = compile_exposures(app.compile(), [compilation])

Availability is not authorization. Presence in the registry does not permit
an invocation, and hiding an exposure from one viewer does not disable it;
RFC 0006 section 12 keeps availability, discovery, publication and
authorization separate on purpose.
"""

from .compiled import CompiledExposure, SurfaceCompilation
from .identity import ExposureError, ExposureId, SurfaceId
from .registry import FrozenExposureRegistry, compile_exposures

__all__ = [
    "CompiledExposure",
    "ExposureError",
    "ExposureId",
    "FrozenExposureRegistry",
    "SurfaceCompilation",
    "SurfaceId",
    "compile_exposures",
]

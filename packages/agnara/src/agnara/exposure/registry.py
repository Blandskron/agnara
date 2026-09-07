"""One frozen, project-wide answer to where a capability is reachable.

`compile_exposures` is the aggregation step of the startup lifecycle
(RFC 0006 section 10): every selected adapter surface has already compiled,
and the project now validates the cross-adapter rules and freezes one
registry.

There is no open collecting registry on purpose. Aggregation takes the
complete set of surface compilations and returns the frozen result, so no
caller can observe a half-populated view and no code path can register an
exposure after the freeze -- the failure mode ADR 0005 exists to prevent is
structurally absent rather than guarded by a flag.

The registry is availability truth and nothing else. Presence here does not
authorize an invocation and does not make an exposure discoverable to a
particular viewer; those are the policy engine and `filter_snapshot`, and
RFC 0006 section 12 keeps the four facts separate.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType
from typing import Any

from agnara.capability.identity import CapabilityId
from agnara.capability.registry import FrozenCapabilityRegistry
from agnara.exposure.compiled import CompiledExposure, SurfaceCompilation
from agnara.exposure.identity import ExposureError, ExposureId, SurfaceId


class FrozenExposureRegistry(Mapping[ExposureId, CompiledExposure]):
    """Every compiled exposure of one project, immutable and ordered.

    Iteration order is the order the surfaces were aggregated in, and within
    a surface the order its compiler emitted. Determinism is part of the
    contract: introspection documents, OpenAPI projections and MCP tool lists
    are derived from it and must not reshuffle between runs.

    Holds no mutable state and no adapter artifact, so concurrent readers
    need no synchronization (PRINCIPLES.md P6).
    """

    __slots__ = ("_by_capability", "_exposures", "_surfaces")

    def __init__(self, exposures: Iterable[CompiledExposure] = ()) -> None:
        indexed: dict[ExposureId, CompiledExposure] = {}
        by_capability: dict[CapabilityId, list[CompiledExposure]] = {}
        surfaces: list[SurfaceId] = []
        for exposure in exposures:
            if not isinstance(exposure, CompiledExposure):
                raise ExposureError(
                    "exposure registry accepts only CompiledExposure values, got "
                    f"{type(exposure).__name__}"
                )
            existing = indexed.get(exposure.id)
            if existing is not None:
                raise ExposureError(
                    f"duplicate exposure {exposure.id}: already reaches {existing.capability_id}"
                )
            indexed[exposure.id] = exposure
            by_capability.setdefault(exposure.capability_id, []).append(exposure)
            if exposure.surface not in surfaces:
                surfaces.append(exposure.surface)
        self._exposures: Mapping[ExposureId, CompiledExposure] = MappingProxyType(indexed)
        self._by_capability: Mapping[CapabilityId, tuple[CompiledExposure, ...]] = MappingProxyType(
            {capability_id: tuple(items) for capability_id, items in by_capability.items()}
        )
        self._surfaces = tuple(surfaces)

    def __getitem__(self, key: ExposureId) -> CompiledExposure:
        try:
            return self._exposures[key]
        except KeyError:
            raise ExposureError(f"no exposure compiled as {key}") from None

    def __iter__(self) -> Iterator[ExposureId]:
        return iter(self._exposures)

    def __len__(self) -> int:
        return len(self._exposures)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self)} exposures across {len(self._surfaces)} surfaces)"

    @property
    def surfaces(self) -> tuple[SurfaceId, ...]:
        """Every surface contributing at least one exposure, in order."""
        return self._surfaces

    def for_capability(self, capability_id: CapabilityId) -> tuple[CompiledExposure, ...]:
        """Every compiled exposure of one capability, in aggregation order.

        Empty for a capability the project declared but exposed nowhere,
        which is an ordinary state: a capability reachable only by direct
        Python invocation is still a capability.
        """
        return self._by_capability.get(capability_id, ())

    def on_surface(self, surface: SurfaceId) -> tuple[CompiledExposure, ...]:
        """Every compiled exposure of one surface, in the order it emitted."""
        return tuple(
            exposure for exposure in self._exposures.values() if exposure.surface == surface
        )

    def transports(self, capability_id: CapabilityId) -> tuple[str, ...]:
        """The distinct adapter kinds one capability is reachable through."""
        seen: list[str] = []
        for exposure in self.for_capability(capability_id):
            if exposure.id.adapter not in seen:
                seen.append(exposure.id.adapter)
        return tuple(seen)


def compile_exposures(
    capabilities: FrozenCapabilityRegistry,
    compilations: Iterable[SurfaceCompilation[Any]] = (),
) -> FrozenExposureRegistry:
    """Aggregate compiled adapter surfaces into one frozen exposure registry.

    Validates only what the kernel owns (RFC 0006 section 11): that each
    record names a capability this project actually compiled, that no two
    surfaces claim one identity, that a compiler contributed records only for
    its own surface, and that the result is deterministic. Method grammar,
    route ambiguity and tool-name rules stay with the adapter that
    understands them.

    Args:
        capabilities: the frozen capability registry returned by
            `Agnara.compile`. Membership is checked against it, so an
            exposure cannot advertise a capability the project does not have.
        compilations: one `SurfaceCompilation` per selected adapter surface.
            The runtime artifact is `Any` because the kernel never reads it:
            a compilation is generic and invariant in that parameter, so
            naming a bound here would reject every adapter's own type.

    Returns:
        The frozen registry. Aggregating the same compilations again produces
        an equivalent registry, so a composition root need not track whether
        this already ran.

    Raises:
        ExposureError: a record names an unknown capability, two surfaces
            share an identity, a surface is compiled twice, or a compilation
            is malformed.
    """
    if not isinstance(capabilities, FrozenCapabilityRegistry):
        raise ExposureError(
            "exposure aggregation needs the frozen capability registry, got "
            f"{type(capabilities).__name__}"
        )
    collected: list[CompiledExposure] = []
    seen_surfaces: list[SurfaceId] = []
    for compilation in compilations:
        if not isinstance(compilation, SurfaceCompilation):
            raise ExposureError(
                "exposure aggregation accepts only SurfaceCompilation values, got "
                f"{type(compilation).__name__}"
            )
        if compilation.surface in seen_surfaces:
            raise ExposureError(
                f"surface {compilation.surface} was compiled twice; a surface name is "
                "project-local and identifies one deployment of one adapter"
            )
        seen_surfaces.append(compilation.surface)
        for exposure in compilation.exposures:
            if exposure.capability_id not in capabilities:
                raise ExposureError(
                    f"exposure {exposure.id} names capability {exposure.capability_id}, "
                    "which this project did not compile"
                )
            collected.append(exposure)
    return FrozenExposureRegistry(collected)

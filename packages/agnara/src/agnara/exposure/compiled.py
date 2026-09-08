"""What an adapter compiler produces: runtime truth and neutral records.

Two things must be produced together or the kernel gains a second source of
truth about what is reachable (RFC 0006 section 9). `SurfaceCompilation`
carries both, so a caller cannot obtain an adapter's dispatch table without
the neutral records derived from exactly that table.

`CompiledExposure` is deliberately insufficient to dispatch. It names a
capability and an adapter target; it holds no route object, no SDK tool, no
binder, no callback and no server. That is what keeps the kernel free of
protocol types while still having one answer to "where is this capability
reachable?".
"""

from __future__ import annotations

import json
from dataclasses import field
from typing import Any

from agnara._frozen import frozen_slots_dataclass
from agnara._json import canonical_json
from agnara.capability.identity import CapabilityId
from agnara.exposure.identity import ExposureError, ExposureId, SurfaceId

#: Detail key the kernel owns. Surface identity has no field of its own in
#: introspection version 0, and discarding it would understate a project that
#: runs two surfaces of one protocol. It travels as detail instead, which also
#: means `filter_snapshot` redacts deployment topology for a viewer who may
#: not see exposure detail — the correct default for a topology fact.
_SURFACE_DETAIL_KEY = "surface"


@frozen_slots_dataclass
class CompiledExposure:
    """One neutral record of one reachable adapter target.

    ``detail`` is adapter-owned canonical JSON: whatever that protocol
    considers safe to publish about this target, such as an HTTP method and
    path template. It is validated as plain JSON data, so an adapter cannot
    smuggle a runtime object into the kernel or into a snapshot.
    """

    id: ExposureId
    capability_id: CapabilityId
    detail: str = field(default="{}")

    def __post_init__(self) -> None:
        if not isinstance(self.id, ExposureId):
            raise ExposureError(f"exposure id must be an ExposureId, got {type(self.id).__name__}")
        if not isinstance(self.capability_id, CapabilityId):
            raise ExposureError(
                "exposure capability_id must be a CapabilityId, got "
                f"{type(self.capability_id).__name__}"
            )
        if not isinstance(self.detail, str):
            raise ExposureError(
                f"exposure detail must be canonical JSON text, got {type(self.detail).__name__}"
            )
        decoded = self._decoded()
        if _SURFACE_DETAIL_KEY in decoded:
            raise ExposureError(
                f"exposure {self.id} sets the kernel-owned detail key "
                f"{_SURFACE_DETAIL_KEY!r}; surface identity is derived, not declared"
            )

    def _decoded(self) -> dict[str, Any]:
        try:
            decoded = json.loads(self.detail)
        except ValueError as error:
            raise ExposureError(f"exposure {self.id} detail is not valid JSON: {error}") from error
        if not isinstance(decoded, dict):
            raise ExposureError(
                f"exposure {self.id} detail must be a JSON object, got {type(decoded).__name__}"
            )
        return decoded

    @classmethod
    def of(
        cls,
        surface: SurfaceId,
        name: str,
        capability_id: CapabilityId,
        detail: object = None,
    ) -> CompiledExposure:
        """Build a record, canonicalizing adapter-supplied detail."""
        return cls(
            ExposureId(surface, name),
            capability_id,
            canonical_json(
                {} if detail is None else detail,
                field=f"exposure {surface} {name} detail",
                error=ExposureError,
            ),
        )

    @property
    def surface(self) -> SurfaceId:
        """The named adapter surface this exposure belongs to."""
        return self.id.surface

    def published_detail(self) -> dict[str, Any]:
        """Adapter detail plus the surface name, as plain JSON data.

        This is what introspection publishes. Surface identity is added here
        rather than stored, so a record cannot disagree with its own identity.
        """
        return {**self._decoded(), _SURFACE_DETAIL_KEY: self.id.surface.name}


@frozen_slots_dataclass
class SurfaceCompilation[RuntimeT]:
    """One adapter surface's dispatch artifact and its neutral records.

    ``runtime`` is the adapter's own immutable type — a frozen route registry,
    a frozen tool table — and the kernel is generic over it precisely so that
    it never names one. The kernel reads ``surface`` and ``exposures`` and
    nothing else; ``runtime`` travels with them so that the two cannot be
    obtained separately and drift.
    """

    surface: SurfaceId
    runtime: RuntimeT
    exposures: tuple[CompiledExposure, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.surface, SurfaceId):
            raise ExposureError(
                f"surface compilation surface must be a SurfaceId, got "
                f"{type(self.surface).__name__}"
            )
        if not isinstance(self.exposures, tuple):
            raise ExposureError(
                "surface compilation exposures must be a tuple, got "
                f"{type(self.exposures).__name__}"
            )
        seen: dict[ExposureId, None] = {}
        for exposure in self.exposures:
            if not isinstance(exposure, CompiledExposure):
                raise ExposureError(
                    "surface compilation exposures must contain CompiledExposure values, got "
                    f"{type(exposure).__name__}"
                )
            if exposure.surface != self.surface:
                raise ExposureError(
                    f"surface {self.surface} contributed an exposure for {exposure.surface}; "
                    "one compiler owns one surface"
                )
            if exposure.id in seen:
                raise ExposureError(
                    f"surface {self.surface} compiled {exposure.id.name!r} twice; an "
                    "adapter-local name identifies one target"
                )
            seen[exposure.id] = None

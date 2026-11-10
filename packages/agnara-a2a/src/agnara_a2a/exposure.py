"""Declare the one capability an A2A surface serves (ADR 0098 D2, ADR 0099)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agnara import (
    Agnara,
    CapabilityDefinition,
    Confirmation,
    DefinitionError,
    UnknownCapabilityError,
)
from agnara.exposure import CompiledExposure, SurfaceCompilation, SurfaceId

__all__: list[str] = []

#: The adapter kind this package contributes to the unified exposure model.
_ADAPTER = "a2a"

#: Surface name used when a project does not name one.
_DEFAULT_SURFACE = "default"


class A2aDefinitionError(DefinitionError):
    """An A2A surface cannot be composed under the ADR 0098 profile."""


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise A2aDefinitionError(f"public A2A metadata {field!r} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class A2aSkillExposure:
    """One capability published as the single skill of an A2A surface.

    Every card field is explicit public metadata (ADR 0098 D8): nothing falls
    back to docstrings, capability identifiers or definition text.
    """

    definition: CapabilityDefinition
    id: str
    name: str
    description: str
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.definition, CapabilityDefinition):
            raise A2aDefinitionError(
                "A2A skill definition must be a CapabilityDefinition, got "
                f"{type(self.definition).__name__}"
            )
        for field in ("id", "name", "description"):
            _required_text(f"skill {field}", getattr(self, field))
        if not isinstance(self.tags, tuple) or not self.tags:
            raise A2aDefinitionError("public A2A metadata 'skill tags' needs at least one tag")
        for tag in self.tags:
            _required_text("skill tag", tag)
        if self.definition.confirmation is Confirmation.REQUIRED:
            # ADR 0098 D5: the profile has no confirmation evidence channel.
            raise A2aDefinitionError(
                f"capability {self.definition.id} requires confirmation, which the "
                "A2A profile cannot carry"
            )


class A2a:
    """Declare the A2A surface for one capability owned by one application.

    A surface serves exactly one capability (ADR 0098 D2). A deployment that
    needs several capabilities composes several `A2a` surfaces with distinct
    names and serves each at its own URL.
    """

    __slots__ = ("_app", "_exposure", "_frozen", "_lock", "_surface")

    def __init__(self, app: Agnara, *, surface: str = _DEFAULT_SURFACE) -> None:
        if not isinstance(app, Agnara):
            raise TypeError(f"app must be an Agnara application, got {type(app).__name__}")
        self._app = app
        self._surface = SurfaceId(_ADAPTER, surface)
        self._exposure: A2aSkillExposure | None = None
        self._frozen = False
        self._lock = threading.Lock()

    @property
    def is_compiled(self) -> bool:
        """Whether skill registration has been closed."""
        return self._frozen

    @property
    def surface(self) -> SurfaceId:
        """This surface's identity in the project-wide exposure registry."""
        return self._surface

    def skill(
        self,
        capability: CapabilityDefinition | Callable[..., Any],
        /,
        *,
        id: str,
        name: str,
        description: str,
        tags: tuple[str, ...],
    ) -> A2aSkillExposure:
        """Publish one declared capability as this surface's only skill."""
        exposure = A2aSkillExposure(self._resolve(capability), id, name, description, tags)
        with self._lock:
            if self._frozen:
                raise A2aDefinitionError(f"cannot register A2A skill {id!r} after A2A compilation")
            if self._exposure is not None:
                raise A2aDefinitionError(
                    f"A2A surface {self._surface.name!r} already serves "
                    f"{self._exposure.definition.id}; compose another surface instead"
                )
            self._exposure = exposure
        return exposure

    def compile(self) -> A2aSkillExposure:
        """Close registration and return the surface's skill exposure."""
        with self._lock:
            if self._exposure is None:
                raise A2aDefinitionError(f"A2A surface {self._surface.name!r} declares no skill")
            self._frozen = True
            return self._exposure

    def compile_surface(self) -> SurfaceCompilation[A2aSkillExposure]:
        """Close registration and return the skill with its neutral record."""
        exposure = self.compile()
        return SurfaceCompilation(
            self._surface,
            exposure,
            (
                CompiledExposure.of(
                    self._surface,
                    exposure.id,
                    exposure.definition.id,
                    {"skill": exposure.id},
                ),
            ),
        )

    def _resolve(
        self, capability: CapabilityDefinition | Callable[..., Any]
    ) -> CapabilityDefinition:
        if isinstance(capability, CapabilityDefinition):
            try:
                registered = self._app.capabilities[capability.id]
            except UnknownCapabilityError:
                registered = None
            if registered is not capability:
                raise A2aDefinitionError(
                    f"capability {capability.id} is not declared on application {self._app.name!r}"
                )
            return capability
        if not callable(capability):
            raise A2aDefinitionError(
                "a2a.skill expects a declared capability callable or CapabilityDefinition, got "
                f"{type(capability).__name__}"
            )
        matches = tuple(
            definition
            for capability_id in self._app.capabilities
            if (definition := self._app.capabilities[capability_id]).handler is capability
        )
        if not matches:
            raise A2aDefinitionError(
                f"callable {getattr(capability, '__name__', repr(capability))!r} is not declared "
                f"on application {self._app.name!r}"
            )
        if len(matches) > 1:
            ids = ", ".join(str(definition.id) for definition in matches)
            raise A2aDefinitionError(
                f"callable is declared as multiple capabilities ({ids}); pass a "
                "CapabilityDefinition to select one explicitly"
            )
        return matches[0]

    def __repr__(self) -> str:
        state = "compiled" if self._frozen else "open"
        served = "1 skill" if self._exposure is not None else "no skill"
        return f"A2a({self._app.name!r}, {self._surface.name!r}, {served}, {state})"

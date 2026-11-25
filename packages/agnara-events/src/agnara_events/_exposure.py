"""Internal inbound event exposure declaration and compilation (ADR 0101, EVT-03)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from agnara import (
    AnonymousPrincipal,
    CapabilityDefinition,
    CapabilityId,
    Confirmation,
    DefinitionError,
    Principal,
)
from agnara.execution import ExecutionPlan
from agnara.exposure import CompiledExposure, SurfaceCompilation, SurfaceId

__all__: list[str] = []

_ADAPTER = "events"
_DEFAULT_SURFACE = "default"
_SUBSCRIPTION_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}\Z")


class _EventsDefinitionError(DefinitionError):
    """An inbound event subscription violates the ADR 0101 profile."""


def _required_text(field: str, value: object) -> str:
    if not isinstance(value, str):
        raise _EventsDefinitionError(f"{field} must be a non-empty string")
    trimmed = value.strip()
    if not trimmed or trimmed != value:
        raise _EventsDefinitionError(
            f"{field} must be a non-empty string without leading or trailing whitespace"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in trimmed):
        raise _EventsDefinitionError(f"{field} must not contain control characters")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in trimmed):
        raise _EventsDefinitionError(f"{field} must not contain unpaired Unicode surrogates")
    return trimmed


def _optional_text(field: str, value: object) -> str | None:
    if value is None:
        return None
    return _required_text(field, value)


def _validate_public_address(address: object) -> str | None:
    if address is None:
        return None
    text = _required_text("public_address", address)
    if any(ch.isspace() for ch in text):
        raise _EventsDefinitionError("public_address must not contain whitespace")
    if "://" in text or "@" in text or "?" in text or "#" in text:
        raise _EventsDefinitionError(
            "public_address must be a logical channel address without URL scheme or credentials"
        )
    return text


@dataclass(frozen=True, slots=True)
class _EventSubscriptionExposure:
    """One declared inbound CloudEvents subscription for a capability."""

    capability_id: CapabilityId
    subscription_id: str
    event_type: str
    principal: Principal
    public_address: str | None = None
    summary: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, CapabilityId):
            raise _EventsDefinitionError(
                f"capability_id must be a CapabilityId, got {type(self.capability_id).__name__}"
            )
        _required_text("subscription_id", self.subscription_id)
        if not _SUBSCRIPTION_ID_RE.match(self.subscription_id):
            raise _EventsDefinitionError(
                "subscription_id must match ^[A-Za-z0-9._-]{1,128}$ so AsyncAPI references "
                "stay safe RFC 6901 pointers"
            )
        _required_text("event_type", self.event_type)
        if not isinstance(self.principal, Principal) or isinstance(
            self.principal, AnonymousPrincipal
        ):
            raise _EventsDefinitionError(
                "inbound event subscription requires an authenticated host-verified Principal"
            )
        _required_text("principal.identity", self.principal.identity)
        _validate_public_address(self.public_address)
        _optional_text("summary", self.summary)
        _optional_text("description", self.description)


@dataclass(frozen=True, slots=True)
class _CompiledEventBinding:
    """Immutable compiled binding between one inbound event exposure and one plan."""

    exposure: _EventSubscriptionExposure
    plan: ExecutionPlan
    surface: SurfaceId

    def __post_init__(self) -> None:
        if not isinstance(self.exposure, _EventSubscriptionExposure):
            raise _EventsDefinitionError("exposure must be an _EventSubscriptionExposure")
        if not isinstance(self.plan, ExecutionPlan):
            raise _EventsDefinitionError("plan must be an ExecutionPlan")
        if not isinstance(self.surface, SurfaceId) or self.surface.adapter != _ADAPTER:
            raise _EventsDefinitionError("surface must be an events SurfaceId")
        if self.plan.definition.id != self.exposure.capability_id:
            raise _EventsDefinitionError(
                f"compiled plan {self.plan.definition.id} does not match exposure "
                f"{self.exposure.capability_id}"
            )
        if self.plan.streaming:
            raise _EventsDefinitionError(
                f"capability {self.plan.definition.id} is streaming; ADR 0101 supports "
                "complete-result capabilities only"
            )
        if self.plan.definition.confirmation is not Confirmation.NEVER:
            raise _EventsDefinitionError(
                f"capability {self.plan.definition.id} requires confirmation, which the "
                "ADR 0101 inbound event profile cannot carry"
            )


def _declare_inbound_event(
    capability: CapabilityId | CapabilityDefinition,
    *,
    subscription_id: str,
    event_type: str,
    principal: Principal,
    public_address: str | None = None,
    summary: str | None = None,
    description: str | None = None,
) -> _EventSubscriptionExposure:
    """Declare one inbound event subscription bound to a capability and host principal."""
    if isinstance(capability, CapabilityDefinition):
        capability_id = capability.id
    elif isinstance(capability, CapabilityId):
        capability_id = capability
    else:
        raise _EventsDefinitionError(
            "capability must be a CapabilityId or CapabilityDefinition, got "
            f"{type(capability).__name__}"
        )
    return _EventSubscriptionExposure(
        capability_id=capability_id,
        subscription_id=subscription_id,
        event_type=event_type,
        principal=principal,
        public_address=public_address,
        summary=summary,
        description=description,
    )


def _compile_inbound_event(
    exposure: _EventSubscriptionExposure,
    plans: Mapping[CapabilityId, ExecutionPlan],
    *,
    surface: str = _DEFAULT_SURFACE,
) -> _CompiledEventBinding:
    """Compile one declared inbound event exposure against compiled execution plans."""
    if not isinstance(exposure, _EventSubscriptionExposure):
        raise _EventsDefinitionError("exposure must be an _EventSubscriptionExposure")
    if not isinstance(plans, Mapping):
        raise _EventsDefinitionError("plans must be a mapping of CapabilityId to ExecutionPlan")
    plan = plans.get(exposure.capability_id)
    if plan is None:
        raise _EventsDefinitionError(
            f"no compiled ExecutionPlan found for capability {exposure.capability_id}"
        )
    return _CompiledEventBinding(
        exposure=exposure,
        plan=plan,
        surface=SurfaceId(_ADAPTER, surface),
    )


def _compile_event_surface(
    binding: _CompiledEventBinding,
) -> SurfaceCompilation[_CompiledEventBinding]:
    """Produce a protocol-neutral ``SurfaceCompilation`` record for one compiled binding."""
    return SurfaceCompilation(
        binding.surface,
        binding,
        (
            CompiledExposure.of(
                binding.surface,
                binding.exposure.subscription_id,
                binding.exposure.capability_id,
                {"event_type": binding.exposure.event_type},
            ),
        ),
    )

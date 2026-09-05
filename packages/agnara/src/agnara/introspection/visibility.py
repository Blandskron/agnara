"""Decide what one viewer may see, before anything is serialized.

RFC 0003 section 2 rejects filtering a serialized document: references,
indexes and derived descriptions leak what was removed. So the snapshot is
filtered as a model, and only the result is ever serialized.

RFC 0003 also names five decisions that must stay distinct — whether a
capability is registered and executable, whether it is discoverable to a given
principal, whether an HTTP exposure appears in OpenAPI, whether a human UI is
served, and whether interactive execution is enabled. This module owns the
second one and the field-level publication that follows from it. It owns
neither invocation authority nor any transport surface, and nothing here is a
substitute for policy evaluation: seeing a capability never authorizes
invoking it (ADR 0008).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol, runtime_checkable

from agnara._frozen import frozen_slots_dataclass
from agnara.introspection.descriptors import (
    AppDescriptor,
    CapabilityDescriptor,
    DependencyDescriptor,
    ExposureDescriptor,
    IntrospectionError,
    IntrospectionSnapshot,
    ProviderDescriptor,
    TypeReference,
)
from agnara.policy.principal import Principal

__all__ = [
    "AllCapabilitiesVisible",
    "DiscoveryField",
    "DiscoveryVisibility",
    "Hiding",
    "NoCapabilityVisible",
    "ScopeVisible",
    "VisibilityRule",
    "filter_snapshot",
]


class DiscoveryField(StrEnum):
    """One independently publishable part of a described capability.

    Each member is its own decision. Nothing here is implied by anything else,
    because RFC 0003 requires that no single flag grant several publication
    decisions at once.
    """

    #: The capability's human description.
    DESCRIPTION = "description"
    #: Declared effect labels.
    EFFECTS = "effects"
    #: Declared scope labels. These name what a caller would need, not what
    #: this viewer holds.
    SCOPES = "scopes"
    #: Declared risk, confirmation requirement and idempotency.
    SAFETY = "safety"
    #: Input names, whether they are required, and their JSON Schema.
    INPUTS = "inputs"
    #: Dependency parameter names and the types bound to them.
    DEPENDENCIES = "dependencies"
    #: The application's provider graph.
    PROVIDERS = "providers"
    #: The names of the policy types a capability's plan evaluates.
    POLICIES = "policies"
    #: Exposures, and therefore the derived transport availability: in this
    #: model transport availability *is* the exposure list, so an adapter that
    #: wants coarse availability without route names contributes a coarse
    #: exposure name rather than having one fabricated here.
    EXPOSURES = "exposures"
    #: The namespaced detail an adapter attached to an exposure.
    EXPOSURE_DETAIL = "exposure_detail"
    #: The defining module of a referenced type, which describes internal
    #: package structure rather than the contract.
    TYPE_MODULES = "type_modules"


@runtime_checkable
class VisibilityRule(Protocol):
    """Decide whether one principal may discover one described capability.

    A rule sees the described capability rather than its definition, so it can
    never reach a handler, and it cannot make a capability executable or
    unexecutable. Implementations must be pure and safe to share across
    threads: one rule serves every concurrent viewer.
    """

    def visible(self, capability: CapabilityDescriptor, principal: Principal, /) -> bool: ...


@frozen_slots_dataclass
class ScopeVisible:
    """Discoverable when the principal holds every scope the capability declares.

    This is the rule the MCP adapter already applies to ``tools/list``, so a
    capability cannot be discoverable through one surface and hidden by the
    other for the same principal. A capability that declares no scopes is
    visible to everyone, including an anonymous viewer: it declares no
    requirement, and inventing one here would be guessing. Compose with
    :class:`Hiding` when something unscoped must still not be published.
    """

    def visible(self, capability: CapabilityDescriptor, principal: Principal, /) -> bool:
        return frozenset(capability.scopes).issubset(principal.scopes)


@frozen_slots_dataclass
class AllCapabilitiesVisible:
    """Discoverable to everyone. A development posture, named as one.

    Use it when a snapshot is not leaving the machine. Serving this to an
    unauthenticated viewer publishes every declared capability.
    """

    def visible(self, capability: CapabilityDescriptor, principal: Principal, /) -> bool:
        return True


@frozen_slots_dataclass
class NoCapabilityVisible:
    """Discoverable to nobody, so a surface can be turned off without removing it."""

    def visible(self, capability: CapabilityDescriptor, principal: Principal, /) -> bool:
        return False


@frozen_slots_dataclass
class Hiding:
    """Hide named capabilities, then defer to another rule.

    Hiding is not authorization: a hidden capability remains registered and
    remains invocable by anyone the policy layer allows (ADR 0008). This exists
    because the capability model has no private/internal metadata, so the
    decision belongs to whoever composes the application rather than to a flag
    this filter would have to invent.
    """

    ids: frozenset[str]
    rule: VisibilityRule

    def __init__(self, ids: Iterable[str], rule: VisibilityRule) -> None:
        hidden = frozenset(ids)
        for identifier in hidden:
            if not isinstance(identifier, str) or not identifier:
                raise IntrospectionError("hidden capability ids must be non-empty strings")
        if not isinstance(rule, VisibilityRule):
            raise IntrospectionError("Hiding requires a VisibilityRule to defer to")
        object.__setattr__(self, "ids", hidden)
        object.__setattr__(self, "rule", rule)

    def visible(self, capability: CapabilityDescriptor, principal: Principal, /) -> bool:
        if capability.id in self.ids:
            return False
        return self.rule.visible(capability, principal)


@frozen_slots_dataclass
class DiscoveryVisibility:
    """One explicit publication decision, applied to every viewer.

    ``published`` has no default. The runtime must not guess an environment
    and silently publish descriptions, schemas, dependency structure, provider
    graphs or policy names, so the decision is made by whoever composes the
    application. :meth:`identity_only`, :meth:`agent_safe` and
    :meth:`unrestricted` are named starting points, not defaults.
    """

    rule: VisibilityRule
    published: frozenset[DiscoveryField]

    def __init__(
        self,
        rule: VisibilityRule,
        published: Iterable[DiscoveryField | str],
    ) -> None:
        if not isinstance(rule, VisibilityRule):
            raise IntrospectionError("discovery visibility requires a VisibilityRule")
        if isinstance(published, str):
            raise IntrospectionError(
                "discovery visibility published fields must be a collection, not a string"
            )
        fields: set[DiscoveryField] = set()
        for field in published:
            try:
                fields.add(DiscoveryField(field))
            except ValueError as error:
                raise IntrospectionError(
                    f"unknown discovery field {field!r}; expected one of "
                    f"{sorted(member.value for member in DiscoveryField)}"
                ) from error
        object.__setattr__(self, "rule", rule)
        object.__setattr__(self, "published", frozenset(fields))

    def publishes(self, field: DiscoveryField) -> bool:
        """Whether this decision publishes one field."""
        return field in self.published

    @classmethod
    def identity_only(cls, rule: VisibilityRule) -> DiscoveryVisibility:
        """Publish that a capability exists, and nothing else about it."""
        return cls(rule, ())

    @classmethod
    def agent_safe(cls, rule: VisibilityRule) -> DiscoveryVisibility:
        """Publish what an agent needs to choose and call a capability safely.

        Description, effects, declared scopes, safety metadata, inputs and
        exposures: enough to decide whether this is the right capability and
        what invoking it would do. Dependencies, providers, policy names,
        exposure detail and type modules describe the implementation, so they
        stay unpublished.
        """
        return cls(
            rule,
            (
                DiscoveryField.DESCRIPTION,
                DiscoveryField.EFFECTS,
                DiscoveryField.SCOPES,
                DiscoveryField.SAFETY,
                DiscoveryField.INPUTS,
                DiscoveryField.EXPOSURES,
            ),
        )

    @classmethod
    def unrestricted(cls, rule: VisibilityRule) -> DiscoveryVisibility:
        """Publish every field. A development and local-tooling posture."""
        return cls(rule, tuple(DiscoveryField))


def _redacted_type(reference: TypeReference, visibility: DiscoveryVisibility) -> TypeReference:
    if visibility.publishes(DiscoveryField.TYPE_MODULES):
        return reference
    return TypeReference(reference.name)


def _exposures(
    capability: CapabilityDescriptor,
    visibility: DiscoveryVisibility,
) -> tuple[ExposureDescriptor, ...]:
    if not visibility.publishes(DiscoveryField.EXPOSURES):
        return ()
    if visibility.publishes(DiscoveryField.EXPOSURE_DETAIL):
        return capability.exposures
    return tuple(
        ExposureDescriptor(exposure.transport, exposure.name) for exposure in capability.exposures
    )


def _capability(
    capability: CapabilityDescriptor,
    visibility: DiscoveryVisibility,
) -> CapabilityDescriptor:
    """Rebuild one descriptor from published fields only.

    Rebuilding rather than blanking matters: an unpublished field must be
    absent from the result, not present with an emptied value that a reader
    could mistake for a fact about the capability.
    """
    safety = visibility.publishes(DiscoveryField.SAFETY)
    defaults = CapabilityDescriptor(capability.id)
    return CapabilityDescriptor(
        id=capability.id,
        description=(
            capability.description if visibility.publishes(DiscoveryField.DESCRIPTION) else None
        ),
        effects=capability.effects if visibility.publishes(DiscoveryField.EFFECTS) else (),
        scopes=capability.scopes if visibility.publishes(DiscoveryField.SCOPES) else (),
        risk=capability.risk if safety else defaults.risk,
        confirmation=capability.confirmation if safety else defaults.confirmation,
        idempotency=capability.idempotency if safety else defaults.idempotency,
        inputs=capability.inputs if visibility.publishes(DiscoveryField.INPUTS) else (),
        dependencies=(
            tuple(
                DependencyDescriptor(
                    dependency.parameter, _redacted_type(dependency.type, visibility)
                )
                for dependency in capability.dependencies
            )
            if visibility.publishes(DiscoveryField.DEPENDENCIES)
            else ()
        ),
        policies=capability.policies if visibility.publishes(DiscoveryField.POLICIES) else (),
        exposures=_exposures(capability, visibility),
    )


def _providers(
    app: AppDescriptor,
    visibility: DiscoveryVisibility,
) -> tuple[ProviderDescriptor, ...]:
    if not visibility.publishes(DiscoveryField.PROVIDERS):
        return ()
    return tuple(
        ProviderDescriptor(
            _redacted_type(provider.provides, visibility),
            provider.scope,
            provider.kind,
            tuple(_redacted_type(required, visibility) for required in provider.requires),
        )
        for provider in app.providers
    )


def filter_snapshot(
    snapshot: IntrospectionSnapshot,
    visibility: DiscoveryVisibility,
    principal: Principal,
) -> IntrospectionSnapshot:
    """Return the snapshot this principal may see, ready to serialize.

    An application whose capabilities are all hidden is dropped, because an
    application name is itself a disclosure. Transport availability is derived
    from the exposures that survive, so it cannot describe a transport the
    viewer was not shown.

    The result is marked filtered. That is a label for a consumer deciding
    whether it is safe to serve, not a claim that the publication decision was
    a good one.
    """
    if not isinstance(snapshot, IntrospectionSnapshot):
        raise IntrospectionError(
            f"filter_snapshot requires an IntrospectionSnapshot, got {type(snapshot).__name__}"
        )
    if not isinstance(visibility, DiscoveryVisibility):
        raise IntrospectionError(
            f"filter_snapshot requires a DiscoveryVisibility, got {type(visibility).__name__}"
        )
    if not isinstance(principal, Principal):
        raise IntrospectionError(
            f"filter_snapshot requires a Principal, got {type(principal).__name__}"
        )

    apps: list[AppDescriptor] = []
    for app in snapshot.apps:
        visible = tuple(
            _capability(capability, visibility)
            for capability in app.capabilities
            if visibility.rule.visible(capability, principal)
        )
        if not visible:
            continue
        apps.append(
            AppDescriptor(
                name=app.name,
                capabilities=visible,
                providers=_providers(app, visibility),
            )
        )
    return IntrospectionSnapshot(
        apps=tuple(apps),
        project=snapshot.project if apps else None,
        format=snapshot.format,
        version=snapshot.version,
        filtered=True,
    )

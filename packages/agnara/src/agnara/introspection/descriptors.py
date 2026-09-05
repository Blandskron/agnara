"""Immutable descriptors for one compiled Agnara surface.

These are the protocol-neutral counterpart to a protocol contract: what
OpenAPI, MCP discovery and an Agent Card each project a slice of, and what
the CLI and Agnara Explorer read directly (`ARCHITECTURE.md` section 10,
RFC 0003).

Every descriptor holds names, declared metadata and plain JSON data. None of
them holds a handler, a dependency instance, a provider callable, a policy
object or a compiled schema, so no traversal of a snapshot can reach a
runtime object. That is a structural guarantee, not a convention: the
visibility, redaction and authorization controls that decide what a
particular viewer may see are a separate layer (E8.2), and they filter this
model rather than repairing it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Confirmation, Idempotency, Risk
from agnara.errors import DefinitionError

__all__ = [
    "INTROSPECTION_FORMAT",
    "INTROSPECTION_VERSION",
    "AppDescriptor",
    "CapabilityDescriptor",
    "DependencyDescriptor",
    "ExposureDescriptor",
    "InputDescriptor",
    "IntrospectionError",
    "IntrospectionSnapshot",
    "PolicyDescriptor",
    "ProviderDescriptor",
    "TypeReference",
]

#: The snapshot's stable format marker. It names this contract so a consumer
#: can refuse a document that merely looks similar.
INTROSPECTION_FORMAT: Final = "agnara-introspection"

#: The snapshot's own version, deliberately independent of the Agnara release
#: version and of OpenAPI. ``"0"`` states that the contract is not yet stable.
INTROSPECTION_VERSION: Final = "0"

#: Deepest JSON structure copied out of a schema fragment or exposure detail.
#: A cycle is impossible below this, and a hostile or accidental deep value
#: cannot make a later serializer recurse without bound.
_MAX_DEPTH: Final = 64


class IntrospectionError(DefinitionError):
    """A snapshot cannot be built from the supplied compiled surface."""


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise IntrospectionError(f"introspection {field} must be a non-empty string")
    return value


def _optional_text(value: object, *, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise IntrospectionError(
            f"introspection {field} must be a string or None, got {type(value).__name__}"
        )
    return value


def _json_data(value: object, *, field: str, depth: int = 0) -> Any:
    """Detach plain JSON data, refusing anything a snapshot must not carry.

    Copying matters as much as validating: a schema fragment or exposure
    detail supplied by an adapter stays owned by that adapter, and a snapshot
    that shared it could change after it was read.
    """
    if depth > _MAX_DEPTH:
        raise IntrospectionError(f"introspection {field} nests deeper than {_MAX_DEPTH} levels")
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise IntrospectionError(f"introspection {field} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise IntrospectionError(
                    f"introspection {field} contains a non-string object key {key!r}"
                )
            copied[key] = _json_data(item, field=f"{field}.{key}", depth=depth + 1)
        return copied
    if isinstance(value, list | tuple):
        return [
            _json_data(item, field=f"{field}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    raise IntrospectionError(
        f"introspection {field} contains a non-JSON value of type {type(value).__name__}"
    )


def _frozen_json(value: object, *, field: str) -> str:
    """Freeze detached JSON data into its canonical text.

    A frozen slotted dataclass cannot hold a mutable mapping and stay honest
    about immutability, and a read-only proxy would still be a view of
    something a caller could mutate. Canonical text is immutable, hashable,
    comparable and trivially deterministic to serialize.
    """
    return json.dumps(
        _json_data(value, field=field),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@frozen_slots_dataclass
class TypeReference:
    """A Python type named without being reachable.

    ``module`` is separate because it exposes internal package structure that
    a deployment may not want published; a filter can drop it without
    rebuilding the reference.
    """

    name: str
    module: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, field="type name")
        _optional_text(self.module, field="type module")

    @classmethod
    def of(cls, annotation: type) -> TypeReference:
        """Describe an annotation by name, keeping no reference to it."""
        name = getattr(annotation, "__qualname__", None) or getattr(annotation, "__name__", None)
        if not isinstance(name, str) or not name:
            name = str(annotation)
        module = getattr(annotation, "__module__", None)
        return cls(name, module if isinstance(module, str) and module else None)

    def json_data(self) -> dict[str, Any]:
        document: dict[str, Any] = {"name": self.name}
        if self.module is not None:
            document["module"] = self.module
        return document


@frozen_slots_dataclass
class InputDescriptor:
    """One declared capability input and its published JSON Schema."""

    name: str
    required: bool
    schema: str

    def __post_init__(self) -> None:
        _text(self.name, field="input name")
        if not isinstance(self.required, bool):
            raise IntrospectionError("introspection input required must be a boolean")
        _text(self.schema, field="input schema")

    @classmethod
    def of(cls, name: str, *, required: bool, schema: object) -> InputDescriptor:
        return cls(name, required, _frozen_json(schema, field=f"input {name} schema"))

    def json_data(self) -> dict[str, Any]:
        return {"name": self.name, "required": self.required, "schema": json.loads(self.schema)}


@frozen_slots_dataclass
class DependencyDescriptor:
    """One dependency a capability handler declares, named not resolved."""

    parameter: str
    type: TypeReference

    def __post_init__(self) -> None:
        _text(self.parameter, field="dependency parameter")
        if not isinstance(self.type, TypeReference):
            raise IntrospectionError("introspection dependency type must be a TypeReference")

    def json_data(self) -> dict[str, Any]:
        return {"parameter": self.parameter, "type": self.type.json_data()}


@frozen_slots_dataclass
class ProviderDescriptor:
    """One bound dependency provider, as a graph node without its callable.

    ``requires`` lists the provider's own bound dependencies, so a relationship
    view (E8.5) can be drawn from the snapshot alone rather than by walking the
    DI registry a second time.
    """

    provides: TypeReference
    scope: str
    kind: str
    requires: tuple[TypeReference, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provides, TypeReference):
            raise IntrospectionError("introspection provider provides must be a TypeReference")
        _text(self.scope, field="provider scope")
        _text(self.kind, field="provider kind")
        if not isinstance(self.requires, tuple) or any(
            not isinstance(item, TypeReference) for item in self.requires
        ):
            raise IntrospectionError(
                "introspection provider requires must be a tuple of TypeReference values"
            )

    def json_data(self) -> dict[str, Any]:
        return {
            "provides": self.provides.json_data(),
            "scope": self.scope,
            "kind": self.kind,
            "requires": [item.json_data() for item in self.requires],
        }


@frozen_slots_dataclass
class PolicyDescriptor:
    """One policy attached to a compiled plan, named not carried.

    Only the policy type's name is recorded. A policy's configuration is its
    own internal state, and publishing it would describe how authorization can
    be satisfied rather than that it applies.
    """

    kind: str

    def __post_init__(self) -> None:
        _text(self.kind, field="policy kind")

    def json_data(self) -> dict[str, Any]:
        return {"kind": self.kind}


@frozen_slots_dataclass
class ExposureDescriptor:
    """One transport exposure, contributed by an adapter as plain data.

    Core defines this contract but never fills it in: it imports no adapter,
    so ``transport`` and ``detail`` are whatever the adapter that owns the
    exposure chooses to publish. ``detail`` is namespaced by ``transport`` and
    must be JSON data, which is what keeps an adapter from smuggling a route
    object, a server or a client into the snapshot.
    """

    transport: str
    name: str
    detail: str = "{}"

    def __post_init__(self) -> None:
        _text(self.transport, field="exposure transport")
        _text(self.name, field="exposure name")
        _text(self.detail, field="exposure detail")

    @classmethod
    def of(cls, transport: str, name: str, detail: object = None) -> ExposureDescriptor:
        return cls(
            transport,
            name,
            _frozen_json({} if detail is None else detail, field=f"{transport} exposure detail"),
        )

    def json_data(self) -> dict[str, Any]:
        return {"transport": self.transport, "name": self.name, "detail": json.loads(self.detail)}


@frozen_slots_dataclass
class CapabilityDescriptor:
    """One compiled capability, described without its handler.

    Metadata is reported as declared. Effects, scopes, risk, idempotency and
    confirmation describe what invoking this capability does; none of them
    authorizes anything (ADR 0008), and a viewer seeing this descriptor has
    not thereby been allowed to invoke it.
    """

    id: str
    description: str | None = None
    effects: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    risk: str = Risk.LOW.value
    confirmation: str = Confirmation.NEVER.value
    idempotency: str = Idempotency.UNKNOWN.value
    inputs: tuple[InputDescriptor, ...] = ()
    dependencies: tuple[DependencyDescriptor, ...] = ()
    policies: tuple[PolicyDescriptor, ...] = ()
    exposures: tuple[ExposureDescriptor, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, field="capability id")
        try:
            CapabilityId.parse(self.id)
        except DefinitionError as error:
            raise IntrospectionError(
                f"introspection capability id {self.id!r} is not a valid capability identity"
            ) from error
        _optional_text(self.description, field="capability description")
        for field, values, expected in (
            ("effects", self.effects, str),
            ("scopes", self.scopes, str),
            ("inputs", self.inputs, InputDescriptor),
            ("dependencies", self.dependencies, DependencyDescriptor),
            ("policies", self.policies, PolicyDescriptor),
            ("exposures", self.exposures, ExposureDescriptor),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(item, expected) for item in values
            ):
                raise IntrospectionError(
                    f"introspection capability {field} must be a tuple of "
                    f"{expected.__name__} values"
                )
        for field, value, enumeration in (
            ("risk", self.risk, Risk),
            ("confirmation", self.confirmation, Confirmation),
            ("idempotency", self.idempotency, Idempotency),
        ):
            if value not in {member.value for member in enumeration}:
                raise IntrospectionError(
                    f"introspection capability {field} must be one of "
                    f"{sorted(member.value for member in enumeration)}"
                )

    @property
    def transports(self) -> tuple[str, ...]:
        """Transports this capability is exposed through, in first-seen order."""
        return tuple(dict.fromkeys(exposure.transport for exposure in self.exposures))

    def json_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "effects": list(self.effects),
            "scopes": list(self.scopes),
            "risk": self.risk,
            "confirmation": self.confirmation,
            "idempotency": self.idempotency,
            "inputs": [item.json_data() for item in self.inputs],
            "dependencies": [item.json_data() for item in self.dependencies],
            "policies": [item.json_data() for item in self.policies],
            "exposures": [item.json_data() for item in self.exposures],
            "transports": list(self.transports),
        }


@frozen_slots_dataclass
class AppDescriptor:
    """One compiled application: its namespace, capabilities and providers."""

    name: str
    capabilities: tuple[CapabilityDescriptor, ...] = ()
    providers: tuple[ProviderDescriptor, ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, field="app name")
        if not isinstance(self.capabilities, tuple) or any(
            not isinstance(item, CapabilityDescriptor) for item in self.capabilities
        ):
            raise IntrospectionError(
                "introspection app capabilities must be a tuple of CapabilityDescriptor values"
            )
        if not isinstance(self.providers, tuple) or any(
            not isinstance(item, ProviderDescriptor) for item in self.providers
        ):
            raise IntrospectionError(
                "introspection app providers must be a tuple of ProviderDescriptor values"
            )
        identifiers = [capability.id for capability in self.capabilities]
        if len(identifiers) != len(set(identifiers)):
            raise IntrospectionError(f"introspection app {self.name!r} repeats a capability id")

    @property
    def transports(self) -> tuple[str, ...]:
        """Transports any capability in this app is exposed through."""
        return tuple(
            dict.fromkeys(
                transport for capability in self.capabilities for transport in capability.transports
            )
        )

    def json_data(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "transports": list(self.transports),
            "capabilities": [item.json_data() for item in self.capabilities],
            "providers": [item.json_data() for item in self.providers],
        }


@frozen_slots_dataclass
class IntrospectionSnapshot:
    """An immutable, versioned view of one compiled project.

    ``project`` is optional because a project is not yet a runtime concept
    (EPIC 0A and EPIC 1A); a snapshot of one standalone application says so by
    leaving it unset rather than by inventing a name.
    """

    apps: tuple[AppDescriptor, ...] = ()
    project: str | None = None
    format: str = INTROSPECTION_FORMAT
    version: str = INTROSPECTION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.apps, tuple) or any(
            not isinstance(item, AppDescriptor) for item in self.apps
        ):
            raise IntrospectionError(
                "introspection snapshot apps must be a tuple of AppDescriptor values"
            )
        names = [app.name for app in self.apps]
        if len(names) != len(set(names)):
            raise IntrospectionError("introspection snapshot repeats an app name")
        _optional_text(self.project, field="project")
        if self.project is not None and not self.project:
            raise IntrospectionError("introspection project must be a non-empty string or None")
        _text(self.format, field="format")
        _text(self.version, field="version")

    @property
    def transports(self) -> tuple[str, ...]:
        """Transports any app in this snapshot is exposed through."""
        return tuple(dict.fromkeys(transport for app in self.apps for transport in app.transports))

    def json_data(self) -> dict[str, Any]:
        """Return the snapshot's stable JSON data form.

        Serializing is not publishing. A snapshot reaching this method is
        already whatever the caller decided a viewer may see; the visibility,
        redaction and authorization decisions belong upstream (E8.2), because
        filtering a serialized document leaves references and counts behind.
        """
        return {
            "format": self.format,
            "version": self.version,
            "project": self.project,
            "transports": list(self.transports),
            "apps": [app.json_data() for app in self.apps],
        }

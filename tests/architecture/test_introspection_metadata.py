"""The snapshot model still covers what `ARCHITECTURE.md` says it covers.

Section 10 lists the concepts the protocol-neutral snapshot represents. That
list is prose, and prose does not fail when the model drifts away from it. This
module reads the list out of the document and checks the model against it, so
removing a concept from either one breaks a test rather than a promise.

It also checks the vocabulary. Every metadata value a surface can emit has to
come from a core enum: a surface that invented its own risk level would be
describing a capability in terms the runtime never agreed to.
"""

from __future__ import annotations

import dataclasses
import re
from enum import StrEnum
from typing import Any

import pytest

from agnara.capability.metadata import Confirmation, Idempotency, Risk
from agnara.introspection import (
    INTROSPECTION_FORMAT,
    INTROSPECTION_VERSION,
    AppDescriptor,
    CapabilityDescriptor,
    DependencyDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    ExposureDescriptor,
    InputDescriptor,
    IntrospectionError,
    IntrospectionSnapshot,
    PolicyDescriptor,
    ProviderDescriptor,
    ScopeVisible,
)
from tests.architecture.boundaries import WORKSPACE_ROOT

ARCHITECTURE = WORKSPACE_ROOT / "ARCHITECTURE.md"

#: Where each concept `ARCHITECTURE.md` lists is represented. A concept with no
#: entry here has either left the document or never reached the model, and
#: either way somebody has to decide which.
CONCEPT_HOME: dict[str, tuple[type, str]] = {
    "Project": (IntrospectionSnapshot, "project"),
    "Apps": (IntrospectionSnapshot, "apps"),
    "Capabilities": (AppDescriptor, "capabilities"),
    "Exposures": (CapabilityDescriptor, "exposures"),
    "Dependencies": (CapabilityDescriptor, "dependencies"),
    "Policies": (CapabilityDescriptor, "policies"),
    "Effects": (CapabilityDescriptor, "effects"),
    "Risk": (CapabilityDescriptor, "risk"),
    "Idempotency": (CapabilityDescriptor, "idempotency"),
    "Confirmation": (CapabilityDescriptor, "confirmation"),
    "Schemas": (InputDescriptor, "schema"),
    "Transport availability": (CapabilityDescriptor, "transports"),
}

#: Descriptor fields that identify rather than describe. Publishing one is what
#: it means for something to be visible at all, so none has — or needs — its
#: own `DiscoveryField`: the visibility *rule* governs them, not the published
#: field set.
IDENTITY_FIELDS = {
    (CapabilityDescriptor, "id"),
    (AppDescriptor, "name"),
    (AppDescriptor, "capabilities"),
    (IntrospectionSnapshot, "apps"),
    (IntrospectionSnapshot, "project"),
    (IntrospectionSnapshot, "format"),
    (IntrospectionSnapshot, "version"),
    (IntrospectionSnapshot, "filtered"),
}

#: Every remaining descriptor field, and the decision that publishes it.
FIELD_DECISION: dict[tuple[type, str], DiscoveryField] = {
    (CapabilityDescriptor, "description"): DiscoveryField.DESCRIPTION,
    (CapabilityDescriptor, "effects"): DiscoveryField.EFFECTS,
    (CapabilityDescriptor, "scopes"): DiscoveryField.SCOPES,
    (CapabilityDescriptor, "risk"): DiscoveryField.SAFETY,
    (CapabilityDescriptor, "confirmation"): DiscoveryField.SAFETY,
    (CapabilityDescriptor, "idempotency"): DiscoveryField.SAFETY,
    (CapabilityDescriptor, "inputs"): DiscoveryField.INPUTS,
    (CapabilityDescriptor, "dependencies"): DiscoveryField.DEPENDENCIES,
    (CapabilityDescriptor, "policies"): DiscoveryField.POLICIES,
    (CapabilityDescriptor, "exposures"): DiscoveryField.EXPOSURES,
    (AppDescriptor, "providers"): DiscoveryField.PROVIDERS,
}


def _documented_concepts() -> list[str]:
    """Read the concept list out of `ARCHITECTURE.md` section 10."""
    text = ARCHITECTURE.read_text(encoding="utf-8")
    match = re.search(
        r"### Protocol-neutral introspection.*?```text\n(.*?)```",
        text,
        re.DOTALL,
    )
    assert match is not None, "ARCHITECTURE.md no longer lists the snapshot concepts"
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def test_every_documented_concept_is_represented_in_the_model() -> None:
    documented = _documented_concepts()

    assert documented, "the concept list is empty"
    assert set(documented) == set(CONCEPT_HOME), (
        "ARCHITECTURE.md and the model's concept map disagree; "
        f"document={sorted(documented)}, map={sorted(CONCEPT_HOME)}"
    )
    for concept, (owner, attribute) in CONCEPT_HOME.items():
        assert hasattr(owner, attribute), f"{concept} has no home on {owner.__name__}"


def test_the_documented_order_is_stable() -> None:
    """The list is read by humans; reordering it silently is a documentation bug."""
    assert _documented_concepts()[:4] == ["Project", "Apps", "Capabilities", "Exposures"]


def _described(attribute: str, value: str) -> CapabilityDescriptor:
    arguments: dict[str, Any] = {"id": "app.capability", attribute: value}
    return CapabilityDescriptor(**arguments)


@pytest.mark.parametrize(
    ("attribute", "enumeration"),
    [
        ("risk", Risk),
        ("confirmation", Confirmation),
        ("idempotency", Idempotency),
    ],
)
def test_metadata_values_come_from_a_core_enum(attribute: str, enumeration: type[StrEnum]) -> None:
    allowed = {member.value for member in enumeration}

    assert getattr(CapabilityDescriptor("app.capability"), attribute) in allowed
    for value in allowed:
        assert getattr(_described(attribute, value), attribute) == value
    for invented in ("catastrophic", "sometimes", "maybe"):
        assert invented not in allowed
        with pytest.raises(IntrospectionError):
            _described(attribute, invented)


def test_no_descriptor_field_is_published_without_a_named_decision() -> None:
    """Adding a field must not quietly widen what a posture publishes."""
    described: set[tuple[type, str]] = set()
    for owner in (
        IntrospectionSnapshot,
        AppDescriptor,
        CapabilityDescriptor,
        InputDescriptor,
        DependencyDescriptor,
        ProviderDescriptor,
        PolicyDescriptor,
        ExposureDescriptor,
    ):
        for field in dataclasses.fields(owner):
            described.add((owner, field.name))

    # Nested descriptors are published with the collection that holds them, so
    # only the owners of those collections carry a decision.
    nested = {
        InputDescriptor,
        DependencyDescriptor,
        ProviderDescriptor,
        PolicyDescriptor,
        ExposureDescriptor,
    }
    undecided = {
        entry
        for entry in described
        if entry[0] not in nested and entry not in IDENTITY_FIELDS and entry not in FIELD_DECISION
    }

    assert not undecided, (
        "these descriptor fields have no DiscoveryField and are not identity: "
        f"{sorted((owner.__name__, name) for owner, name in undecided)}"
    )


def test_every_named_decision_publishes_something() -> None:
    """A decision nobody consults is a decision a composer cannot make."""
    consulted = set(FIELD_DECISION.values()) | {
        DiscoveryField.EXPOSURE_DETAIL,
        DiscoveryField.TYPE_MODULES,
    }

    assert consulted == set(DiscoveryField)


def test_provenance_is_part_of_the_model_rather_than_a_surface_decision() -> None:
    document = IntrospectionSnapshot().json_data()

    assert document["format"] == INTROSPECTION_FORMAT
    assert document["version"] == INTROSPECTION_VERSION
    # Every surface renders from `json_data`, so none of them can drop these
    # without removing them here first.
    assert {"format", "version", "filtered"} <= set(document)


def test_the_identity_only_posture_publishes_no_described_field() -> None:
    visibility = DiscoveryVisibility.identity_only(ScopeVisible())

    for field in FIELD_DECISION.values():
        assert not visibility.publishes(field)

"""E1.1 and E1.8 — the definition is immutable and carries agentic metadata."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from agnara import (
    CapabilityDefinition,
    CapabilityId,
    Confirmation,
    DefinitionError,
    Idempotency,
    Risk,
    StandardEffect,
)

REFUND = CapabilityId("payments", "refund")


def handler() -> str:
    return "receipt"


def define(**overrides: Any) -> CapabilityDefinition:
    """Build a definition, overriding any field.

    Typed as `Any` on purpose: many tests deliberately pass values the
    signature rejects, to prove construction validates them at runtime.
    """
    kwargs: dict[str, Any] = {"id": REFUND, "handler": handler}
    kwargs.update(overrides)
    return CapabilityDefinition(**kwargs)


class TestConstruction:
    def test_requires_only_an_id_and_a_handler(self) -> None:
        definition = define()
        assert definition.id == REFUND
        assert definition.handler is handler

    def test_renders_as_its_id(self) -> None:
        assert str(define()) == "payments.refund"

    def test_rejects_a_string_id(self) -> None:
        """A raw string would defeat the validation CapabilityId performs."""
        with pytest.raises(DefinitionError, match="CapabilityId"):
            define(id="payments.refund")

    def test_rejects_a_non_callable_handler(self) -> None:
        with pytest.raises(DefinitionError, match="callable"):
            define(handler="not a function")

    def test_accepts_any_callable_object(self) -> None:
        class Invocable:
            def __call__(self) -> None:
                return None

        invocable = Invocable()
        assert define(handler=invocable).handler is invocable


class TestDefaults:
    def test_risk_defaults_to_low(self) -> None:
        assert define().risk is Risk.LOW

    def test_confirmation_defaults_to_never(self) -> None:
        assert define().confirmation is Confirmation.NEVER

    def test_effects_default_to_empty(self) -> None:
        assert define().effects == frozenset()

    def test_description_defaults_to_none(self) -> None:
        assert define().description is None

    def test_idempotency_defaults_to_unknown_not_yes(self) -> None:
        """RFC 0001: claiming idempotency falsely is worse than admitting
        ignorance, because a caller may retry and duplicate real effects."""
        assert define().idempotency is Idempotency.UNKNOWN


class TestMetadataCoercion:
    @pytest.mark.parametrize("value", ["low", "medium", "high", "critical"])
    def test_risk_accepts_its_string_form(self, value: str) -> None:
        assert define(risk=value).risk == Risk(value)

    @pytest.mark.parametrize("value", ["never", "policy", "required"])
    def test_confirmation_accepts_its_string_form(self, value: str) -> None:
        assert define(confirmation=value).confirmation == Confirmation(value)

    @pytest.mark.parametrize("value", ["yes", "no", "unknown"])
    def test_idempotency_accepts_its_string_form(self, value: str) -> None:
        assert define(idempotency=value).idempotency == Idempotency(value)

    def test_rejects_an_unknown_risk(self) -> None:
        with pytest.raises(DefinitionError, match="invalid risk"):
            define(risk="catastrophic")

    def test_rejects_an_unknown_confirmation(self) -> None:
        with pytest.raises(DefinitionError, match="invalid confirmation"):
            define(confirmation="maybe")

    def test_rejects_an_unknown_idempotency(self) -> None:
        with pytest.raises(DefinitionError, match="invalid idempotency"):
            define(idempotency="probably")

    def test_the_error_lists_the_allowed_values(self) -> None:
        with pytest.raises(DefinitionError, match="'low', 'medium', 'high', 'critical'"):
            define(risk="catastrophic")


class TestEffects:
    def test_accepts_a_set(self) -> None:
        assert define(effects={"database-write"}).effects == frozenset({"database-write"})

    def test_accepts_any_iterable(self) -> None:
        assert define(effects=["read", "read"]).effects == frozenset({"read"})

    def test_accepts_the_standard_vocabulary(self) -> None:
        definition = define(effects={StandardEffect.FINANCIAL_WRITE})
        assert definition.has_effect("financial-write")

    def test_accepts_an_application_specific_effect(self) -> None:
        """The vocabulary is open; applications have effects Agnara cannot
        anticipate."""
        assert define(effects={"warehouse-dispatch"}).has_effect("warehouse-dispatch")

    def test_rejects_a_bare_string(self) -> None:
        """Passing `effects="read"` would silently become a set of characters."""
        with pytest.raises(DefinitionError, match="not the single string"):
            define(effects="read")

    def test_rejects_an_empty_effect(self) -> None:
        with pytest.raises(DefinitionError, match="empty or whitespace"):
            define(effects={"  "})

    def test_is_stored_as_a_frozenset(self) -> None:
        assert isinstance(define(effects={"read"}).effects, frozenset)

    def test_a_caller_cannot_mutate_effects_afterwards(self) -> None:
        """The definition copies the set; it does not alias the caller's."""
        mutable = {"read"}
        definition = define(effects=mutable)
        mutable.add("destructive")
        assert definition.effects == frozenset({"read"})

    def test_has_effect_is_false_for_an_undeclared_effect(self) -> None:
        assert not define(effects={"read"}).has_effect("destructive")

    def test_rejects_a_non_string_effect(self) -> None:
        with pytest.raises(DefinitionError, match="not a string"):
            define(effects={1, 2})

    @pytest.mark.parametrize(
        ("label", "value"),
        [
            ("none", None),
            ("an integer", 123),
            ("a list of lists", [["read"]]),
            ("a dict of lists", {"read": []}.items()),
        ],
    )
    def test_rejects_effects_that_are_not_an_iterable_of_strings(
        self, label: str, value: object
    ) -> None:
        """Every rejection is a DefinitionError, never a raw TypeError.

        Construction promises protocol-neutral errors. A caller catching
        `DefinitionError` should not also have to catch whatever the
        standard library happened to raise on the way.
        """
        with pytest.raises(DefinitionError):
            define(effects=value)


class TestImmutability:
    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            ("id", CapabilityId("billing", "refund")),
            ("handler", print),
            ("description", "changed"),
            ("effects", frozenset({"destructive"})),
            ("risk", Risk.CRITICAL),
            ("confirmation", Confirmation.REQUIRED),
            ("idempotency", Idempotency.YES),
        ],
    )
    def test_every_field_is_frozen(self, attribute: str, value: object) -> None:
        definition = define()
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(definition, attribute, value)

    def test_remains_slotted(self) -> None:
        assert not hasattr(define(), "__dict__")

    def test_no_new_attribute_can_be_added(self) -> None:
        """A typo reports the same clear frozen-value error as a real field."""
        definition = define()
        with pytest.raises(
            dataclasses.FrozenInstanceError,
            match="cannot assign to field 'exposures'",
        ):
            definition.exposures = ["http"]  # ty: ignore[invalid-assignment]
        assert not hasattr(definition, "exposures")

    def test_unknown_attribute_cannot_be_deleted(self) -> None:
        definition = define()
        with pytest.raises(
            dataclasses.FrozenInstanceError,
            match="cannot delete field 'exposures'",
        ):
            del definition.exposures  # ty: ignore[unresolved-attribute]

    def test_replace_produces_a_new_definition(self) -> None:
        original = define()
        changed = dataclasses.replace(original, risk=Risk.HIGH)
        assert original.risk is Risk.LOW
        assert changed.risk is Risk.HIGH
        assert changed.id == original.id

    def test_replace_revalidates(self) -> None:
        with pytest.raises(DefinitionError):
            dataclasses.replace(define(), risk="catastrophic")


class TestValueSemantics:
    def test_equal_definitions_compare_equal(self) -> None:
        assert define(risk="high") == define(risk="high")

    def test_differing_metadata_compares_unequal(self) -> None:
        assert define(risk="high") != define(risk="low")

    def test_is_hashable_and_usable_as_a_key(self) -> None:
        assert {define(): "plan"}[define()] == "plan"

    def test_string_and_enum_metadata_are_interchangeable(self) -> None:
        assert define(risk="high") == define(risk=Risk.HIGH)
        assert hash(define(risk="high")) == hash(define(risk=Risk.HIGH))


class TestAgenticDeclaration:
    def test_a_high_risk_destructive_capability_reads_as_intended(self) -> None:
        """The golden example from docs/API_DESIGN.md section 12."""
        definition = define(
            id=CapabilityId("accounts", "delete_account"),
            description="Permanently delete an account",
            effects={StandardEffect.DESTRUCTIVE},
            risk=Risk.HIGH,
            confirmation=Confirmation.REQUIRED,
            idempotency=Idempotency.NO,
        )
        assert definition.has_effect("destructive")
        assert definition.confirmation is Confirmation.REQUIRED
        assert definition.idempotency is Idempotency.NO

    def test_metadata_carries_no_authorization(self) -> None:
        """ADR 0008: metadata is input to a policy engine, not a decision.

        The definition exposes no `authorize`, `is_allowed` or similar
        surface. If one ever appears, this test fails and forces the ADR to
        be revisited rather than quietly bypassed.
        """
        forbidden = {"authorize", "is_allowed", "check_permission", "can_invoke"}
        assert forbidden.isdisjoint(dir(define()))

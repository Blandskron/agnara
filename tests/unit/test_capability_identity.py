"""E1.2 — capability identity is stable, validated and transport-neutral."""

from __future__ import annotations

import dataclasses
import re

import pytest

from agnara import CapabilityId, DefinitionError


class TestConstruction:
    def test_builds_from_namespace_and_name(self) -> None:
        capability_id = CapabilityId(namespace="payments", name="refund")
        assert capability_id.namespace == "payments"
        assert capability_id.name == "refund"

    def test_renders_as_a_dotted_string(self) -> None:
        assert str(CapabilityId("payments", "refund")) == "payments.refund"

    def test_name_may_be_a_dotted_qualified_name(self) -> None:
        """A Python qualified name can contain dots, as in `Refunds.create`."""
        capability_id = CapabilityId("payments", "Refunds.create")
        assert str(capability_id) == "payments.Refunds.create"


class TestParsing:
    def test_parses_a_dotted_string(self) -> None:
        assert CapabilityId.parse("payments.refund") == CapabilityId("payments", "refund")

    def test_splits_on_the_first_separator(self) -> None:
        """Splitting last would make a dotted qualified name ambiguous."""
        capability_id = CapabilityId.parse("payments.Refunds.create")
        assert capability_id.namespace == "payments"
        assert capability_id.name == "Refunds.create"

    def test_round_trips_through_its_string_form(self) -> None:
        for text in ("payments.refund", "payments.Refunds.create", "users.disable_account"):
            assert str(CapabilityId.parse(text)) == text

    def test_rejects_a_string_without_a_namespace(self) -> None:
        with pytest.raises(DefinitionError, match="found no"):
            CapabilityId.parse("refund")


class TestValidation:
    @pytest.mark.parametrize(
        "text",
        [
            ".refund",
            "payments.",
            "payments..refund",
            "pay ments.refund",
            "payments.re fund",
            "1payments.refund",
            "payments.1refund",
            "payments.re-fund",
            "pay-ments.refund",
        ],
    )
    def test_rejects_a_malformed_id(self, text: str) -> None:
        with pytest.raises(DefinitionError):
            CapabilityId.parse(text)

    def test_rejects_an_empty_namespace(self) -> None:
        with pytest.raises(DefinitionError, match="namespace"):
            CapabilityId(namespace="", name="refund")

    def test_rejects_an_empty_name(self) -> None:
        with pytest.raises(DefinitionError, match="name"):
            CapabilityId(namespace="payments", name="")

    def test_rejects_a_dotted_namespace(self) -> None:
        """The first separator is what splits namespace from name."""
        with pytest.raises(DefinitionError, match="single segment"):
            CapabilityId(namespace="commerce.payments", name="refund")

    @pytest.mark.parametrize(
        ("namespace", "name"),
        [
            (123, "refund"),
            ("payments", None),
            (None, None),
            (b"payments", "refund"),
        ],
    )
    def test_rejects_a_non_string_segment(self, namespace: object, name: object) -> None:
        """A wrong type raises DefinitionError, never a raw TypeError.

        Without an explicit type check the `isidentifier` and containment
        tests below leak `AttributeError` or `TypeError` instead.
        """
        with pytest.raises(DefinitionError, match="must be a string"):
            CapabilityId(namespace, name)  # ty: ignore[invalid-argument-type]

    def test_the_error_message_names_the_offending_id(self) -> None:
        with pytest.raises(DefinitionError, match=re.escape("payments.re-fund")):
            CapabilityId.parse("payments.re-fund")


class TestValueSemantics:
    def test_equal_ids_compare_equal(self) -> None:
        assert CapabilityId("payments", "refund") == CapabilityId("payments", "refund")

    def test_different_ids_compare_unequal(self) -> None:
        assert CapabilityId("payments", "refund") != CapabilityId("payments", "capture")
        assert CapabilityId("payments", "refund") != CapabilityId("billing", "refund")

    def test_is_hashable_and_usable_as_a_key(self) -> None:
        registry = {CapabilityId("payments", "refund"): "handler"}
        assert registry[CapabilityId("payments", "refund")] == "handler"

    def test_equal_ids_hash_equally(self) -> None:
        assert hash(CapabilityId("payments", "refund")) == hash(
            CapabilityId.parse("payments.refund")
        )

    def test_is_frozen(self) -> None:
        capability_id = CapabilityId("payments", "refund")
        with pytest.raises(dataclasses.FrozenInstanceError):
            capability_id.namespace = "billing"  # ty: ignore[invalid-assignment]

    def test_remains_slotted(self) -> None:
        assert not hasattr(CapabilityId("payments", "refund"), "__dict__")

    def test_unknown_attribute_reports_a_clear_frozen_error(self) -> None:
        capability_id = CapabilityId("payments", "refund")
        with pytest.raises(
            dataclasses.FrozenInstanceError,
            match="cannot assign to field 'version'",
        ):
            capability_id.version = 2  # ty: ignore[invalid-assignment]

    def test_unknown_attribute_cannot_be_deleted(self) -> None:
        capability_id = CapabilityId("payments", "refund")
        with pytest.raises(
            dataclasses.FrozenInstanceError,
            match="cannot delete field 'version'",
        ):
            delattr(capability_id, "version")

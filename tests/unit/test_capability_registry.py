"""E1.4 to E1.7 — registration, duplicates, freezing and introspection."""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from typing import Any

import pytest

from agnara import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityRegistry,
    DuplicateCapabilityError,
    FrozenCapabilityRegistry,
    RegistryError,
    RegistryFrozenError,
    StandardEffect,
    UnknownCapabilityError,
)


def handler() -> None:
    return None


def define(namespace: str, name: str, **overrides: object) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId(namespace, name),
        handler=handler,
        **overrides,  # ty: ignore[invalid-argument-type]
    )


REFUND = define("payments", "refund")
CAPTURE = define("payments", "capture")
GET_USER = define("users", "get")


class TestRegistration:
    def test_starts_empty(self) -> None:
        assert len(CapabilityRegistry()) == 0

    def test_accepts_initial_definitions(self) -> None:
        assert len(CapabilityRegistry([REFUND, CAPTURE])) == 2

    def test_register_returns_the_definition(self) -> None:
        """So a decorator can register and hand the value straight back."""
        assert CapabilityRegistry().register(REFUND) is REFUND

    def test_registered_capability_is_found(self) -> None:
        registry = CapabilityRegistry([REFUND])
        assert registry[REFUND.id] is REFUND

    def test_rejects_something_that_is_not_a_definition(self) -> None:
        with pytest.raises(TypeError, match="CapabilityDefinition"):
            CapabilityRegistry().register("payments.refund")  # ty: ignore[invalid-argument-type]


class TestDuplicates:
    def test_registering_the_same_id_twice_raises(self) -> None:
        registry = CapabilityRegistry([REFUND])
        with pytest.raises(DuplicateCapabilityError):
            registry.register(REFUND)

    def test_a_different_definition_with_the_same_id_also_raises(self) -> None:
        """Identity collides, not the object. A silent overwrite would make
        every policy rule and audit record referencing the id ambiguous."""
        registry = CapabilityRegistry([REFUND])
        with pytest.raises(DuplicateCapabilityError):
            registry.register(define("payments", "refund", risk="high"))

    def test_the_error_names_the_capability(self) -> None:
        registry = CapabilityRegistry([REFUND])
        with pytest.raises(DuplicateCapabilityError, match=re.escape("payments.refund")):
            registry.register(REFUND)

    def test_the_first_registration_survives_a_rejected_duplicate(self) -> None:
        registry = CapabilityRegistry([REFUND])
        with pytest.raises(DuplicateCapabilityError):
            registry.register(define("payments", "refund", risk="high"))
        assert registry["payments.refund"] is REFUND
        assert len(registry) == 1

    def test_the_same_name_in_another_namespace_is_not_a_duplicate(self) -> None:
        registry = CapabilityRegistry([define("payments", "get")])
        registry.register(define("users", "get"))
        assert len(registry) == 2

    def test_is_a_registry_error(self) -> None:
        assert issubclass(DuplicateCapabilityError, RegistryError)


class TestLookup:
    def test_by_capability_id(self) -> None:
        assert CapabilityRegistry([REFUND])[CapabilityId("payments", "refund")] is REFUND

    def test_by_dotted_string(self) -> None:
        """docs/API_DESIGN.md section 17 shows string lookup."""
        assert CapabilityRegistry([REFUND])["payments.refund"] is REFUND

    def test_containment_by_both_key_types(self) -> None:
        registry = CapabilityRegistry([REFUND])
        assert REFUND.id in registry
        assert "payments.refund" in registry
        assert "payments.missing" not in registry

    def test_containment_of_an_unparseable_string_is_false(self) -> None:
        """A malformed id is simply not registered, not an error."""
        assert "not-an-id" not in CapabilityRegistry([REFUND])

    def test_containment_of_an_unrelated_type_is_false(self) -> None:
        assert 42 not in CapabilityRegistry([REFUND])

    def test_a_miss_raises_unknown_capability(self) -> None:
        with pytest.raises(UnknownCapabilityError, match=re.escape("payments.missing")):
            CapabilityRegistry([REFUND])["payments.missing"]

    def test_a_miss_is_also_a_key_error(self) -> None:
        """So mapping-shaped code keeps working unchanged."""
        with pytest.raises(KeyError):
            CapabilityRegistry([REFUND])["payments.missing"]

    def test_the_miss_message_is_not_double_quoted(self) -> None:
        """`KeyError.__str__` reprs its argument; the override avoids that."""
        with pytest.raises(UnknownCapabilityError) as caught:
            CapabilityRegistry()["payments.missing"]
        assert str(caught.value).startswith("no capability registered as")


class TestDeterminism:
    def test_iteration_follows_registration_order(self) -> None:
        registry = CapabilityRegistry([GET_USER, REFUND, CAPTURE])
        assert list(registry) == [GET_USER.id, REFUND.id, CAPTURE.id]

    def test_the_frozen_view_keeps_that_order(self) -> None:
        frozen = CapabilityRegistry([GET_USER, REFUND, CAPTURE]).freeze()
        assert list(frozen) == [GET_USER.id, REFUND.id, CAPTURE.id]

    def test_order_is_not_alphabetical_by_accident(self) -> None:
        """Registration order, not sorted order. Manifests, OpenAPI documents
        and MCP tool lists derive from this and must not reshuffle."""
        frozen = CapabilityRegistry([define("z", "last"), define("a", "first")]).freeze()
        assert [str(key) for key in frozen] == ["z.last", "a.first"]


class TestFreezing:
    def test_freeze_returns_a_frozen_registry(self) -> None:
        assert isinstance(CapabilityRegistry().freeze(), FrozenCapabilityRegistry)

    def test_is_frozen_reports_the_phase(self) -> None:
        registry = CapabilityRegistry()
        assert not registry.is_frozen
        registry.freeze()
        assert registry.is_frozen

    def test_registering_after_freeze_raises(self) -> None:
        registry = CapabilityRegistry()
        registry.freeze()
        with pytest.raises(RegistryFrozenError, match="after the registry was frozen"):
            registry.register(REFUND)

    def test_freeze_is_idempotent(self) -> None:
        """A composition root should not have to track whether something
        else already froze the registry."""
        registry = CapabilityRegistry([REFUND])
        first = registry.freeze()
        second = registry.freeze()
        assert dict(first) == dict(second)

    def test_the_frozen_view_carries_the_definitions(self) -> None:
        frozen = CapabilityRegistry([REFUND, CAPTURE]).freeze()
        assert len(frozen) == 2
        assert frozen["payments.refund"] is REFUND

    def test_freezing_an_empty_registry_is_allowed(self) -> None:
        assert len(CapabilityRegistry().freeze()) == 0


class TestFrozenViewImmutability:
    def test_is_a_mapping(self) -> None:
        assert isinstance(CapabilityRegistry().freeze(), Mapping)

    def test_has_no_register_method(self) -> None:
        """The whole point of two types: misuse fails at type-check time."""
        assert not hasattr(CapabilityRegistry().freeze(), "register")

    def test_item_assignment_is_rejected(self) -> None:
        frozen: Any = CapabilityRegistry([REFUND]).freeze()
        with pytest.raises(TypeError):
            frozen["payments.capture"] = CAPTURE

    def test_the_underlying_mapping_cannot_be_mutated(self) -> None:
        """Reaching through the private attribute must not work either."""
        underlying: Any = CapabilityRegistry([REFUND]).freeze()._definitions
        with pytest.raises(TypeError):
            underlying[CAPTURE.id] = CAPTURE

    def test_it_is_detached_from_the_registry_that_produced_it(self) -> None:
        """A frozen view is a snapshot. Even if the source registry were
        somehow extended, the view already handed out must not change."""
        registry = CapabilityRegistry([REFUND])
        frozen = registry.freeze()
        registry._definitions[CAPTURE.id] = CAPTURE
        assert len(frozen) == 1
        assert "payments.capture" not in frozen


class TestIntrospection:
    def test_namespaces_lists_every_owner(self) -> None:
        frozen = CapabilityRegistry([REFUND, CAPTURE, GET_USER]).freeze()
        assert frozen.namespaces == frozenset({"payments", "users"})

    def test_namespaces_of_an_empty_registry_is_empty(self) -> None:
        assert CapabilityRegistry().freeze().namespaces == frozenset()

    def test_in_namespace_filters_and_keeps_order(self) -> None:
        frozen = CapabilityRegistry([REFUND, GET_USER, CAPTURE]).freeze()
        assert frozen.in_namespace("payments") == (REFUND, CAPTURE)

    def test_in_namespace_of_an_unknown_namespace_is_empty(self) -> None:
        assert CapabilityRegistry([REFUND]).freeze().in_namespace("billing") == ()

    def test_with_effect_finds_declaring_capabilities(self) -> None:
        destructive = define("accounts", "delete", effects={StandardEffect.DESTRUCTIVE})
        frozen = CapabilityRegistry([REFUND, destructive]).freeze()
        assert frozen.with_effect("destructive") == (destructive,)

    def test_with_effect_of_an_undeclared_effect_is_empty(self) -> None:
        assert CapabilityRegistry([REFUND]).freeze().with_effect("destructive") == ()

    def test_mapping_views_work(self) -> None:
        frozen = CapabilityRegistry([REFUND]).freeze()
        assert list(frozen.keys()) == [REFUND.id]
        assert list(frozen.values()) == [REFUND]
        assert list(frozen.items()) == [(REFUND.id, REFUND)]

    def test_get_returns_a_default_on_a_miss(self) -> None:
        assert CapabilityRegistry([REFUND]).freeze().get(CapabilityId("x", "y")) is None

    def test_repr_states_the_size_and_phase(self) -> None:
        registry = CapabilityRegistry([REFUND])
        assert "1 capabilities" in repr(registry)
        assert "open" in repr(registry)
        registry.freeze()
        assert "frozen" in repr(registry)


class TestConcurrency:
    def test_concurrent_registration_loses_nothing(self) -> None:
        """PRINCIPLES.md P6: startup is usually single-threaded, but
        "usually" is not a guarantee under free-threaded CPython."""
        registry = CapabilityRegistry()
        definitions = [define("bulk", f"capability_{index}") for index in range(200)]
        barrier = threading.Barrier(8)
        errors: list[Exception] = []

        def worker(chunk: list[CapabilityDefinition]) -> None:
            barrier.wait()
            for definition in chunk:
                try:
                    registry.register(definition)
                except Exception as exc:
                    errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(definitions[index::8],)) for index in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        assert len(registry) == 200

    def test_concurrent_duplicates_are_rejected_exactly_once(self) -> None:
        """Only one of several racing registrations of the same id wins."""
        registry = CapabilityRegistry()
        barrier = threading.Barrier(8)
        outcomes: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            barrier.wait()
            try:
                registry.register(REFUND)
                result = "registered"
            except DuplicateCapabilityError:
                result = "rejected"
            with lock:
                outcomes.append(result)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert outcomes.count("registered") == 1
        assert outcomes.count("rejected") == 7
        assert len(registry) == 1

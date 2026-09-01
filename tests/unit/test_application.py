"""E1.3 — the composition root and the @app.capability decorator."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest

from agnara import (
    Agnara,
    CapabilityId,
    Confirmation,
    DefinitionError,
    DuplicateCapabilityError,
    FrozenCapabilityRegistry,
    Idempotency,
    RegistryFrozenError,
    Risk,
    StandardEffect,
)


@pytest.fixture
def app() -> Agnara:
    return Agnara("payments")


class TestConstruction:
    def test_names_the_application(self) -> None:
        assert Agnara("payments").name == "payments"

    def test_starts_with_no_capabilities(self) -> None:
        assert len(Agnara("payments").capabilities) == 0

    def test_starts_uncompiled(self) -> None:
        assert not Agnara("payments").is_compiled

    @pytest.mark.parametrize("name", ["pay ments", "1payments", "pay-ments", "commerce.payments"])
    def test_rejects_a_name_that_cannot_be_a_namespace(self, name: str) -> None:
        """One rule for namespaces, shared with CapabilityId."""
        with pytest.raises(DefinitionError):
            Agnara(name)

    def test_rejects_an_empty_name(self) -> None:
        with pytest.raises(DefinitionError, match="must not be empty"):
            Agnara("")

    def test_rejects_a_non_string_name(self) -> None:
        with pytest.raises(DefinitionError, match="must be a string"):
            Agnara(123)  # ty: ignore[invalid-argument-type]

    def test_repr_states_the_name_size_and_phase(self) -> None:
        app = Agnara("payments")
        assert "payments" in repr(app)
        assert "open" in repr(app)
        app.compile()
        assert "compiled" in repr(app)


class TestBareDecorator:
    def test_registers_the_capability(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        assert "payments.refund" in app.capabilities

    def test_returns_the_function_unchanged(self, app: Agnara) -> None:
        """Registration is a side effect, not a transformation. A capability
        stays an ordinary callable a test can call directly."""

        def original() -> str:
            return "value"

        decorated = app.capability(original)
        assert decorated is original

    def test_the_function_remains_callable(self, app: Agnara) -> None:
        @app.capability
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_function_metadata_survives(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None:
            """Refund a payment."""

        assert refund.__name__ == "refund"
        assert refund.__doc__ == "Refund a payment."

    def test_the_handler_is_the_function(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        assert app.capabilities["payments.refund"].handler is refund


class TestCalledDecorator:
    def test_with_no_arguments(self, app: Agnara) -> None:
        @app.capability()
        def refund() -> None: ...

        assert "payments.refund" in app.capabilities

    def test_with_metadata(self, app: Agnara) -> None:
        @app.capability(risk="high")
        def refund() -> None: ...

        assert app.capabilities["payments.refund"].risk is Risk.HIGH

    def test_returns_the_function_unchanged(self, app: Agnara) -> None:
        def original() -> None: ...

        assert app.capability(risk="high")(original) is original

    def test_rejects_a_non_callable(self, app: Agnara) -> None:
        with pytest.raises(DefinitionError, match="expects a callable"):
            app.capability(risk="high")("not a function")  # ty: ignore[invalid-argument-type]


class TestIdentity:
    def test_defaults_to_app_name_and_function_name(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        assert app.capabilities["payments.refund"].id == CapabilityId("payments", "refund")

    def test_the_namespace_is_the_application_name(self) -> None:
        billing = Agnara("billing")

        @billing.capability
        def refund() -> None: ...

        assert str(billing.capabilities["billing.refund"].id) == "billing.refund"

    def test_an_explicit_name_overrides_the_function_name(self, app: Agnara) -> None:
        """RFC 0001 requires explicit ids so a Python rename does not silently
        change an id that policies and audit records refer to."""

        @app.capability(name="refund_payment")
        def refund_v2() -> None: ...

        assert "payments.refund_payment" in app.capabilities
        assert "payments.refund_v2" not in app.capabilities

    def test_an_invalid_explicit_name_is_rejected(self, app: Agnara) -> None:
        with pytest.raises(DefinitionError):

            @app.capability(name="not a valid name")
            def refund() -> None: ...

    def test_two_apps_do_not_collide_on_the_same_function_name(self) -> None:
        payments, users = Agnara("payments"), Agnara("users")

        @payments.capability
        def get() -> None: ...

        @users.capability
        def get() -> None:  # noqa: F811
            ...

        assert "payments.get" in payments.capabilities
        assert "users.get" in users.capabilities


class TestDescription:
    def test_defaults_to_the_docstring_summary(self, app: Agnara) -> None:
        """Agents need a description to choose a capability (P10), and
        requiring it to repeat the docstring would guarantee drift."""

        @app.capability
        def refund() -> None:
            """Refund a payment."""

        assert app.capabilities["payments.refund"].description == "Refund a payment."

    def test_takes_only_the_first_paragraph(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None:
            """Refund a payment.

            Implementation detail a caller does not need.
            """

        assert app.capabilities["payments.refund"].description == "Refund a payment."

    def test_an_explicit_description_wins(self, app: Agnara) -> None:
        @app.capability(description="Explicit wins")
        def refund() -> None:
            """Docstring loses."""

        assert app.capabilities["payments.refund"].description == "Explicit wins"

    def test_is_none_without_a_docstring(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        assert app.capabilities["payments.refund"].description is None


class TestMetadata:
    def test_accepts_every_field_from_the_golden_examples(self, app: Agnara) -> None:
        """docs/API_DESIGN.md section 12, declared through the decorator."""

        @app.capability(
            description="Permanently delete an account",
            scopes={"accounts:delete"},
            effects={StandardEffect.DESTRUCTIVE},
            risk="high",
            confirmation="required",
            idempotent=False,
        )
        async def delete_account() -> None: ...

        definition = app.capabilities["payments.delete_account"]
        assert definition.has_effect("destructive")
        assert definition.requires_scope("accounts:delete")
        assert definition.risk is Risk.HIGH
        assert definition.confirmation is Confirmation.REQUIRED
        assert definition.idempotency is Idempotency.NO

    def test_defaults_are_conservative(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        definition = app.capabilities["payments.refund"]
        assert definition.risk is Risk.LOW
        assert definition.confirmation is Confirmation.NEVER
        assert definition.effects == frozenset()
        assert definition.scopes == frozenset()

    def test_invalid_metadata_is_rejected_at_declaration(self, app: Agnara) -> None:
        """Fails at import time, not on first invocation (ADR 0005)."""
        with pytest.raises(DefinitionError, match="invalid risk"):

            @app.capability(risk="catastrophic")
            def refund() -> None: ...


class TestIdempotentBridge:
    def test_omitted_means_unknown_not_yes(self, app: Agnara) -> None:
        """RFC 0001: silence must never become a false idempotency claim."""

        @app.capability
        def refund() -> None: ...

        assert app.capabilities["payments.refund"].idempotency is Idempotency.UNKNOWN

    def test_true_maps_to_yes(self, app: Agnara) -> None:
        @app.capability(idempotent=True)
        def get() -> None: ...

        assert app.capabilities["payments.get"].idempotency is Idempotency.YES

    def test_false_maps_to_no(self, app: Agnara) -> None:
        @app.capability(idempotent=False)
        def charge() -> None: ...

        assert app.capabilities["payments.charge"].idempotency is Idempotency.NO

    def test_omitted_and_false_are_different(self, app: Agnara) -> None:
        @app.capability
        def silent() -> None: ...

        @app.capability(idempotent=False)
        def explicit() -> None: ...

        assert (
            app.capabilities["payments.silent"].idempotency
            is not app.capabilities["payments.explicit"].idempotency
        )


class TestAsyncAndSync:
    def test_an_async_function_registers(self, app: Agnara) -> None:
        @app.capability
        async def fetch() -> str:
            return "value"

        assert "payments.fetch" in app.capabilities

    def test_an_async_capability_is_still_awaitable(self, app: Agnara) -> None:
        """The decorator implies no execution semantics; EPIC 4 owns those."""

        @app.capability
        async def fetch() -> str:
            return "value"

        assert asyncio.run(fetch()) == "value"

    def test_a_callable_object_registers(self, app: Agnara) -> None:
        class Invocable:
            __name__ = "invocable"

            def __call__(self) -> None: ...

        invocable = Invocable()
        app.capability(invocable)
        assert app.capabilities["payments.invocable"].handler is invocable


class TestDuplicates:
    def test_the_same_name_twice_raises(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        with pytest.raises(DuplicateCapabilityError, match=re.escape("payments.refund")):

            @app.capability(name="refund")
            def other() -> None: ...

    def test_an_explicit_name_colliding_with_a_function_name_raises(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        with pytest.raises(DuplicateCapabilityError):

            @app.capability(name="refund")
            def refund_again() -> None: ...


class TestCompilation:
    def test_compile_returns_the_frozen_registry(self, app: Agnara) -> None:
        assert isinstance(app.compile(), FrozenCapabilityRegistry)

    def test_compile_marks_the_application_compiled(self, app: Agnara) -> None:
        app.compile()
        assert app.is_compiled

    def test_declaring_after_compile_raises(self, app: Agnara) -> None:
        app.compile()
        with pytest.raises(RegistryFrozenError):

            @app.capability
            def late() -> None: ...

    def test_the_compiled_view_carries_the_declarations(self, app: Agnara) -> None:
        @app.capability
        def refund() -> None: ...

        frozen = app.compile()
        assert frozen["payments.refund"].handler is refund

    def test_compile_preserves_declaration_order(self, app: Agnara) -> None:
        @app.capability
        def first() -> None: ...

        @app.capability
        def second() -> None: ...

        assert [str(key) for key in app.compile()] == ["payments.first", "payments.second"]


class TestGoldenApiExamples:
    def test_the_smallest_application(self) -> None:
        """docs/API_DESIGN.md sections 1 and 2."""
        app = Agnara("hello")

        @app.capability
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5
        assert "hello.add" in app.capabilities

    def test_introspection_reads_naturally(self) -> None:
        """docs/API_DESIGN.md section 17."""
        app = Agnara("users")

        @app.capability(effects={"database-write"}, idempotent=False)
        def create_user() -> None: ...

        definition: Any = app.capabilities["users.create_user"]
        assert definition.effects == frozenset({"database-write"})
        assert definition.idempotency is Idempotency.NO

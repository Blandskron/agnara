"""E1A.1/E1A.2: an app is a bounded context that owns its capability names.

`AppDescriptor` answers the first open question in RFC 0002, "exact app
descriptor API". `App` and `Agnara.include` are the runtime for ADR 0011's
decision that an app is a bounded context rather than a protocol type.

The defect this closes is concrete and was reproducible on `develop`: every
generated app registered into the project's single `Agnara`, so its
capabilities took the *project* name as their namespace and two apps from the
same scaffold collided on `get_record`. `test_two_apps_may_declare_the_same_name`
is the regression.
"""

from __future__ import annotations

import re

import pytest

from agnara import Agnara, App, AppDescriptor
from agnara.errors import (
    DefinitionError,
    DuplicateAppError,
    DuplicateCapabilityError,
    RegistryError,
    RegistryFrozenError,
)

# ---------------------------------------------------------------------------
# AppDescriptor
# ---------------------------------------------------------------------------


def test_a_descriptor_carries_the_identity_and_nothing_else() -> None:
    descriptor = AppDescriptor(
        name="payments",
        description="Money movement.",
        module="shop.apps.payments",
    )

    assert descriptor.name == "payments"
    assert descriptor.description == "Money movement."
    assert descriptor.module == "shop.apps.payments"
    assert str(descriptor) == "payments"


def test_a_descriptor_needs_only_a_name() -> None:
    descriptor = AppDescriptor(name="catalog")

    assert descriptor.description is None
    assert descriptor.module is None


def test_a_descriptor_is_frozen_and_hashable() -> None:
    """A project must be able to key on an app's identity."""
    descriptor = AppDescriptor(name="payments")

    with pytest.raises(Exception):  # noqa: B017 - frozen dataclasses raise FrozenInstanceError
        descriptor.name = "catalog"  # ty: ignore[invalid-assignment]

    assert {descriptor, AppDescriptor(name="payments")} == {descriptor}


def test_two_descriptors_with_the_same_contents_are_equal() -> None:
    assert AppDescriptor(name="payments", module="a.b") == AppDescriptor(
        name="payments", module="a.b"
    )


@pytest.mark.parametrize("name", ["", "shop.payments", "not an identifier", "9lives"])
def test_a_name_that_cannot_be_a_namespace_is_refused(name: str) -> None:
    """The name becomes a capability namespace, so it obeys that rule."""
    with pytest.raises(DefinitionError, match="app name"):
        AppDescriptor(name=name)


def test_a_non_string_name_is_refused() -> None:
    with pytest.raises(DefinitionError, match="must be a string"):
        AppDescriptor(name=object())  # ty: ignore[invalid-argument-type]


def test_a_non_string_description_is_refused() -> None:
    with pytest.raises(DefinitionError, match="description must be a string"):
        AppDescriptor(name="payments", description=42)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("module", ["", "shop..payments", "shop.9lives", "shop apps"])
def test_a_module_that_is_not_a_dotted_path_is_refused(module: str) -> None:
    with pytest.raises(DefinitionError, match="module"):
        AppDescriptor(name="payments", module=module)


def test_a_dotted_module_path_is_accepted() -> None:
    assert AppDescriptor(name="payments", module="shop.apps.payments").module


# ---------------------------------------------------------------------------
# App declaration
# ---------------------------------------------------------------------------


def test_an_app_namespaces_its_capabilities_with_its_own_name() -> None:
    payments = App("payments")

    @payments.capability(description="Refund.", idempotent=False)
    def refund(payment_id: str) -> str:
        return "refunded"

    assert [str(identifier) for identifier in payments.capabilities] == ["payments.refund"]


def test_the_bare_decorator_form_works() -> None:
    payments = App("payments")

    @payments.capability
    def refund(payment_id: str) -> str:
        """Refund a payment."""
        return "refunded"

    definition = payments.capabilities["payments.refund"]
    assert definition.description == "Refund a payment."


def test_the_decorator_returns_the_function_unchanged() -> None:
    """Declaration is a side effect, not a transformation."""
    payments = App("payments")

    def refund(payment_id: str) -> str:
        return "refunded"

    assert payments.capability(refund) is refund
    assert refund("p1") == "refunded"


def test_an_explicit_name_overrides_the_function_name() -> None:
    payments = App("payments")

    @payments.capability(name="issue_refund")
    def refund(payment_id: str) -> str:
        return "refunded"

    assert [str(identifier) for identifier in payments.capabilities] == ["payments.issue_refund"]


def test_a_non_callable_declaration_names_the_app_that_refused_it() -> None:
    payments = App("payments")

    with pytest.raises(DefinitionError, match=re.escape("@payments.capability expects a callable")):
        payments.capability(object())  # ty: ignore[invalid-argument-type]


def test_an_app_exposes_its_descriptor_and_name() -> None:
    payments = App("payments", description="Money movement.", module="shop.apps.payments")

    assert payments.name == "payments"
    assert payments.descriptor == AppDescriptor(
        name="payments", description="Money movement.", module="shop.apps.payments"
    )


def test_the_repr_says_what_the_app_holds() -> None:
    payments = App("payments")
    assert repr(payments) == "App('payments', 0 capabilities)"


def test_an_app_has_no_compile_of_its_own() -> None:
    """Freezing is a project-wide decision; see ADR 0005."""
    assert not hasattr(App("payments"), "compile")


# ---------------------------------------------------------------------------
# Agnara.include
# ---------------------------------------------------------------------------


def test_including_an_app_mounts_its_capabilities() -> None:
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "refunded"

    project = Agnara("shop")
    project.include(payments)

    assert [str(identifier) for identifier in project.compile()] == ["payments.refund"]


def test_two_apps_may_declare_the_same_name(capsys: pytest.CaptureFixture[str]) -> None:
    """The regression. Two apps from the same scaffold used to collide.

    Both templates give every app the same domain-neutral `get_record`, so
    before an app owned its namespace the scaffolder's own output did not
    compose with itself.
    """
    payments = App("payments")
    catalog = App("catalog")

    @payments.capability(description="Read one payments record.", idempotent=True)
    def get_record(reference: str) -> str:
        return "payment"

    @catalog.capability(name="get_record", description="Read one catalog record.", idempotent=True)
    def catalog_get_record(reference: str) -> str:
        return "item"

    project = Agnara("shop")
    project.include(payments)
    project.include(catalog)

    assert sorted(str(identifier) for identifier in project.compile()) == [
        "catalog.get_record",
        "payments.get_record",
    ]


def test_the_project_name_stays_out_of_the_capability_id() -> None:
    """Renaming a project must not change ids that policies refer to."""
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "refunded"

    ids = set()
    for project_name in ("shop", "storefront", "commerce"):
        project = Agnara(project_name)
        project.include(payments)
        ids |= {str(identifier) for identifier in project.compile()}

    assert ids == {"payments.refund"}


def test_including_returns_the_app() -> None:
    payments = App("payments")
    project = Agnara("shop")

    assert project.include(payments) is payments


def test_two_apps_with_the_same_name_are_refused() -> None:
    """Namespacing fixes accidental collisions, not a duplicated identity.

    E1A.3 reports this as a duplicated *app*, not as a capability clash: the
    capability is fine, and pointing at it would send a reader to investigate
    the wrong thing.
    """
    first, second = App("payments"), App("payments")

    @first.capability(description="One.")
    def refund(payment_id: str) -> str:
        return "a"

    @second.capability(name="refund", description="Two.")
    def other(payment_id: str) -> str:
        return "b"

    project = Agnara("shop")
    project.include(first)

    with pytest.raises(DuplicateAppError, match="a different app already claims that name"):
        project.include(second)


def test_including_after_compile_is_refused() -> None:
    """`include` is registration, so the freeze applies to it too."""
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "refunded"

    project = Agnara("shop")
    project.compile()

    with pytest.raises(RegistryFrozenError):
        project.include(payments)


def test_including_something_that_is_not_an_app_is_refused() -> None:
    project = Agnara("shop")

    with pytest.raises(DefinitionError, match="expects an App"):
        project.include(Agnara("other"))  # ty: ignore[invalid-argument-type]


def test_an_app_may_be_declared_and_inspected_without_a_project() -> None:
    """An app is testable on its own, which is why declaration is separate."""
    payments = App("payments")

    @payments.capability(description="Refund.", idempotent=False)
    def refund(payment_id: str) -> str:
        return "refunded"

    definition = payments.capabilities["payments.refund"]
    assert definition.description == "Refund."
    assert refund("p1") == "refunded"


def test_declaring_on_the_application_directly_still_works() -> None:
    """`include` adds a way to compose; it replaces nothing.

    The published `0.1.0a3` surface declares capabilities on `Agnara`, and
    that must keep working alongside apps.
    """
    project = Agnara("shop")

    @project.capability(description="Health probe.", idempotent=True)
    def ping() -> str:
        return "pong"

    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "refunded"

    project.include(payments)

    assert sorted(str(identifier) for identifier in project.compile()) == [
        "payments.refund",
        "shop.ping",
    ]


# ---------------------------------------------------------------------------
# E1A.3 — duplicate app identity
# ---------------------------------------------------------------------------


def test_two_apps_sharing_a_name_are_refused_even_with_no_capability_clash() -> None:
    """The case that used to pass silently.

    Two unrelated bounded contexts both called `payments`, declaring different
    capabilities, were accepted. The project then presented one `payments`
    namespace that was really two, and nothing said so.
    """
    first, second = App("payments"), App("payments")

    @first.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "a"

    @second.capability(description="Capture.")
    def capture(payment_id: str) -> str:
        return "b"

    project = Agnara("shop")
    project.include(first)

    with pytest.raises(DuplicateAppError, match="a different app already claims that name"):
        project.include(second)


def test_an_app_with_no_capabilities_still_claims_its_name() -> None:
    """Identity is the app's, not a side effect of what it happens to declare."""
    project = Agnara("shop")
    project.include(App("payments"))

    with pytest.raises(DuplicateAppError):
        project.include(App("payments"))


def test_including_the_same_app_twice_says_so() -> None:
    """Distinguishable from a different app claiming the name."""
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "refunded"

    project = Agnara("shop")
    project.include(payments)

    with pytest.raises(DuplicateAppError, match="it is already mounted"):
        project.include(payments)


def test_a_refused_include_leaves_the_project_unchanged() -> None:
    """A rejected app must not half-register its capabilities."""
    first, second = App("payments"), App("payments")

    @first.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "a"

    @second.capability(description="Capture.")
    def capture(payment_id: str) -> str:
        return "b"

    project = Agnara("shop")
    project.include(first)
    with pytest.raises(DuplicateAppError):
        project.include(second)

    assert [str(identifier) for identifier in project.compile()] == ["payments.refund"]
    assert list(project.apps) == ["payments"]


def test_a_duplicate_app_is_not_reported_as_a_capability_clash() -> None:
    """`DuplicateAppError` is its own type so a caller can tell them apart."""
    project = Agnara("shop")
    project.include(App("payments"))

    with pytest.raises(DuplicateAppError) as raised:
        project.include(App("payments"))

    assert not isinstance(raised.value, DuplicateCapabilityError)
    assert isinstance(raised.value, RegistryError)


def test_the_same_app_may_be_mounted_on_two_projects() -> None:
    """Identity is per project. An app is not owned by the first to mount it."""
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return "refunded"

    for project_name in ("shop", "storefront"):
        project = Agnara(project_name)
        project.include(payments)
        assert list(project.apps) == ["payments"]


# ---------------------------------------------------------------------------
# The mounted-app view
# ---------------------------------------------------------------------------


def test_apps_reports_what_was_mounted_in_order() -> None:
    project = Agnara("shop")
    payments, catalog = App("payments"), App("catalog")

    project.include(payments)
    project.include(catalog)

    assert list(project.apps) == ["payments", "catalog"]
    assert project.apps["payments"] is payments


def test_a_project_with_no_apps_reports_none() -> None:
    assert dict(Agnara("shop").apps) == {}


def test_the_apps_view_cannot_be_written_through() -> None:
    """Mounting is `include`; reaching through this must not work."""
    project = Agnara("shop")

    with pytest.raises(TypeError):
        project.apps["payments"] = App("payments")  # ty: ignore[invalid-assignment]


def test_declaring_on_the_application_does_not_create_an_app() -> None:
    """`Agnara.capability` is not an app; only `include` mounts one."""
    project = Agnara("shop")

    @project.capability(description="Health probe.", idempotent=True)
    def ping() -> str:
        return "pong"

    assert dict(project.apps) == {}
    assert [str(identifier) for identifier in project.compile()] == ["shop.ping"]


def test_a_late_include_reports_the_freeze_not_a_duplicate() -> None:
    """The freeze is the real cause, so it is checked first."""
    payments = App("payments")
    project = Agnara("shop")
    project.include(payments)
    project.compile()

    with pytest.raises(RegistryFrozenError):
        project.include(payments)


# ---------------------------------------------------------------------------
# E1A.6 — project compilation freezes mounted apps
# ---------------------------------------------------------------------------


def test_compiling_a_project_freezes_its_mounted_app() -> None:
    payments = App("payments")
    project = Agnara("shop")
    project.include(payments)

    project.compile()

    with pytest.raises(RegistryFrozenError, match="startup compilation"):

        @payments.capability(description="Too late.")
        def refund(payment_id: str) -> str:
            return payment_id


def test_compiling_a_project_freezes_an_empty_mounted_app() -> None:
    payments = App("payments")
    project = Agnara("shop")
    project.include(payments)

    assert len(project.compile()) == 0

    with pytest.raises(RegistryFrozenError):

        @payments.capability(description="Too late.")
        def refund(payment_id: str) -> str:
            return payment_id


def test_compiling_does_not_freeze_an_unmounted_app() -> None:
    payments = App("payments")

    Agnara("shop").compile()

    @payments.capability(description="Still open.")
    def refund(payment_id: str) -> str:
        return payment_id

    assert "payments.refund" in payments.capabilities


def test_a_frozen_shared_app_can_compile_in_another_project() -> None:
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return payment_id

    shop = Agnara("shop")
    storefront = Agnara("storefront")
    shop.include(payments)
    storefront.include(payments)

    assert list(shop.compile()) == list(storefront.compile())
    assert "payments.refund" in storefront.capabilities


def test_repeated_project_compilation_keeps_the_app_frozen() -> None:
    payments = App("payments")
    project = Agnara("shop")
    project.include(payments)

    first = project.compile()
    second = project.compile()

    assert list(first) == list(second)
    assert payments.capabilities.is_frozen


def test_capabilities_declared_before_mounting_are_in_the_compiled_project() -> None:
    payments = App("payments")

    @payments.capability(description="Refund.")
    def refund(payment_id: str) -> str:
        return payment_id

    project = Agnara("shop")
    project.include(payments)

    assert project.compile()["payments.refund"].handler is refund


def test_capabilities_declared_after_mounting_but_before_compile_are_included() -> None:
    """Registration stays open until project compilation, not mounting."""
    payments = App("payments")
    project = Agnara("shop")
    project.include(payments)

    @payments.capability(description="Declared during startup.")
    def refund(payment_id: str) -> str:
        return payment_id

    assert project.compile()["payments.refund"].handler is refund


def test_a_late_app_declaration_cannot_hide_a_project_capability() -> None:
    """Synchronization must retain ordinary duplicate-id diagnostics."""
    project = Agnara("shop")

    @project.capability(description="Project declaration.")
    def status() -> str:
        return "project"

    bounded_context = App("shop")
    project.include(bounded_context)

    @bounded_context.capability(name="status", description="App declaration.")
    def other_status() -> str:
        return "app"

    with pytest.raises(DuplicateCapabilityError, match=r"shop\.status"):
        project.compile()

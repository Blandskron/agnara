"""I1: one exposure model, and what it refuses.

These tests exercise the kernel half of RFC 0006 with no adapter present, so
they also state the boundary: the kernel validates identity, membership,
uniqueness and order, and validates no protocol grammar at all.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agnara import Agnara
from agnara.capability import CapabilityId
from agnara.exposure import (
    CompiledExposure,
    ExposureError,
    ExposureId,
    FrozenExposureRegistry,
    SurfaceCompilation,
    SurfaceId,
    compile_exposures,
)

HTTP = SurfaceId("http", "public")
MCP = SurfaceId("mcp", "agents")


def project() -> Agnara:
    app = Agnara("billing")

    @app.capability
    def refund(payment_id: str) -> str:
        return "refunded"

    @app.capability
    def statement(account_id: str) -> str:
        return "statement"

    @app.capability
    def internal_only() -> str:
        return "private"

    return app


def record(surface: SurfaceId, name: str, capability: str, **detail: object) -> CompiledExposure:
    return CompiledExposure.of(surface, name, CapabilityId.parse(capability), detail)


def surface(
    identity: SurfaceId,
    *exposures: CompiledExposure,
) -> SurfaceCompilation[str]:
    """A compilation whose runtime artifact is a stand-in for an adapter's."""
    return SurfaceCompilation(identity, "runtime-artifact", exposures)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("adapter", "name"),
    [("", "public"), ("http", ""), ("HTTP", "public"), ("http", "Public")],
)
def test_an_identifier_the_kernel_owns_is_validated(adapter: str, name: str) -> None:
    with pytest.raises(ExposureError):
        SurfaceId(adapter, name)


@pytest.mark.parametrize("adapter", ["http.public", "2fast", "web socket", "grpc/v1"])
def test_an_adapter_kind_is_one_lowercase_word(adapter: str) -> None:
    with pytest.raises(ExposureError, match="exposure adapter"):
        SurfaceId(adapter, "public")


def test_two_spellings_of_one_surface_cannot_both_exist() -> None:
    """Case folding is refused rather than normalized, so nothing is silent."""
    with pytest.raises(ExposureError, match="identifiers are lowercase"):
        SurfaceId("http", "Public")


def test_the_kernel_validates_no_protocol_grammar() -> None:
    """A method/path pair and a tool name are both just opaque local names."""
    assert ExposureId(HTTP, "GET /payments/{payment_id}").name == "GET /payments/{payment_id}"
    assert ExposureId(MCP, "billing.refund").name == "billing.refund"
    assert ExposureId(HTTP, "billing.refund").name == "billing.refund"


def test_a_local_name_with_control_characters_is_refused() -> None:
    with pytest.raises(ExposureError, match="control characters"):
        ExposureId(HTTP, "GET /a\nb")


def test_an_unbounded_local_name_is_refused() -> None:
    with pytest.raises(ExposureError, match="longer than"):
        ExposureId(HTTP, "x" * 513)


def test_an_exposure_id_reports_its_adapter_and_renders_readably() -> None:
    exposure_id = ExposureId(HTTP, "GET /refunds")
    assert exposure_id.adapter == "http"
    assert str(exposure_id) == "http:public GET /refunds"


# ---------------------------------------------------------------------------
# Compiled records
# ---------------------------------------------------------------------------


def test_a_record_names_a_capability_and_a_target_and_nothing_runnable() -> None:
    exposure = record(HTTP, "POST /refunds", "billing.refund", method="POST", path="/refunds")

    assert exposure.capability_id == CapabilityId("billing", "refund")
    assert exposure.surface == HTTP
    assert not hasattr(exposure, "plan")
    assert not hasattr(exposure, "handler")


def test_adapter_detail_stays_plain_json_data() -> None:
    """A record cannot carry a route object, a server or a callback."""
    with pytest.raises(ExposureError, match="non-JSON value"):
        record(HTTP, "POST /refunds", "billing.refund", binder=object())


def test_adapter_detail_is_canonical_so_records_compare_and_hash() -> None:
    first = record(HTTP, "POST /refunds", "billing.refund", method="POST", path="/refunds")
    second = record(HTTP, "POST /refunds", "billing.refund", path="/refunds", method="POST")

    assert first == second
    assert hash(first) == hash(second)


def test_an_adapter_cannot_claim_the_kernel_owned_surface_detail_key() -> None:
    with pytest.raises(ExposureError, match="surface identity is derived"):
        CompiledExposure.of(
            HTTP,
            "POST /refunds",
            CapabilityId("billing", "refund"),
            {"surface": "elsewhere"},
        )


def test_published_detail_carries_surface_identity_without_storing_it() -> None:
    """RFC 0006 section 13: surface identity must not be silently discarded."""
    exposure = record(HTTP, "POST /refunds", "billing.refund", method="POST")

    assert exposure.published_detail() == {"method": "POST", "surface": "public"}
    assert "surface" not in exposure.detail


def test_a_record_is_immutable() -> None:
    exposure = record(HTTP, "POST /refunds", "billing.refund")

    with pytest.raises(FrozenInstanceError):
        exposure.capability_id = CapabilityId("billing", "statement")  # ty: ignore[invalid-assignment]


def test_detail_that_is_not_a_json_object_is_refused() -> None:
    with pytest.raises(ExposureError, match="must be a JSON object"):
        CompiledExposure(ExposureId(HTTP, "x"), CapabilityId("billing", "refund"), "[1, 2]")


def test_detail_that_is_not_json_at_all_is_refused() -> None:
    with pytest.raises(ExposureError, match="not valid JSON"):
        CompiledExposure(ExposureId(HTTP, "x"), CapabilityId("billing", "refund"), "{oops")


# ---------------------------------------------------------------------------
# Surface compilation
# ---------------------------------------------------------------------------


def test_a_compilation_carries_the_runtime_artifact_with_its_records() -> None:
    """Atomic derivation: the two cannot be obtained separately and drift."""
    exposure = record(HTTP, "POST /refunds", "billing.refund")
    compilation = surface(HTTP, exposure)

    assert compilation.runtime == "runtime-artifact"
    assert compilation.exposures == (exposure,)


def test_one_compiler_owns_one_surface() -> None:
    with pytest.raises(ExposureError, match="one compiler owns one surface"):
        surface(HTTP, record(MCP, "billing.refund", "billing.refund"))


def test_a_compiler_cannot_emit_one_local_name_twice() -> None:
    with pytest.raises(ExposureError, match="twice"):
        surface(
            HTTP,
            record(HTTP, "POST /refunds", "billing.refund"),
            record(HTTP, "POST /refunds", "billing.statement"),
        )


def test_a_compilation_refuses_a_non_record() -> None:
    with pytest.raises(ExposureError, match="CompiledExposure values"):
        SurfaceCompilation(HTTP, "runtime", ("POST /refunds",))  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# Project aggregation
# ---------------------------------------------------------------------------


def test_one_capability_on_one_surface() -> None:
    app = project()
    exposures = compile_exposures(
        app.compile(),
        [surface(HTTP, record(HTTP, "POST /refunds", "billing.refund", method="POST"))],
    )

    assert len(exposures) == 1
    assert exposures.surfaces == (HTTP,)
    assert exposures.transports(CapabilityId("billing", "refund")) == ("http",)


def test_one_capability_on_two_adapters_yields_two_records() -> None:
    app = project()
    refund = CapabilityId("billing", "refund")
    exposures = compile_exposures(
        app.compile(),
        [
            surface(HTTP, record(HTTP, "POST /refunds", "billing.refund")),
            surface(MCP, record(MCP, "billing.refund", "billing.refund")),
        ],
    )

    assert len(exposures.for_capability(refund)) == 2
    assert exposures.transports(refund) == ("http", "mcp")


def test_a_capability_exposed_nowhere_is_an_ordinary_state() -> None:
    """Direct Python invocation is a first-class way to reach a capability."""
    app = project()
    exposures = compile_exposures(
        app.compile(),
        [surface(HTTP, record(HTTP, "POST /refunds", "billing.refund"))],
    )

    assert exposures.for_capability(CapabilityId("billing", "internal_only")) == ()
    assert exposures.transports(CapabilityId("billing", "internal_only")) == ()


def test_two_surfaces_may_reuse_one_local_name() -> None:
    """A public and an admin HTTP API are two surfaces, not a collision."""
    app = project()
    admin = SurfaceId("http", "admin")
    exposures = compile_exposures(
        app.compile(),
        [
            surface(HTTP, record(HTTP, "POST /refunds", "billing.refund")),
            surface(admin, record(admin, "POST /refunds", "billing.statement")),
        ],
    )

    assert len(exposures) == 2
    assert exposures[ExposureId(HTTP, "POST /refunds")].capability_id.name == "refund"
    assert exposures[ExposureId(admin, "POST /refunds")].capability_id.name == "statement"


def test_a_duplicate_full_identity_fails_closed() -> None:
    """Last-write-wins would route one wire name to the wrong capability."""
    with pytest.raises(ExposureError, match="duplicate exposure"):
        FrozenExposureRegistry(
            [
                record(HTTP, "POST /refunds", "billing.refund"),
                record(HTTP, "POST /refunds", "billing.statement"),
            ]
        )


def test_one_surface_cannot_be_compiled_twice() -> None:
    app = project()
    with pytest.raises(ExposureError, match="compiled twice"):
        compile_exposures(
            app.compile(),
            [
                surface(HTTP, record(HTTP, "POST /refunds", "billing.refund")),
                surface(HTTP, record(HTTP, "GET /statements", "billing.statement")),
            ],
        )


def test_an_exposure_cannot_advertise_a_capability_the_project_lacks() -> None:
    """Otherwise a snapshot describes something that does not exist."""
    app = project()
    with pytest.raises(ExposureError, match="did not compile"):
        compile_exposures(
            app.compile(),
            [surface(HTTP, record(HTTP, "POST /audit", "billing.audit"))],
        )


def test_aggregation_requires_the_frozen_capability_registry() -> None:
    app = project()
    with pytest.raises(ExposureError, match="frozen capability registry"):
        compile_exposures(app.capabilities, [])  # ty: ignore[invalid-argument-type]


def test_aggregation_refuses_something_that_is_not_a_compilation() -> None:
    app = project()
    with pytest.raises(ExposureError, match="SurfaceCompilation values"):
        compile_exposures(app.compile(), [record(HTTP, "x", "billing.refund")])  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# Determinism and immutability
# ---------------------------------------------------------------------------


def test_ordering_is_aggregation_order_and_repeats_exactly() -> None:
    app = project()
    frozen = app.compile()

    def build() -> FrozenExposureRegistry:
        return compile_exposures(
            frozen,
            [
                surface(
                    HTTP,
                    record(HTTP, "POST /refunds", "billing.refund"),
                    record(HTTP, "GET /statements", "billing.statement"),
                ),
                surface(MCP, record(MCP, "billing.refund", "billing.refund")),
            ],
        )

    expected = [
        "http:public POST /refunds",
        "http:public GET /statements",
        "mcp:agents billing.refund",
    ]
    assert [str(key) for key in build()] == expected
    assert [str(key) for key in build()] == expected


def test_surface_order_follows_aggregation_not_hashing() -> None:
    app = project()
    frozen = app.compile()
    reversed_order = compile_exposures(
        frozen,
        [
            surface(MCP, record(MCP, "billing.refund", "billing.refund")),
            surface(HTTP, record(HTTP, "POST /refunds", "billing.refund")),
        ],
    )

    assert reversed_order.surfaces == (MCP, HTTP)


def test_the_registry_exposes_no_way_to_add_or_remove_an_exposure() -> None:
    """There is no open collecting registry, so there is no late registration."""
    app = project()
    exposures = compile_exposures(
        app.compile(),
        [surface(HTTP, record(HTTP, "POST /refunds", "billing.refund"))],
    )

    for mutator in ("register", "add", "contribute", "freeze", "__setitem__", "__delitem__"):
        assert not hasattr(exposures, mutator), mutator


def test_mutating_the_frozen_registry_through_its_internals_fails() -> None:
    app = project()
    exposures = compile_exposures(
        app.compile(),
        [surface(HTTP, record(HTTP, "POST /refunds", "billing.refund"))],
    )

    with pytest.raises(TypeError):
        exposures._exposures[ExposureId(MCP, "x")] = record(  # ty: ignore[invalid-assignment]
            MCP, "x", "billing.refund"
        )
    with pytest.raises(AttributeError):
        exposures.injected = ()  # ty: ignore[unresolved-attribute]


def test_an_unknown_exposure_lookup_names_what_was_asked_for() -> None:
    app = project()
    exposures = compile_exposures(app.compile(), [])

    with pytest.raises(ExposureError, match="no exposure compiled as mcp:agents nope"):
        exposures[ExposureId(MCP, "nope")]


def test_aggregating_the_same_compilations_again_is_equivalent() -> None:
    app = project()
    frozen = app.compile()
    compilation = surface(HTTP, record(HTTP, "POST /refunds", "billing.refund"))

    first = compile_exposures(frozen, [compilation])
    second = compile_exposures(frozen, [compilation])

    assert dict(first) == dict(second)


def test_on_surface_reports_one_surface_in_emission_order() -> None:
    app = project()
    exposures = compile_exposures(
        app.compile(),
        [
            surface(
                HTTP,
                record(HTTP, "POST /refunds", "billing.refund"),
                record(HTTP, "GET /statements", "billing.statement"),
            ),
            surface(MCP, record(MCP, "billing.refund", "billing.refund")),
        ],
    )

    assert [exposure.id.name for exposure in exposures.on_surface(HTTP)] == [
        "POST /refunds",
        "GET /statements",
    ]
    assert [exposure.id.name for exposure in exposures.on_surface(MCP)] == ["billing.refund"]


def test_the_registry_repr_summarizes_without_dumping_records() -> None:
    app = project()
    exposures = compile_exposures(
        app.compile(),
        [surface(HTTP, record(HTTP, "POST /refunds", "billing.refund"))],
    )

    assert repr(exposures) == "FrozenExposureRegistry(1 exposures across 1 surfaces)"

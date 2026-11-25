"""Tests for EVT-03 inbound exposure compilation and strict CloudEvents decoding."""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator

import pytest

from agnara import (
    Agnara,
    AnonymousPrincipal,
    CapabilityDefinition,
    CapabilityId,
    Confirmation,
    ConfirmationEvidence,
    ConfirmationVerdict,
    Principal,
)
from agnara.di import DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation
from agnara.exposure import compile_exposures
from agnara.policy import Policy, PolicyResult, PolicySuccess
from agnara_events._envelope import (
    CLOUDEVENTS_JSON_CONTENT_TYPE,
    MAX_BODY_BYTES,
    MAX_JSON_DEPTH,
    _decode_cloudevent,
    _EnvelopeError,
)
from agnara_events._exposure import (
    _compile_event_surface,
    _compile_inbound_event,
    _declare_inbound_event,
    _EventsDefinitionError,
)


def _make_event_bytes(
    overrides: dict[str, object] | None = None, *, extra: dict[str, object] | None = None
) -> bytes:
    payload: dict[str, object] = {
        "specversion": "1.0",
        "id": "evt-1",
        "source": "/inventory/node-1",
        "type": "example.inventory.snapshot.v1",
        "datacontenttype": "application/json",
        "data": {"sku": "A-1", "revision": 9007199254740993},
    }
    if overrides:
        payload.update(overrides)
    if extra:
        payload.update(extra)
    return json.dumps(payload).encode("utf-8")


def test_exposure_declaration_compilation_and_surface_record() -> None:
    app = Agnara("inventory")

    @app.capability(scopes=("inventory:write",), output=str)
    async def apply(sku: str) -> str:
        return sku

    compiled_app = app.compile()
    definition = compiled_app["inventory.apply"]
    plan = ExecutionPlan.compile(definition, DIRegistry())
    principal = Principal("evt-worker", scopes={"inventory:write"})

    exposure = _declare_inbound_event(
        definition,
        subscription_id="inventory-apply",
        event_type="example.inventory.snapshot.v1",
        principal=principal,
        public_address="inventory.snapshot.v1",
        summary="Apply inventory snapshot",
    )
    binding = _compile_inbound_event(exposure, {definition.id: plan})
    compilation = _compile_event_surface(binding)
    registry = compile_exposures(compiled_app, [compilation])

    assert binding.surface.adapter == "events"
    assert binding.surface.name == "default"
    assert len(registry.for_capability(definition.id)) == 1


def test_exposure_rejects_streaming_confirmation_anonymous_and_url_addresses() -> None:
    app = Agnara("jobs")

    @app.capability(streaming=True, output=int)
    async def stream_items() -> AsyncIterator[int]:
        yield 1

    @app.capability(confirmation=Confirmation.REQUIRED, output=str)
    async def confirm_op(x: str) -> str:
        return x

    class DummyPolicy(Policy):
        async def evaluate(self, context: ExecutionContext) -> PolicyResult:
            return PolicySuccess()

    class DummyVerifier:
        async def verify(
            self,
            evidence: ConfirmationEvidence,
            *,
            capability_id: CapabilityId,
            invocation: Invocation,
            principal: Principal,
        ) -> ConfirmationVerdict:
            return ConfirmationVerdict.VALID

    async def policy_handler(x: str) -> str:
        return x

    policy_confirm_def = CapabilityDefinition(
        id=CapabilityId.parse("jobs.policy_confirm_op"),
        handler=policy_handler,
        confirmation=Confirmation.POLICY,
        policies=(DummyPolicy(),),
        output=str,
    )

    @app.capability(output=str)
    async def plain(x: str) -> str:
        return x

    compiled_app = app.compile()
    principal = Principal("svc")
    plans = {
        compiled_app["jobs.stream_items"].id: ExecutionPlan.compile(
            compiled_app["jobs.stream_items"], DIRegistry()
        ),
        compiled_app["jobs.confirm_op"].id: ExecutionPlan.compile(
            compiled_app["jobs.confirm_op"],
            DIRegistry(),
            confirmation_verifier=DummyVerifier(),
        ),
        policy_confirm_def.id: ExecutionPlan.compile(policy_confirm_def, DIRegistry()),
        compiled_app["jobs.plain"].id: ExecutionPlan.compile(
            compiled_app["jobs.plain"], DIRegistry()
        ),
    }

    with pytest.raises(_EventsDefinitionError, match="streaming"):
        _compile_inbound_event(
            _declare_inbound_event(
                compiled_app["jobs.stream_items"],
                subscription_id="s1",
                event_type="e.stream",
                principal=principal,
            ),
            plans,
        )

    for target_cap in (compiled_app["jobs.confirm_op"], policy_confirm_def):
        with pytest.raises(_EventsDefinitionError, match="confirmation"):
            _compile_inbound_event(
                _declare_inbound_event(
                    target_cap,
                    subscription_id="s2",
                    event_type="e.confirm",
                    principal=principal,
                ),
                plans,
            )

    with pytest.raises(_EventsDefinitionError, match="no compiled ExecutionPlan"):
        _compile_inbound_event(
            _declare_inbound_event(
                CapabilityId.parse("jobs.missing"),
                subscription_id="s3",
                event_type="e.missing",
                principal=principal,
            ),
            plans,
        )

    with pytest.raises(_EventsDefinitionError, match="Principal"):
        _declare_inbound_event(
            compiled_app["jobs.plain"],
            subscription_id="s4",
            event_type="e.anon",
            principal=AnonymousPrincipal(),
        )

    for bad_addr in ("amqp://user:pass@broker/v", "user@channel", "channel?x=1", "channel#frag"):
        with pytest.raises(_EventsDefinitionError, match="logical channel"):
            _declare_inbound_event(
                compiled_app["jobs.plain"],
                subscription_id="s5",
                event_type="e.addr",
                principal=principal,
                public_address=bad_addr,
            )


def test_decode_cloudevent_preserves_exact_integer_and_ignores_extensions() -> None:
    raw = _make_event_bytes(
        extra={
            "time": "2026-11-24T12:00:00Z",
            "xextension": "ignored",
            "scope": "admin:all",
        }
    )
    decoded = _decode_cloudevent(
        raw,
        CLOUDEVENTS_JSON_CONTENT_TYPE,
        expected_type="example.inventory.snapshot.v1",
    )
    assert decoded.specversion == "1.0"
    assert decoded.event_id == "evt-1"
    assert decoded.source == "/inventory/node-1"
    assert decoded.data["revision"] == 9007199254740993
    assert type(decoded.data["revision"]) is int
    assert "xextension" not in decoded.data
    assert "scope" not in decoded.data


def test_decode_cloudevent_body_size_boundary_65536() -> None:
    prefix = b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"pad":"'
    suffix = b'"}}'
    exact_pad = b"a" * (MAX_BODY_BYTES - len(prefix) - len(suffix))
    exact_body = prefix + exact_pad + suffix
    assert len(exact_body) == MAX_BODY_BYTES

    decoded = _decode_cloudevent(
        exact_body,
        CLOUDEVENTS_JSON_CONTENT_TYPE,
        expected_type="e.v1",
    )
    assert len(decoded.data["pad"]) == len(exact_pad)

    # 65,537 bytes with invalid UTF-8 at the end must be refused before UTF-8 decode.
    over_body = exact_body[:-1] + b"\xff\xff"
    assert len(over_body) == MAX_BODY_BYTES + 1
    with pytest.raises(_EnvelopeError) as exc_info:
        _decode_cloudevent(over_body, CLOUDEVENTS_JSON_CONTENT_TYPE, expected_type="e.v1")
    assert exc_info.value.category == "body_too_large"


def test_decode_cloudevent_json_depth_boundary_32() -> None:
    def nested_event(depth: int) -> bytes:
        # Depth 1 = root object; depth 2 = data object; remaining levels inside "x".
        inner = '{"leaf":1}'
        for _ in range(depth - 3):
            inner = f'{{"n":{inner}}}'
        return (
            '{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"x":' + inner + "}}"
        ).encode("utf-8")

    ok_body = nested_event(MAX_JSON_DEPTH)
    decoded = _decode_cloudevent(ok_body, CLOUDEVENTS_JSON_CONTENT_TYPE, expected_type="e.v1")
    assert isinstance(decoded.data["x"], dict)

    too_deep = nested_event(MAX_JSON_DEPTH + 1)
    with pytest.raises(_EnvelopeError) as exc_info:
        _decode_cloudevent(too_deep, CLOUDEVENTS_JSON_CONTENT_TYPE, expected_type="e.v1")
    assert exc_info.value.category == "json_nesting_depth"


@pytest.mark.parametrize(
    ("raw_body", "content_type", "expected_category"),
    [
        (b'{"specversion":"1.0"}', "application/json", "unsupported_content_type"),
        (b'{"specversion":"1.0"}', None, "unsupported_content_type"),
        (b"\xff\xfe", CLOUDEVENTS_JSON_CONTENT_TYPE, "invalid_utf8"),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"a":1},"data":{"a":2}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "duplicate_key",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"a":1,"a":2}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "duplicate_key",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"x":NaN}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "non_finite_number",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"x":Infinity}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "non_finite_number",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"x":1e309}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "non_finite_number",
        ),
        (
            b'[{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{}}]',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "invalid_envelope",
        ),
        (
            b'{"specversion":"0.3","id":"1","source":"/s","type":"e.v1","data":{}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "invalid_specversion",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"other.v1","data":{}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "type_mismatch",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data_base64":"e30=","data":{}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "unsupported_data_base64",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","datacontenttype":"text/plain","data":{}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "unsupported_datacontenttype",
        ),
        (
            b'{"specversion":"1.0","id":"","source":"/s","type":"e.v1","data":{}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "invalid_id",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"bad source","type":"e.v1","data":{}}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "invalid_source",
        ),
        (
            b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":[1,2]}',
            CLOUDEVENTS_JSON_CONTENT_TYPE,
            "invalid_data",
        ),
    ],
)
def test_decode_cloudevent_rejections_omit_payload_text(
    raw_body: bytes, content_type: str | None, expected_category: str
) -> None:
    with pytest.raises(_EnvelopeError) as exc_info:
        _decode_cloudevent(raw_body, content_type, expected_type="e.v1")
    assert exc_info.value.category == expected_category
    assert str(exc_info.value) == expected_category


def test_decode_cloudevent_rejects_oversized_integer_digits() -> None:
    max_digits = sys.get_int_max_str_digits()
    huge_int = "9" * (max_digits + 1)
    body = (
        f'{{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{{"n":{huge_int}}}}}'
    ).encode()
    with pytest.raises(_EnvelopeError) as exc_info:
        _decode_cloudevent(body, CLOUDEVENTS_JSON_CONTENT_TYPE, expected_type="e.v1")
    assert exc_info.value.category == "integer_bounds"


@pytest.mark.parametrize(
    "raw_json",
    [
        b'{"specversion":"1.0","id":"bad\\uD800","source":"/s","type":"e.v1","data":{}}',
        b'{"specversion":"1.0","id":"1","source":"/s\\uDC00","type":"e.v1","data":{}}',
        b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"k\\uD800":1}}',
        b'{"specversion":"1.0","id":"1","source":"/s","type":"e.v1","data":{"nested":["\\uDFFF"]}}',
    ],
)
def test_decode_cloudevent_rejects_unpaired_surrogates(raw_json: bytes) -> None:
    with pytest.raises(_EnvelopeError) as exc_info:
        _decode_cloudevent(raw_json, CLOUDEVENTS_JSON_CONTENT_TYPE, expected_type="e.v1")
    assert exc_info.value.category == "invalid_utf8"


@pytest.mark.parametrize(
    "bad_sub_id",
    ["orders/v1", "orders~1", "orders sub", "a" * 129, "sub\ud800", "orders#1"],
)
def test_exposure_rejects_unsafe_subscription_id(bad_sub_id: str) -> None:
    with pytest.raises(_EventsDefinitionError):
        _declare_inbound_event(
            CapabilityId.parse("jobs.plain"),
            subscription_id=bad_sub_id,
            event_type="e.v1",
            principal=Principal("svc"),
        )

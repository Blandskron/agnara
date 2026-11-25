"""Bounded adversarial fuzzing for agnara-events envelope, AsyncAPI, and consumer."""

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator
from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st
from jsonschema import Draft7Validator

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import ExecutionPlan
from agnara_events import (
    CLOUDEVENTS_JSON_CONTENT_TYPE,
    AsyncAPIExportError,
    ConsumerBudgets,
    ConsumerDiagnostic,
    Delivery,
    compile_inbound_event,
    consume_inbound_events,
    declare_inbound_event,
)
from agnara_events._asyncapi import _translate_schema_to_draft07
from agnara_events._envelope import _decode_cloudevent, _EnvelopeError

SECRET = "private-events-fuzz-diagnostic"


class _AdversarialStore:
    pass


class _AdversarialDelivery:
    def __init__(self, body: bytes, content_type: str | None) -> None:
        self.body = body
        self.content_type = content_type
        self.settlements: list[str] = []

    async def acknowledge(self) -> None:
        self.settlements.append("acknowledge")

    async def reject(self) -> None:
        self.settlements.append("reject")

    async def release(self) -> None:
        self.settlements.append("release")


class _AdversarialSource:
    def __init__(self, deliveries: list[_AdversarialDelivery]) -> None:
        self._queue: asyncio.Queue[Delivery | None] = asyncio.Queue()
        for item in deliveries:
            self._queue.put_nowait(item)
        self._queue.put_nowait(None)

    async def receive(self) -> Delivery | None:
        return await self._queue.get()

    async def stop_receiving(self) -> None:
        return None


_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-10_000, 10_000),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=12),
)

_json_values = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=6), children, max_size=4),
    ),
    max_leaves=10,
)

_wire_bodies = st.one_of(
    st.binary(max_size=256),
    st.text(max_size=128).map(lambda s: s.encode("utf-8", errors="surrogatepass")),
    _json_values.map(lambda val: json.dumps(val, allow_nan=True).encode("utf-8")),
)

_content_types = st.one_of(
    st.none(),
    st.just(CLOUDEVENTS_JSON_CONTENT_TYPE),
    st.just("application/json"),
    st.text(max_size=24),
)


def _deep_json_bytes(depth: int) -> bytes:
    inner = "1"
    for _ in range(depth):
        inner = f'{{"a":{inner}}}'
    return (
        '{"specversion":"1.0","id":"1","source":"/s","type":"evt.fuzz.v1","data":' + inner + "}"
    ).encode()


@settings(max_examples=200)
@given(body=_wire_bodies, content_type=_content_types)
@example(
    body=b'{"specversion":"1.0","id":"1","source":"/s","type":"evt.fuzz.v1","data":{"x":"\\uD800"}}',
    content_type=CLOUDEVENTS_JSON_CONTENT_TYPE,
)
@example(
    body=b'{"specversion":"1.0","id":"1","source":"/s","type":"evt.fuzz.v1","data":{"x":1e309}}',
    content_type=CLOUDEVENTS_JSON_CONTENT_TYPE,
)
@example(
    body=b'{"specversion":"1.0","id":"1","source":"/s","type":"evt.fuzz.v1","data":[{"a":1,"a":2}]}',
    content_type=CLOUDEVENTS_JSON_CONTENT_TYPE,
)
@example(body=_deep_json_bytes(33), content_type=CLOUDEVENTS_JSON_CONTENT_TYPE)
def test_cloudevent_decoder_never_raises_unhandled_or_emits_surrogates(
    body: bytes, content_type: str | None
) -> None:
    try:
        decoded = _decode_cloudevent(body, content_type, expected_type="evt.fuzz.v1")
    except _EnvelopeError as error:
        assert error.category
        assert str(error) == error.category
        return

    encoded = json.dumps(dict(decoded.data), allow_nan=False).encode("utf-8", errors="strict")
    assert isinstance(encoded, bytes)
    assert decoded.specversion == "1.0"
    assert decoded.event_type == "evt.fuzz.v1"


_schema_keys = st.sampled_from(
    [
        "type",
        "enum",
        "const",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "prefixItems",
        "$ref",
        "anyOf",
        "oneOf",
        "unknown",
    ]
)

_schema_nodes = st.recursive(
    st.one_of(
        st.booleans(),
        st.none(),
        st.sampled_from(["string", "integer", "number", "boolean", "object", "array", "null"]),
        st.floats(allow_nan=True, allow_infinity=True),
        st.integers(-5, 10),
        st.text(max_size=8),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_schema_keys, children, max_size=5),
    ),
    max_leaves=12,
)


def _deep_schema(depth: int) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "string"}
    for _ in range(depth):
        node = {"type": "object", "properties": {"n": node}}
    return node


@settings(max_examples=200)
@given(schema=_schema_nodes)
@example(schema=_deep_schema(40))
@example(schema={"type": "string", "const": "\ud800"})
@example(schema={"type": "number", "minimum": math.nan})
@example(schema={"type": "integer", "minimum": 10, "maximum": 1})
def test_draft07_translator_never_raises_unhandled_and_outputs_valid_schema(
    schema: object,
) -> None:
    try:
        translated = _translate_schema_to_draft07(schema)
    except AsyncAPIExportError:
        return

    Draft7Validator.check_schema(translated)
    serialized = json.dumps(translated, allow_nan=False).encode("utf-8", errors="strict")
    assert isinstance(serialized, bytes)


@settings(max_examples=50)
@given(
    deliveries=st.lists(
        st.tuples(_wire_bodies, _content_types),
        min_size=1,
        max_size=5,
    )
)
def test_consumer_settles_every_adversarial_delivery_once_without_leaks(
    deliveries: list[tuple[bytes, str | None]],
) -> None:
    async def run() -> None:
        acquisitions = 0
        app = Agnara("fuzz")

        @provider(scope=Scope.INVOCATION)
        async def open_store() -> AsyncIterator[_AdversarialStore]:
            nonlocal acquisitions
            acquisitions += 1
            yield _AdversarialStore()

        @app.capability(scopes=("fuzz:run",), output=str)
        async def handle(value: str, store: _AdversarialStore) -> str:
            if value == "boom":
                raise RuntimeError(SECRET)
            return value

        compiled = app.compile()
        deps = DIRegistry()
        deps.bind(_AdversarialStore, open_store)
        cap_def = compiled["fuzz.handle"]
        plan = ExecutionPlan.compile(cap_def, deps)
        container = DIContainer(deps)
        binding = compile_inbound_event(
            declare_inbound_event(
                cap_def,
                subscription_id="fuzz-sub",
                event_type="evt.fuzz.v1",
                principal=Principal("fuzz-worker", scopes={"fuzz:run"}),
            ),
            {cap_def.id: plan},
        )

        batch = [_AdversarialDelivery(body, content_type) for body, content_type in deliveries]
        before = asyncio.all_tasks()
        try:
            diagnostics: tuple[ConsumerDiagnostic, ...] = await consume_inbound_events(
                binding,
                container,
                _AdversarialSource(batch),
                budgets=ConsumerBudgets(attempt_seconds=2.0, shutdown_seconds=0.5),
                stop_event=asyncio.Event(),
            )
        finally:
            await container.aclose()

        assert asyncio.all_tasks() == before
        assert len(diagnostics) == len(batch)
        for item, diag in zip(batch, diagnostics, strict=True):
            assert len(item.settlements) == 1
            assert item.settlements[0] in {"acknowledge", "reject", "release"}
            assert diag.settlement == item.settlements[0]
            assert SECRET not in str(diag)

    asyncio.run(run())

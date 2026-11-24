"""Tests for EVT-03 opt-in AsyncAPI 3.1.0 projection and Draft-07 translation."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from jsonschema import Draft7Validator

from agnara import Agnara, Principal
from agnara.di import DIRegistry, provider
from agnara.execution import ExecutionPlan
from agnara_events._asyncapi import (
    ASYNCAPI_VERSION,
    DRAFT_07_SCHEMA_FORMAT,
    _AsyncAPIExportError,
    _AsyncAPIInfo,
    _project_asyncapi,
    _translate_schema_to_draft07,
)
from agnara_events._envelope import CLOUDEVENTS_JSON_CONTENT_TYPE
from agnara_events._exposure import _compile_inbound_event, _declare_inbound_event


@dataclass(frozen=True, slots=True)
class SnapshotPayload:
    sku: str
    revision: int
    pair: tuple[str, int]


class _Store:
    pass


def test_asyncapi_310_document_and_draft07_validation() -> None:
    app = Agnara("inventory")

    @provider()
    def open_store() -> _Store:
        return _Store()

    @app.capability(scopes=("inventory:write",), output=str)
    async def apply(snapshot: SnapshotPayload, tags: list[str], store: _Store) -> str:
        return snapshot.sku

    compiled = app.compile()
    deps = DIRegistry()
    deps.bind(_Store, open_store)
    plan = ExecutionPlan.compile(compiled["inventory.apply"], deps)
    binding = _compile_inbound_event(
        _declare_inbound_event(
            compiled["inventory.apply"],
            subscription_id="inventory-apply",
            event_type="example.inventory.snapshot.v1",
            principal=Principal("evt-worker", scopes={"inventory:write"}),
            public_address="inventory.snapshot.v1",
            summary="Inventory snapshot receiver",
        ),
        {compiled["inventory.apply"].id: plan},
    )

    doc = _project_asyncapi(
        binding,
        _AsyncAPIInfo(title="Inventory Events", version="1.0.0"),
    )

    assert doc["asyncapi"] == ASYNCAPI_VERSION
    assert doc["defaultContentType"] == CLOUDEVENTS_JSON_CONTENT_TYPE
    assert "servers" not in doc

    channel = doc["channels"]["inventory-apply"]
    assert channel["address"] == "inventory.snapshot.v1"
    op = doc["operations"]["receive_inventory-apply"]
    assert op["action"] == "receive"
    assert op["channel"] == {"$ref": "#/channels/inventory-apply"}
    assert op["messages"] == [
        {"$ref": "#/channels/inventory-apply/messages/inventory-applyMessage"}
    ]

    msg = doc["components"]["messages"]["inventory-applyMessage"]
    assert msg["contentType"] == CLOUDEVENTS_JSON_CONTENT_TYPE
    assert msg["payload"]["schemaFormat"] == DRAFT_07_SCHEMA_FORMAT

    envelope_schema = msg["payload"]["schema"]
    Draft7Validator.check_schema(envelope_schema)
    validator = Draft7Validator(envelope_schema)

    data_props = envelope_schema["properties"]["data"]["properties"]
    assert "store" not in data_props
    assert data_props["snapshot"]["properties"]["pair"] == {
        "type": "array",
        "items": [{"type": "string"}, {"type": "integer"}],
        "additionalItems": False,
        "minItems": 2,
        "maxItems": 2,
    }

    valid_event = {
        "specversion": "1.0",
        "id": "evt-1",
        "source": "/inventory",
        "type": "example.inventory.snapshot.v1",
        "datacontenttype": "application/json",
        "data": {
            "snapshot": {"sku": "A-1", "revision": 9007199254740993, "pair": ["A-1", 3]},
            "tags": ["primary"],
        },
    }
    assert validator.is_valid(valid_event)

    # Draft 07 accepts 2.0 as integer while Python runtime rejects it.
    lexical_float_event = json.loads(json.dumps(valid_event))
    lexical_float_event["data"]["snapshot"]["revision"] = 2.0
    assert validator.is_valid(lexical_float_event)

    wrong_tuple_event = json.loads(json.dumps(valid_event))
    wrong_tuple_event["data"]["snapshot"]["pair"] = ["A-1", 3, 99]
    assert not validator.is_valid(wrong_tuple_event)

    # Protected dependency injected into data is rejected by additionalProperties: False.
    forged_dep_event = json.loads(json.dumps(valid_event))
    forged_dep_event["data"]["store"] = "forged"
    assert not validator.is_valid(forged_dep_event)


def test_keyword_allowlist_applies_to_schema_positions_only() -> None:
    # Property literally named "$ref" or "oneOf" is allowed as a property name.
    schema = {
        "type": "object",
        "properties": {
            "$ref": {"type": "string", "minLength": 1},
            "oneOf": {"type": "integer", "minimum": 0},
        },
        "required": ["$ref"],
        "additionalProperties": False,
    }
    translated = _translate_schema_to_draft07(schema)
    Draft7Validator.check_schema(translated)
    assert isinstance(translated, dict)
    assert "$ref" in translated["properties"]
    assert "oneOf" in translated["properties"]

    # Unsupported keyword at schema position is refused.
    for bad_schema in (
        {"$ref": "#/defs/Foo"},
        {"anyOf": [{"type": "string"}, {"type": "integer"}]},
        {"oneOf": [{"type": "string"}]},
        {"type": "number", "minimum": float("nan")},
        {"type": "string", "minLength": True},
        {
            "type": "array",
            "prefixItems": [{"type": "string"}],
            "items": True,
            "minItems": 1,
            "maxItems": 1,
        },
    ):
        with pytest.raises(_AsyncAPIExportError):
            _translate_schema_to_draft07(bad_schema)


def test_hidden_or_private_exposures_are_filtered_before_schema_translation() -> None:
    app = Agnara("mixed")

    @app.capability(output=str)
    async def public_op(name: str) -> str:
        return name

    # Union produces `anyOf`, which Draft-07 subset rejects if visible.
    @app.capability(output=str)
    async def hidden_union_op(value: int | str) -> str:
        return str(value)

    compiled = app.compile()
    plans = {
        compiled["mixed.public_op"].id: ExecutionPlan.compile(
            compiled["mixed.public_op"], DIRegistry()
        ),
        compiled["mixed.hidden_union_op"].id: ExecutionPlan.compile(
            compiled["mixed.hidden_union_op"], DIRegistry()
        ),
    }
    principal = Principal("svc")
    visible = _compile_inbound_event(
        _declare_inbound_event(
            compiled["mixed.public_op"],
            subscription_id="public-sub",
            event_type="evt.public.v1",
            principal=principal,
            public_address="mixed.public.v1",
        ),
        plans,
    )
    private_no_addr = _compile_inbound_event(
        _declare_inbound_event(
            compiled["mixed.hidden_union_op"],
            subscription_id="secret-internal-sub",
            event_type="evt.secret.v1",
            principal=principal,
            public_address=None,
        ),
        plans,
    )
    filtered_by_policy = _compile_inbound_event(
        _declare_inbound_event(
            compiled["mixed.hidden_union_op"],
            subscription_id="filtered-secret-sub",
            event_type="evt.filtered.v1",
            principal=principal,
            public_address="mixed.filtered.v1",
        ),
        plans,
    )

    # Filtered exposures with unsupported shapes do not raise and never appear in the doc.
    doc = _project_asyncapi(
        [visible, private_no_addr, filtered_by_policy],
        _AsyncAPIInfo(title="Mixed", version="1.0.0"),
        is_visible=lambda b: b.exposure.subscription_id == "public-sub",
    )
    assert list(doc["channels"]) == ["public-sub"]
    assert "secret-internal-sub" not in json.dumps(doc)
    assert "filtered-secret-sub" not in json.dumps(doc)

    # When made visible, the unsupported shape fails safely without leaking hidden records.
    with pytest.raises(_AsyncAPIExportError, match="anyOf"):
        _project_asyncapi(
            [visible, filtered_by_policy],
            _AsyncAPIInfo(title="Mixed", version="1.0.0"),
        )

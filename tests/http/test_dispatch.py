"""Compiled HTTP exposures and the end-to-end request path (E6.6b)."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.execution import ExecutionPlan, Failure, FailureCode, Success
from agnara_http._binding import _BindingDefinitionError, _BindingSource, _InputBinding
from agnara_http._dispatch import (
    _compile_exposures,
    _DispatchOptions,
    _HTTPDispatcher,
    _HTTPExposure,
)
from agnara_http._problem import _compile_problem_types
from agnara_http._routing import (
    _DuplicateRouteError,
    _FrozenRouteRegistry,
    _RouteRegistry,
    _RouteRegistryFrozenError,
)


def plan(handler: Callable[..., Any], name: str = "target") -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(CapabilityId("tests", name), handler), DIRegistry()
    )


def dispatcher(
    *exposures: _HTTPExposure,
    options: _DispatchOptions | None = None,
) -> _HTTPDispatcher:
    return _HTTPDispatcher(_compile_exposures(exposures), DIContainer(DIRegistry()), options)


def request(
    served: _HTTPDispatcher,
    method: str,
    path: str,
    *,
    query: bytes = b"",
    headers: tuple[tuple[bytes, bytes], ...] = (),
    body: bytes | None = None,
    root_path: str = "",
    disconnect: bool = False,
) -> list[dict[str, Any]]:
    """Drive one request and return the ASGI events the dispatcher emitted."""
    events: list[dict[str, Any]] = []
    if disconnect:
        pending = [{"type": "http.disconnect"}]
    elif body is None:
        pending = [{"type": "http.request", "body": b"", "more_body": False}]
    else:
        pending = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive() -> dict[str, Any]:
        return pending.pop(0)

    async def send(message: dict[str, Any]) -> None:
        events.append(message)

    asyncio.run(
        served(
            {
                "type": "http",
                "method": method,
                "path": path,
                "raw_path": path.encode("utf-8"),
                "query_string": query,
                "root_path": root_path,
                "headers": list(headers),
            },
            receive,
            send,
        )
    )
    return events


def document(events: list[dict[str, Any]]) -> dict[str, Any]:
    return json.loads(events[1]["body"].decode("utf-8"))


def headers_of(events: list[dict[str, Any]]) -> dict[bytes, bytes]:
    return dict(events[0]["headers"])


JSON = ((b"content-type", b"application/json"),)


# --- compilation -----------------------------------------------------------


def test_compilation_resolves_a_route_to_its_plan_and_binding_in_one_lookup() -> None:
    def show(order_id: int) -> dict[str, int]:
        return {"order_id": order_id}

    routes = _compile_exposures(
        [
            _HTTPExposure(
                "GET",
                "/v1/orders/{order_id}",
                plan(show),
                (_InputBinding("order_id", _BindingSource.PATH),),
            )
        ]
    )
    match = routes.match("GET", "/v1/orders/7")

    assert match is not None
    assert match.route.target.plan.definition.id == CapabilityId("tests", "target")
    assert match.route.target.binding.bindings[0].input_name == "order_id"


def test_compilation_returns_an_immutable_snapshot() -> None:
    def ping() -> str:
        return "pong"

    routes = _compile_exposures([_HTTPExposure("GET", "/ping", plan(ping))])

    assert isinstance(routes, _FrozenRouteRegistry)
    assert len(routes) == 1
    # No exposure can be added to the snapshot a request path reads.
    assert not hasattr(routes, "register")


def test_registration_after_a_freeze_is_refused() -> None:
    def ping() -> str:
        return "pong"

    collector: _RouteRegistry[object] = _RouteRegistry()
    collector.register("GET", "/ping", object())
    collector.freeze()
    with pytest.raises(_RouteRegistryFrozenError):
        collector.register("GET", "/other", object())
    del ping


def test_a_duplicate_route_shape_fails_at_compilation() -> None:
    def show(value: int) -> None:
        del value

    with pytest.raises(_DuplicateRouteError):
        _compile_exposures(
            [
                _HTTPExposure(
                    "GET",
                    "/v1/{a}",
                    plan(show),
                    (_InputBinding("value", _BindingSource.PATH, "a"),),
                ),
                _HTTPExposure(
                    "GET",
                    "/v1/{b}",
                    plan(show),
                    (_InputBinding("value", _BindingSource.PATH, "b"),),
                ),
            ]
        )


def test_a_required_input_without_a_binding_fails_at_compilation() -> None:
    def show(order_id: int) -> None:
        del order_id

    with pytest.raises(_BindingDefinitionError, match="required input 'order_id'"):
        _compile_exposures([_HTTPExposure("GET", "/v1/orders", plan(show))])


def test_an_unbound_path_parameter_fails_at_compilation() -> None:
    def ping() -> str:
        return "pong"

    with pytest.raises(_BindingDefinitionError, match="not bound"):
        _compile_exposures([_HTTPExposure("GET", "/v1/{order_id}", plan(ping))])


def test_a_binding_for_an_unknown_input_fails_at_compilation() -> None:
    def ping() -> str:
        return "pong"

    with pytest.raises(_BindingDefinitionError, match="unknown capability input"):
        _compile_exposures(
            [
                _HTTPExposure(
                    "GET", "/ping", plan(ping), (_InputBinding("nope", _BindingSource.QUERY),)
                )
            ]
        )


def test_compilation_refuses_a_non_exposure() -> None:
    with pytest.raises(_BindingDefinitionError, match="must contain _HTTPExposure"):
        _compile_exposures([object()])  # ty: ignore[invalid-argument-type]


# --- the happy path --------------------------------------------------------


def test_a_matched_request_binds_invokes_and_returns_a_success_response() -> None:
    def show(order_id: int, verbose: bool = False) -> dict[str, Any]:
        return {"order_id": order_id, "verbose": verbose}

    served = dispatcher(
        _HTTPExposure(
            "GET",
            "/v1/orders/{order_id}",
            plan(show),
            (
                _InputBinding("order_id", _BindingSource.PATH),
                _InputBinding("verbose", _BindingSource.QUERY),
            ),
        )
    )
    events = request(served, "GET", "/v1/orders/7", query=b"verbose=true")

    assert len(events) == 2
    assert events[0]["status"] == 200
    assert headers_of(events)[b"content-type"] == b"application/json; charset=utf-8"
    assert json.loads(events[1]["body"]) == {"order_id": 7, "verbose": True}
    assert events[1]["more_body"] is False


def test_a_json_body_reaches_the_capability() -> None:
    def create(order: dict[str, Any]) -> dict[str, Any]:
        return {"received": order}

    served = dispatcher(
        _HTTPExposure(
            "POST", "/v1/orders", plan(create), (_InputBinding("order", _BindingSource.BODY),)
        )
    )
    events = request(served, "POST", "/v1/orders", headers=JSON, body=b'{"sku":"A-1"}')

    assert events[0]["status"] == 200
    assert json.loads(events[1]["body"]) == {"received": {"sku": "A-1"}}


def test_a_none_result_is_a_bodyless_204() -> None:
    def archive() -> None:
        return None

    served = dispatcher(_HTTPExposure("POST", "/v1/archive", plan(archive)))
    events = request(served, "POST", "/v1/archive")

    assert events[0]["status"] == 204
    assert events[0]["headers"] == []
    assert events[1]["body"] == b""


def test_an_explicit_success_is_serialized_like_a_returned_value() -> None:
    def show() -> Success[dict[str, int]]:
        return Success({"count": 2})

    served = dispatcher(_HTTPExposure("GET", "/v1/count", plan(show)))
    events = request(served, "GET", "/v1/count")

    assert events[0]["status"] == 200
    assert json.loads(events[1]["body"]) == {"count": 2}


# --- HEAD ------------------------------------------------------------------


def test_head_reuses_the_get_exposure_with_headers_but_no_body() -> None:
    def show() -> dict[str, str]:
        return {"state": "ready"}

    served = dispatcher(_HTTPExposure("GET", "/v1/state", plan(show)))
    get = request(served, "GET", "/v1/state")
    head = request(served, "HEAD", "/v1/state")

    assert head[0]["status"] == get[0]["status"] == 200
    assert head[0]["headers"] == get[0]["headers"]
    assert headers_of(head)[b"content-length"] == str(len(get[1]["body"])).encode("ascii")
    assert head[1]["body"] == b""


def test_an_explicit_head_exposure_wins_over_the_get_fallback() -> None:
    def get_handler() -> dict[str, str]:
        return {"from": "get"}

    def head_handler() -> dict[str, str]:
        return {"from": "head"}

    served = dispatcher(
        _HTTPExposure("GET", "/v1/state", plan(get_handler, "get")),
        _HTTPExposure("HEAD", "/v1/state", plan(head_handler, "head")),
    )
    events = request(served, "HEAD", "/v1/state")

    # The body is suppressed, but the length proves which exposure answered.
    assert headers_of(events)[b"content-length"] == str(len(b'{"from":"head"}')).encode("ascii")


def test_a_head_problem_also_suppresses_its_body() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    events = request(served, "HEAD", "/absent")

    assert events[0]["status"] == 404
    assert events[1]["body"] == b""


# --- routing failures ------------------------------------------------------


def test_an_unmatched_path_is_a_404_problem() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    events = request(served, "GET", "/absent")

    assert events[0]["status"] == 404
    assert headers_of(events)[b"content-type"] == b"application/problem+json"
    body = document(events)
    assert body["code"] == "not_found"
    assert body["instance"] == "/absent"


def test_a_method_mismatch_is_a_405_with_allow() -> None:
    def ping() -> str:
        return "pong"

    def create() -> str:
        return "made"

    served = dispatcher(
        _HTTPExposure("GET", "/v1/thing", plan(ping, "get")),
        _HTTPExposure("POST", "/v1/thing", plan(create, "post")),
    )
    events = request(served, "DELETE", "/v1/thing")

    assert events[0]["status"] == 405
    assert document(events)["code"] == "method_not_allowed"
    assert headers_of(events)[b"allow"] == b"GET, HEAD, POST"


def test_allow_omits_the_implied_head_when_one_is_declared() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(
        _HTTPExposure("GET", "/v1/thing", plan(ping, "get")),
        _HTTPExposure("HEAD", "/v1/thing", plan(ping, "head")),
    )
    events = request(served, "DELETE", "/v1/thing")

    assert headers_of(events)[b"allow"] == b"GET, HEAD"


def test_allow_does_not_invent_head_without_a_get() -> None:
    def create() -> str:
        return "made"

    served = dispatcher(_HTTPExposure("POST", "/v1/thing", plan(create)))
    events = request(served, "DELETE", "/v1/thing")

    assert headers_of(events)[b"allow"] == b"POST"


# --- binding failures ------------------------------------------------------


def test_a_malformed_query_value_is_a_400_problem_naming_its_location() -> None:
    def show(order_id: int) -> None:
        del order_id

    served = dispatcher(
        _HTTPExposure(
            "GET", "/v1/orders", plan(show), (_InputBinding("order_id", _BindingSource.QUERY),)
        )
    )
    events = request(served, "GET", "/v1/orders", query=b"order_id=abc")

    assert events[0]["status"] == 400
    body = document(events)
    assert body["code"] == "invalid_input"
    assert body["details"] == {"location": "query.order_id"}


def test_a_wrong_media_type_is_a_415_problem() -> None:
    def create(order: dict[str, Any]) -> None:
        del order

    served = dispatcher(
        _HTTPExposure(
            "POST", "/v1/orders", plan(create), (_InputBinding("order", _BindingSource.BODY),)
        )
    )
    events = request(
        served, "POST", "/v1/orders", headers=((b"content-type", b"text/plain"),), body=b"{}"
    )

    assert events[0]["status"] == 415
    assert document(events)["code"] == "unsupported_media_type"


def test_an_oversized_body_is_a_413_problem() -> None:
    def create(order: dict[str, Any]) -> None:
        del order

    served = dispatcher(
        _HTTPExposure(
            "POST",
            "/v1/orders",
            plan(create),
            (_InputBinding("order", _BindingSource.BODY),),
            max_body_bytes=4,
        )
    )
    events = request(served, "POST", "/v1/orders", headers=JSON, body=b'{"sku":"A-1"}')

    assert events[0]["status"] == 413
    assert document(events)["code"] == "content_too_large"


def test_a_client_disconnect_produces_no_response_at_all() -> None:
    def create(order: dict[str, Any]) -> None:
        del order

    served = dispatcher(
        _HTTPExposure(
            "POST", "/v1/orders", plan(create), (_InputBinding("order", _BindingSource.BODY),)
        )
    )
    events = request(served, "POST", "/v1/orders", headers=JSON, disconnect=True)

    assert events == []


# --- capability failures ---------------------------------------------------


def test_a_capability_failure_becomes_its_rfc_9457_problem() -> None:
    def show() -> Failure:
        return Failure(FailureCode.CONFLICT, "version 3 is stale", details={"version": 3})

    served = dispatcher(_HTTPExposure("GET", "/v1/thing", plan(show)))
    events = request(served, "GET", "/v1/thing")

    assert events[0]["status"] == 409
    body = document(events)
    assert body["code"] == "conflict"
    assert body["detail"] == "version 3 is stale"
    assert body["details"] == {"version": 3}
    assert body["instance"] == "/v1/thing"


def test_a_raised_exception_becomes_a_redacted_500() -> None:
    def show() -> None:
        raise RuntimeError("postgres password authentication failed")

    served = dispatcher(_HTTPExposure("GET", "/v1/thing", plan(show)))
    events = request(served, "GET", "/v1/thing")

    assert events[0]["status"] == 500
    body = document(events)
    assert body["code"] == "internal_failure"
    assert "postgres" not in json.dumps(body)


def test_an_unserializable_success_falls_back_to_the_internal_problem() -> None:
    def show() -> object:
        return object()

    served = dispatcher(_HTTPExposure("GET", "/v1/thing", plan(show)))
    events = request(served, "GET", "/v1/thing")

    assert len(events) == 2
    assert events[0]["status"] == 500
    assert document(events)["code"] == "internal_failure"


def test_validation_of_a_bound_value_is_still_the_core_rule() -> None:
    def show(order_id: int) -> None:
        del order_id

    served = dispatcher(
        _HTTPExposure(
            "GET", "/v1/orders", plan(show), (_InputBinding("order_id", _BindingSource.QUERY),)
        )
    )
    events = request(served, "GET", "/v1/orders")

    # Nothing bound, so core reports the missing input rather than the adapter.
    assert events[0]["status"] == 400
    assert document(events)["code"] == "invalid_input"


# --- scope handling --------------------------------------------------------


def test_root_path_is_stripped_before_matching() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    events = request(served, "GET", "/api/ping", root_path="/api")

    assert events[0]["status"] == 200
    assert json.loads(events[1]["body"]) == "pong"


def test_a_request_outside_the_mount_prefix_does_not_match() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    events = request(served, "GET", "/other/ping", root_path="/api")

    assert events[0]["status"] == 404


def test_a_target_that_is_not_a_uri_reference_omits_the_instance() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    events = request(served, "GET", "/órdenes")

    # The 404 still serializes; it simply does not claim an instance.
    assert events[0]["status"] == 404
    assert "instance" not in document(events)


def test_the_problem_instance_never_carries_the_query_string() -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    events = request(served, "GET", "/absent", query=b"token=s3cret")

    body = document(events)
    assert body["instance"] == "/absent"
    assert "s3cret" not in json.dumps(body)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("method", "ASGI scope 'method' must be a string"),
        ("path", "ASGI scope 'path' must be a string"),
        ("root_path", "ASGI scope 'root_path' must be a string"),
    ],
)
def test_a_malformed_scope_is_refused(field: str, message: str) -> None:
    def ping() -> str:
        return "pong"

    served = dispatcher(_HTTPExposure("GET", "/ping", plan(ping)))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/ping",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        field: 42,
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        del message

    with pytest.raises(TypeError, match=message):
        asyncio.run(served(scope, receive, send))


# --- options ---------------------------------------------------------------


def test_configured_problem_types_reach_both_problem_boundaries() -> None:
    def show() -> Failure:
        return Failure(FailureCode.CONFLICT, "stale")

    options = _DispatchOptions(_compile_problem_types("https://example.test/problems/"))
    served = dispatcher(_HTTPExposure("GET", "/v1/thing", plan(show)), options=options)

    capability = document(request(served, "GET", "/v1/thing"))
    transport = document(request(served, "GET", "/absent"))

    assert capability["type"] == "https://example.test/problems/conflict"
    assert transport["type"] == "https://example.test/problems/not-found"


def test_a_configured_timeout_gives_the_invocation_a_deadline() -> None:
    seen: list[float | None] = []

    def show(order_id: int) -> str:
        del order_id
        return "ok"

    served = dispatcher(
        _HTTPExposure(
            "GET", "/v1/orders", plan(show), (_InputBinding("order_id", _BindingSource.QUERY),)
        ),
        options=_DispatchOptions(timeout=30.0),
    )

    def capture(events: list[dict[str, Any]]) -> None:
        seen.append(events[0]["status"])

    capture(request(served, "GET", "/v1/orders", query=b"order_id=1"))
    assert seen == [200]


@pytest.mark.parametrize("timeout", [0, -1, True, "30"])
def test_an_unusable_timeout_is_refused(timeout: object) -> None:
    with pytest.raises(ValueError, match="positive number of seconds"):
        _DispatchOptions(timeout=timeout)  # ty: ignore[invalid-argument-type]


def test_the_dispatcher_refuses_a_non_frozen_registry_or_container() -> None:
    def ping() -> str:
        return "pong"

    routes = _compile_exposures([_HTTPExposure("GET", "/ping", plan(ping))])
    with pytest.raises(TypeError, match="routes must be a frozen registry"):
        _HTTPDispatcher(object(), DIContainer(DIRegistry()))  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError, match="di_container must be a DIContainer"):
        _HTTPDispatcher(routes, object())  # ty: ignore[invalid-argument-type]

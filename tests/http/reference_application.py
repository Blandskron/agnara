"""The reference HTTP application the OpenAPI fixtures are pinned against.

Kept beside the fixture, and out of the test module, so regenerating the
fixture and asserting against it read from exactly one definition.

Regenerate the fixture with:

    uv run python -m tests.http.reference_application
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http._binding import _BindingSource, _InputBinding
from agnara_http._dispatch import (
    _compile_exposures,
    _CompiledExposure,
    _HTTPExposure,
    _OpenAPIPublication,
)
from agnara_http._openapi import _OpenAPIInfo, _project_openapi, _serialize_openapi
from agnara_http._routing import _FrozenRouteRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "openapi_reference.json"

INFO = _OpenAPIInfo(
    title="Agnara reference application",
    version="0.0.0",
    summary="Every projection feature the adapter implements, in one document.",
)


def list_orders(status: str, limit: int = 20) -> list[dict[str, Any]]:
    """List orders, newest first.

    The second paragraph exists to prove only the summary line is published.
    """
    del status, limit
    return []


def show_order(order_id: int, trace_id: str = "") -> dict[str, Any]:
    """Return one order by its identifier."""
    del trace_id
    return {"order_id": order_id}


def create_order(order: dict[str, Any]) -> dict[str, Any]:
    """Create one order."""
    return {"created": order}


def retire_order(order_id: int) -> None:
    """Retire one order. Deprecated in favour of archiving."""
    del order_id


def internal_probe() -> str:
    """Never published: this exposure has no OpenAPI publication."""
    return "ok"


def _plan(handler: Any, name: str) -> ExecutionPlan:
    return ExecutionPlan.compile(
        CapabilityDefinition(
            CapabilityId("reference", name),
            handler,
            description=(handler.__doc__ or "").strip().splitlines()[0] or None,
        ),
        DIRegistry(),
    )


def exposures() -> tuple[_HTTPExposure, ...]:
    """Every projection feature the adapter implements, exactly once."""
    return (
        _HTTPExposure(
            "GET",
            "/v1/orders",
            _plan(list_orders, "list_orders"),
            (
                _InputBinding("status", _BindingSource.QUERY),
                _InputBinding("limit", _BindingSource.QUERY),
            ),
            openapi=_OpenAPIPublication(
                summary="List orders",
                publish_description=True,
                tags=("orders", "read"),
            ),
        ),
        _HTTPExposure(
            "GET",
            "/v1/orders/{order_id}",
            _plan(show_order, "show_order"),
            (
                _InputBinding("order_id", _BindingSource.PATH),
                _InputBinding("trace_id", _BindingSource.HEADER, "x-trace-id"),
            ),
            openapi=_OpenAPIPublication(summary="Show one order", tags=("orders",)),
        ),
        _HTTPExposure(
            "POST",
            "/v1/orders",
            _plan(create_order, "create_order"),
            (_InputBinding("order", _BindingSource.BODY),),
            openapi=_OpenAPIPublication(summary="Create an order", tags=("orders",)),
        ),
        _HTTPExposure(
            "DELETE",
            "/v1/orders/{order_id}",
            _plan(retire_order, "retire_order"),
            (_InputBinding("order_id", _BindingSource.PATH),),
            openapi=_OpenAPIPublication(summary="Retire an order", deprecated=True),
        ),
        _HTTPExposure(
            "GET",
            "/internal/probe",
            _plan(internal_probe, "internal_probe"),
        ),
    )


def routes() -> _FrozenRouteRegistry[_CompiledExposure]:
    return _compile_exposures(exposures())


def document() -> dict[str, Any]:
    return _project_openapi(routes(), INFO)


def serialized() -> bytes:
    return _serialize_openapi(document())


def main() -> int:
    """Regenerate the pinned fixture from the projection, never by hand."""
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_bytes(serialized() + b"\n")
    sys.stdout.write(f"wrote {FIXTURE}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

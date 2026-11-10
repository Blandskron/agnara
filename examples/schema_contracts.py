"""Strict Python schemas and explicit JSON boundaries.

Run with ``uv run python examples/schema_contracts.py``. See docs/SCHEMA_CONTRACTS.md.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import cast

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CanonicalResult,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
    invoke_result,
)
from agnara.schema import materialize_json, serialize_json


class Currency(Enum):
    CLP = "CLP"
    USD = "USD"


@dataclass
class Line:
    quantity: int
    unit_cents: int


@dataclass
class Order:
    lines: list[Line]
    currency: Currency = Currency.CLP
    note: str | None = None


@dataclass
class Receipt:
    total_cents: int
    currency: Currency


@dataclass
class Demonstration:
    results: dict[str, CanonicalResult] = field(default_factory=dict)
    handled: list[Order] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    direct_order: Order = field(default_factory=lambda: Order([Line(2, 125)]))
    wire_order: dict[str, object] = field(
        default_factory=lambda: {"lines": [{"quantity": 2, "unit_cents": 125}], "currency": "CLP"}
    )
    schemas: dict[str, object] = field(default_factory=dict)


async def demonstrate() -> Demonstration:
    demo = Demonstration()
    app = Agnara("checkout")

    @app.capability(scopes=("checkout:quote",), output=Receipt)
    def quote(order: Order) -> Receipt:
        demo.events.append("quote.enter")
        demo.handled.append(order)
        return Receipt(sum(line.quantity * line.unit_cents for line in order.lines), order.currency)

    @app.capability(scopes=("checkout:quote",), output=Receipt)
    def broken() -> Receipt:
        demo.events.append("broken.enter")
        # Deliberate producer fault fixture. Dataclass construction alone
        # does not enforce annotations; the declared output schema does.
        return Receipt(cast(int, "private producer value"), Currency.CLP)

    @app.capability(scopes=("checkout:quote",))
    def annotated_only() -> int:
        demo.events.append("annotated.enter")
        # No output=... was declared: the contract is intentionally Any.
        return cast(int, "annotation alone is unconstrained")

    dependencies = DIRegistry()
    capabilities = app.compile()
    plans = {
        name: ExecutionPlan.compile(capabilities[f"checkout.{name}"], dependencies)
        for name in ("quote", "broken", "annotated_only")
    }
    demo.schemas = {
        "input": plans["quote"].input_schemas["order"].json_schema(),
        "output": plans["quote"].output_schema.json_schema(),
        "annotation_only": plans["annotated_only"].output_schema.json_schema(),
    }
    container = DIContainer(dependencies)
    actor = Principal("local-demo", scopes={"checkout:quote"})

    async def call(
        payload: dict[str, object],
        *,
        json_input: bool = False,
        principal: Principal = actor,
        target: str = "quote",
    ) -> CanonicalResult:
        plan = plans[target]
        return await invoke_result(
            plan,
            ExecutionContext(
                Invocation(plan.definition.id, payload, {}), container, principal=principal
            ),
            input_materializer=materialize_json if json_input else None,
        )

    try:
        async with asyncio.timeout(5):
            demo.results["denied"] = await call(
                {"order": demo.wire_order}, json_input=True, principal=Principal("unscoped")
            )
            demo.results["direct"] = await call({"order": demo.direct_order})
            demo.results["mapping"] = await call({"order": demo.wire_order})
            demo.results["json"] = await call({"order": demo.wire_order}, json_input=True)
            demo.results["json_defaults"] = await call(
                {"order": {"lines": [{"quantity": 2, "unit_cents": 125}]}}, json_input=True
            )
            for name, order in (
                ("bad_quantity", {"lines": [{"quantity": "private input", "unit_cents": 125}]}),
                ("bool_quantity", {"lines": [{"quantity": True, "unit_cents": 125}]}),
                ("extra_field", {**demo.wire_order, "undeclared": "private extra value"}),
                ("bad_currency", {**demo.wire_order, "currency": "undeclared currency"}),
            ):
                demo.results[name] = await call({"order": order}, json_input=True)
            demo.results["bad_output"] = await call({}, target="broken")
            demo.results["annotation_only"] = await call({}, target="annotated_only")
    finally:
        await container.aclose()
    return demo


def main() -> None:
    demo = asyncio.run(demonstrate())
    for name, result in demo.results.items():
        if isinstance(result, Success):
            # Validate first, then explicitly project just the successful value.
            print(f"{name}: {json.dumps(serialize_json(result.value), sort_keys=True)}")
        elif isinstance(result, Failure):
            print(f"{name}: {result.code.value}")
    print(f"events: {demo.events}")


if __name__ == "__main__":
    main()

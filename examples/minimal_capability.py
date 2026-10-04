"""Minimal public-only direct capability; compatible with published Agnara 1.0.3."""

from __future__ import annotations

import asyncio

from agnara import Agnara
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, invoke_result


async def demonstrate():
    app = Agnara("calculator")

    @app.capability(output=int)
    def add(a: int, b: int) -> int:
        return a + b

    dependencies = DIRegistry()
    plan = ExecutionPlan.compile(app.compile()["calculator.add"], dependencies)
    container = DIContainer(dependencies)
    try:
        return await invoke_result(
            plan,
            ExecutionContext(Invocation(plan.definition.id, {"a": 2, "b": 3}, {}), container),
        )
    finally:
        await container.aclose()


if __name__ == "__main__":
    print(asyncio.run(demonstrate()))

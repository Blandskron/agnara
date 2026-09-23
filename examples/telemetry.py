"""Agnara — joining an application's existing telemetry pipeline.

    python telemetry.py

The application owns OpenTelemetry, not Agnara. It creates the tracer provider,
chooses the exporter and shuts both down; Agnara contributes capability spans
through one optional hook and holds no OpenTelemetry type in its kernel.

`agnara-telemetry` depends only on `opentelemetry-api`, so this runs without an
SDK installed: the API's default tracer is a no-op and the wiring is unchanged.
With `opentelemetry-sdk` present it also prints the spans that were exported,
which is what a real deployment sees.

What the hook records, and deliberately does not: the capability identifier, the
execution and invocation identity, and the outcome. Never a payload, a principal,
an argument value or an exception message. Telemetry is an egress boundary, so
`docs/THREAT_MODEL.md` treats redaction there as a security property.
"""

from __future__ import annotations

import asyncio
from typing import Any

from opentelemetry.trace import Tracer, get_tracer

from agnara import Agnara, App
from agnara.di import DIContainer, DIRegistry
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, Success, invoke_result
from agnara_telemetry import OpenTelemetryTracingHook

#: Long, non-hexadecimal and non-numeric, so finding it in exported span
#: JSON can only mean the payload leaked.
SECRET_TOKEN = "zzz-payload-must-never-be-exported-zzz"


def build_tracer() -> tuple[Tracer, Any]:
    """Return (tracer, exporter). The exporter is None without the SDK.

    Provider and exporter lifecycle belong to the application. Agnara never
    creates, configures or shuts down either one.
    """
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
            InMemorySpanExporter,
        )
    except ModuleNotFoundError:
        return get_tracer("example"), None

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider.get_tracer("example"), exporter


def build_application() -> App:
    app = App("billing")

    @app.capability
    def total(amount: int, tax: int) -> int:
        return amount + tax

    @app.capability
    def refuse(token: str) -> int:
        # The token is deliberately long and non-hexadecimal. A short or numeric
        # value would collide with a random span id or a nanosecond timestamp,
        # and the check below would fail on chance rather than on a leak.
        raise RuntimeError(f"secret payload reached the logs: {token}")

    return app


async def main() -> None:
    tracer, exporter = build_tracer()

    project = Agnara("example")
    project.include(build_application())
    capabilities = project.compile()

    registry = DIRegistry()
    # The hook is compiled into the plan. A capability with no hooks pays
    # nothing: the runtime guards lifecycle event construction on their
    # presence rather than building events nobody consumes.
    hook = OpenTelemetryTracingHook(tracer)
    plans = {
        str(identifier): ExecutionPlan.compile(definition, registry, hooks=[hook])
        for identifier, definition in capabilities.items()
    }
    container = DIContainer(registry)

    try:
        for identifier, payload in (
            ("billing.total", {"amount": 100, "tax": 19}),
            ("billing.refuse", {"token": SECRET_TOKEN}),
        ):
            plan = plans[identifier]
            result = await invoke_result(
                plan,
                ExecutionContext(
                    Invocation(plan.definition.id, payload, {}),
                    container,
                ),
            )
            if isinstance(result, Success):
                print(f"{identifier}: success -> {result.value}")
            else:
                # The failure is already redacted: an unexpected exception
                # keeps its capability identifier and loses its message.
                print(f"{identifier}: {result.code} -> {result.message}")
    finally:
        await container.aclose()

    if exporter is None:
        print("\nopentelemetry-sdk is not installed, so nothing was exported.")
        print("The wiring above is unchanged; the API's default tracer is a no-op.")
        return

    print("\nexported spans:")
    for span in exporter.get_finished_spans():
        attributes = span.attributes or {}
        outcome = attributes.get("agnara.invocation.outcome")
        print(f"  {span.name}: outcome={outcome}")

    rendered = "\n".join(span.to_json() for span in exporter.get_finished_spans())
    for secret in (SECRET_TOKEN, "secret payload reached the logs"):
        assert secret not in rendered, "telemetry must not carry payloads or exception text"
    print("\nno payload, argument value or exception message reached the exporter")


if __name__ == "__main__":
    asyncio.run(main())

"""Standalone hosts close their own containers and optional telemetry pipeline."""

from __future__ import annotations

import asyncio
import builtins
from collections.abc import AsyncIterator

import pytest
from examples import quickstart, telemetry
from opentelemetry.sdk import trace
from opentelemetry.sdk.trace.export import in_memory_span_exporter
from opentelemetry.trace import NoOpTracer

from agnara.di import DIContainer, Scope, provider


@pytest.mark.parametrize("example", [quickstart, telemetry], ids=["quickstart", "telemetry"])
@pytest.mark.parametrize("exit_kind", ["success", "error", "cancel"])
def test_owned_resources_close_in_order_on_every_exit(example, exit_kind, monkeypatch, capsys):
    events = []
    calls = []
    exported = []

    class OwnedContainer(DIContainer):
        def __init__(self, registry):
            super().__init__(registry)
            events.append(("container.open", asyncio.get_running_loop()))

        async def aclose(self):
            await super().aclose()
            events.append(("container.close", asyncio.get_running_loop()))

    class OwnedProvider(trace.TracerProvider):
        def shutdown(self):
            events.append(("provider.close", asyncio.get_running_loop()))
            super().shutdown()

    class OwnedExporter(in_memory_span_exporter.InMemorySpanExporter):
        def shutdown(self):
            exported.extend(self.get_finished_spans())
            events.append(("exporter.close", asyncio.get_running_loop()))
            super().shutdown()

    @provider(scope=Scope.SINGLETON)
    async def ledger() -> AsyncIterator[quickstart.Ledger]:
        events.append(("ledger.open", asyncio.get_running_loop()))
        try:
            yield quickstart.Ledger()
        finally:
            events.append(("ledger.close", asyncio.get_running_loop()))

    monkeypatch.setattr(example, "DIContainer", OwnedContainer)
    monkeypatch.setattr(quickstart, "provide_ledger", ledger)
    monkeypatch.setattr(trace, "TracerProvider", OwnedProvider)
    monkeypatch.setattr(in_memory_span_exporter, "InMemorySpanExporter", OwnedExporter)
    invoke = example.invoke_result

    async def run():
        entered = asyncio.Event()

        async def observed_invoke(plan, context):
            calls.append(context.di_container)
            outcome = await invoke(plan, context)
            if exit_kind == "error":
                raise RuntimeError("host failed after invocation")
            if exit_kind == "cancel":
                entered.set()
                await asyncio.Event().wait()
            return outcome

        monkeypatch.setattr(example, "invoke_result", observed_invoke)
        if exit_kind == "cancel":
            async with asyncio.timeout(5), asyncio.TaskGroup() as owned:
                task = owned.create_task(example.main())
                await entered.wait()
                task.cancel()
            assert task.cancelled()
        elif exit_kind == "error":
            with pytest.raises(RuntimeError, match="host failed after invocation"):
                await example.main()
        else:
            await example.main()
            assert len(calls) == 2 and calls[0] is calls[1]

        labels = [name for name, _ in events]
        assert labels.count("container.open") == labels.count("container.close") == 1
        if example is telemetry:
            assert labels[-3:] == ["container.close", "provider.close", "exporter.close"]
            assert labels.count("provider.close") == labels.count("exporter.close") == 1
            assert len(exported) == (2 if exit_kind == "success" else 1)
            rendered = "\n".join(span.to_json() for span in exported)
            assert telemetry.SECRET_TOKEN not in rendered
            assert "secret payload reached the logs" not in rendered
        else:
            assert labels == ["container.open", "ledger.open", "ledger.close", "container.close"]
        assert all(loop is asyncio.get_running_loop() for _, loop in events)
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())
    if exit_kind == "success":
        output = capsys.readouterr().out
        if example is telemetry:
            assert "no payload, argument value or exception message reached the exporter" in output
        else:
            assert "success: refunded 2500 cents for pay_123" in output
            assert "rejected: invalid_input" in output


@pytest.mark.parametrize("missing", ["opentelemetry.sdk", "unrelated_sdk_dependency"])
def test_only_absent_optional_sdk_uses_api_only_fallback(missing, monkeypatch, capsys):
    original_import = builtins.__import__

    def without_sdk(name, *args, **kwargs):
        if name == "opentelemetry.sdk.trace":
            raise ModuleNotFoundError("simulated missing dependency", name=missing)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_sdk)
    if missing == "opentelemetry.sdk":
        tracer = NoOpTracer()
        monkeypatch.setattr(telemetry, "get_tracer", lambda _: tracer)
        with telemetry.build_tracer() as (actual, exporter):
            assert actual is tracer and exporter is None
        asyncio.run(telemetry.main())
        output = capsys.readouterr().out
        assert "billing.total: success -> 119" in output
        assert "opentelemetry-sdk is not installed, so nothing was exported." in output
        assert telemetry.SECRET_TOKEN not in output
    else:
        with pytest.raises(ModuleNotFoundError) as caught, telemetry.build_tracer():
            pytest.fail("a broken SDK must not fall back silently")
        assert caught.value.name == missing


def test_provider_closes_when_tracer_configuration_fails(monkeypatch):
    closed = []
    shutdown = trace.TracerProvider.shutdown

    def fail_configuration(self, *args, **kwargs):
        raise RuntimeError("tracer configuration failed")

    def record_shutdown(self):
        closed.append(self)
        shutdown(self)

    monkeypatch.setattr(trace.TracerProvider, "get_tracer", fail_configuration)
    monkeypatch.setattr(trace.TracerProvider, "shutdown", record_shutdown)
    with pytest.raises(RuntimeError, match="tracer configuration failed"), telemetry.build_tracer():
        pytest.fail("configuration failure must propagate")
    assert len(closed) == 1

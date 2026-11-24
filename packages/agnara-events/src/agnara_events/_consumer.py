"""Broker-neutral inbound event consumer and settlement runtime (ADR 0101, EVT-03)."""

from __future__ import annotations

import asyncio
import contextlib
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from agnara.di import DIContainer
from agnara.execution import (
    ExecutionContext,
    Failure,
    FailureCode,
    Invocation,
    invoke_result,
)
from agnara.schema import TypeSchema, materialize_json

from ._envelope import _decode_cloudevent, _EnvelopeError
from ._exposure import _CompiledEventBinding

__all__: list[str] = []


class _Delivery(Protocol):
    """One received broker delivery supporting manual settlement."""

    @property
    def body(self) -> bytes: ...

    @property
    def content_type(self) -> str | None: ...

    async def acknowledge(self) -> None: ...

    async def reject(self) -> None: ...

    async def release(self) -> None: ...


class _DeliverySource(Protocol):
    """Single-consumer delivery source with explicit stop control."""

    async def receive(self) -> _Delivery | None: ...

    async def stop_receiving(self) -> None: ...


class _SettlementAction(StrEnum):
    """Manual broker settlement operations mapped from canonical outcomes."""

    ACKNOWLEDGE = "acknowledge"
    REJECT = "reject"
    RELEASE = "release"


_RELEASE_FAILURE_CODES = frozenset(
    {
        FailureCode.RATE_LIMITED,
        FailureCode.UNAVAILABLE,
        FailureCode.TIMEOUT,
        FailureCode.INTERNAL_FAILURE,
    }
)


def _settlement_for_failure(code: FailureCode) -> _SettlementAction:
    """Map every canonical ``FailureCode`` to reject or bounded redelivery."""
    if code in _RELEASE_FAILURE_CODES:
        return _SettlementAction.RELEASE
    return _SettlementAction.REJECT


@dataclass(frozen=True, slots=True)
class _ConsumerBudgets:
    """Finite positive monotonic attempt and shutdown budgets owned by the host."""

    attempt_seconds: float
    shutdown_seconds: float

    def __post_init__(self) -> None:
        for name, value in (
            ("attempt_seconds", self.attempt_seconds),
            ("shutdown_seconds", self.shutdown_seconds),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number")
            object.__setattr__(self, name, float(value))


@dataclass(frozen=True, slots=True)
class _ConsumerDiagnostic:
    """Redacted per-delivery record containing no payloads or raw exception text."""

    correlation_id: str
    subscription_id: str
    outcome: str
    settlement: str


class _SettlementUncertaintyError(RuntimeError):
    """Raised when settling a delivery fails and the channel cannot be reused."""

    def __init__(
        self,
        *,
        correlation_id: str,
        subscription_id: str,
        outcome: str,
        intended_action: _SettlementAction,
    ) -> None:
        self.correlation_id = correlation_id
        self.subscription_id = subscription_id
        self.outcome = outcome
        self.intended_action = intended_action
        super().__init__(
            f"settlement uncertainty for subscription={subscription_id} "
            f"correlation_id={correlation_id} outcome={outcome} "
            f"intended={intended_action.value}"
        )


async def _cancel_and_join(task: asyncio.Task[Any]) -> None:
    if not task.done():
        task.cancel()
    with contextlib.suppress(BaseException):
        await task


async def _settle(
    delivery: _Delivery,
    action: _SettlementAction,
    *,
    correlation_id: str,
    subscription_id: str,
    outcome: str,
) -> None:
    try:
        if action is _SettlementAction.ACKNOWLEDGE:
            await delivery.acknowledge()
        elif action is _SettlementAction.REJECT:
            await delivery.reject()
        else:
            await delivery.release()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        raise _SettlementUncertaintyError(
            correlation_id=correlation_id,
            subscription_id=subscription_id,
            outcome=outcome,
            intended_action=action,
        ) from error


async def _consume_inbound_events(
    binding: _CompiledEventBinding,
    container: DIContainer,
    source: _DeliverySource,
    *,
    budgets: _ConsumerBudgets,
    stop_event: asyncio.Event,
    on_diagnostic: Callable[[_ConsumerDiagnostic], None] | None = None,
    input_materializer: Callable[[TypeSchema, object], object] | None = materialize_json,
) -> tuple[_ConsumerDiagnostic, ...]:
    """Run one serial inbound consumer until stopped, drained, or settlement fails."""
    if not isinstance(binding, _CompiledEventBinding):
        raise TypeError("binding must be a _CompiledEventBinding")
    if not isinstance(container, DIContainer):
        raise TypeError("container must be a DIContainer")
    if not isinstance(budgets, _ConsumerBudgets):
        raise TypeError("budgets must be a _ConsumerBudgets")

    subscription_id = binding.exposure.subscription_id
    diagnostics: list[_ConsumerDiagnostic] = []

    def record(correlation_id: str, outcome: str, action: _SettlementAction) -> None:
        entry = _ConsumerDiagnostic(
            correlation_id=correlation_id,
            subscription_id=subscription_id,
            outcome=outcome,
            settlement=action.value,
        )
        diagnostics.append(entry)
        if on_diagnostic is not None:
            on_diagnostic(entry)

    async def next_delivery() -> _Delivery | None:
        if stop_event.is_set():
            await source.stop_receiving()
            return None
        receive_task = asyncio.create_task(source.receive())
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                (receive_task, stop_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_event.is_set():
                await _cancel_and_join(stop_task)
                await source.stop_receiving()
                if receive_task in done and not receive_task.cancelled():
                    if receive_task.exception() is None:
                        unstarted = receive_task.result()
                        if unstarted is not None:
                            await _settle(
                                unstarted,
                                _SettlementAction.RELEASE,
                                correlation_id=uuid.uuid4().hex,
                                subscription_id=subscription_id,
                                outcome="stopped_before_entry",
                            )
                    return None
                await _cancel_and_join(receive_task)
                return None

            await _cancel_and_join(stop_task)
            return await receive_task
        except asyncio.CancelledError:
            await _cancel_and_join(stop_task)
            await _cancel_and_join(receive_task)
            raise

    while True:
        delivery = await next_delivery()
        if delivery is None:
            break

        correlation_id = uuid.uuid4().hex
        try:
            decoded = _decode_cloudevent(
                delivery.body,
                delivery.content_type,
                expected_type=binding.exposure.event_type,
            )
        except _EnvelopeError as error:
            await _settle(
                delivery,
                _SettlementAction.REJECT,
                correlation_id=correlation_id,
                subscription_id=subscription_id,
                outcome=error.category,
            )
            record(correlation_id, error.category, _SettlementAction.REJECT)
            continue

        deadline = asyncio.get_running_loop().time() + budgets.attempt_seconds
        context = ExecutionContext(
            Invocation(
                binding.plan.definition.id,
                dict(decoded.data),
                {},
                deadline=deadline,
            ),
            container,
            principal=binding.exposure.principal,
        )

        invoke_task = asyncio.create_task(
            invoke_result(
                binding.plan,
                context,
                input_materializer=input_materializer,
            )
        )
        stop_wait = asyncio.create_task(stop_event.wait())
        stopped_during_attempt = False
        cancelled_for_shutdown = False
        result = None
        try:
            done, _ = await asyncio.wait(
                (invoke_task, stop_wait),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if invoke_task in done:
                await _cancel_and_join(stop_wait)
                result = await invoke_task
                if stop_event.is_set():
                    stopped_during_attempt = True
                    await source.stop_receiving()
            else:
                await _cancel_and_join(stop_wait)
                stopped_during_attempt = True
                await source.stop_receiving()
                try:
                    async with asyncio.timeout(budgets.shutdown_seconds):
                        result = await invoke_task
                except TimeoutError:
                    cancelled_for_shutdown = True
                    if not invoke_task.done():
                        invoke_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await invoke_task
        except asyncio.CancelledError:
            await _cancel_and_join(stop_wait)
            await _cancel_and_join(invoke_task)
            with contextlib.suppress(Exception):
                await source.stop_receiving()
            with contextlib.suppress(Exception):
                await delivery.release()
            raise

        if cancelled_for_shutdown:
            outcome = "cancelled"
            action = _SettlementAction.RELEASE
        elif isinstance(result, Failure):
            outcome = result.code.value
            action = _settlement_for_failure(result.code)
        else:
            # ADR 0101: discard successful output after acknowledgement.
            outcome = "success"
            action = _SettlementAction.ACKNOWLEDGE

        await _settle(
            delivery,
            action,
            correlation_id=correlation_id,
            subscription_id=subscription_id,
            outcome=outcome,
        )
        record(correlation_id, outcome, action)

        if stopped_during_attempt:
            break

    return tuple(diagnostics)

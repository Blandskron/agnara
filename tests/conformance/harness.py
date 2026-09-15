"""Framework-neutral interoperability harness for host lifecycle and composition.

This stays in the repository test tier. It does not create a public package or a
public API; it provides a reusable contract for exercising the same behavior
against multiple host implementations while keeping the behavioral assertions
framework-neutral.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


class HostContractError(RuntimeError):
    """Raised when a host fixture fails the shared lifecycle or context contract."""


@dataclass
class HostFixture:
    """Minimal host contract used by the conformance harness.

    A fixture owns startup/shutdown and can run one sync or async capability call.
    The harness asserts the behavior, not the framework-specific implementation.
    """

    name: str
    events: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")
        if self.events.count("stop") > 1:
            raise HostContractError(f"{self.name}: shutdown called more than once")

    def call_sync(self, value: object) -> str:
        self.events.append("sync")
        return f"sync:{self.name}:{value}"

    def call_async(self, value: object) -> str:
        self.events.append("async")
        return f"async:{self.name}:{value}"

    def invoke(self, value: object, *, async_mode: bool = False) -> str:
        return self.call_async(value) if async_mode else self.call_sync(value)


class DirectAgnaraHost(HostFixture):
    """Standalone, direct Agnara host fixture used as the minimal positive case."""

    pass


class SideBySideHost(HostFixture):
    """A native host that shares one process and a single lifecycle with Agnara."""

    pass


class BrokenHostFixture(HostFixture):
    """Controlled bad fixture used to verify the harness catches lifecycle drift."""

    def start(self) -> None:
        self.events.append("start")
        raise HostContractError(f"{self.name}: startup failed")

    def stop(self) -> None:
        self.events.append("cleanup")
        raise HostContractError(f"{self.name}: shutdown did not clean up state")


class HostHarness:
    """Framework-neutral runner for same-logic host conformance tests."""

    def _execute(self, action: Callable[[HostFixture], T | Awaitable[T]], host: HostFixture) -> T:
        result = action(host)
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        if isinstance(result, Awaitable):
            return asyncio.run(result)
        return result

    def run_case(
        self,
        host: HostFixture,
        mode: str,
        action: Callable[[HostFixture], T | Awaitable[T]],
        assertion: Callable[[T], bool],
    ) -> T:
        host.start()
        try:
            value = self._execute(action, host)
            if not assertion(value):
                raise HostContractError(f"{host.name}: assertion failed for {mode}")
            return value
        finally:
            host.stop()

    def run_side_by_side(
        self,
        native: HostFixture,
        agnara: HostFixture,
        action: Callable[[HostFixture], T | Awaitable[T]],
        assertion: Callable[[T], bool],
    ) -> dict[str, T]:
        native.start()
        agnara.start()
        try:
            native_value = self._execute(action, native)
            agnara_value = self._execute(action, agnara)
            if not assertion(native_value) or not assertion(agnara_value):
                raise HostContractError("side-by-side host assertion failed")
            return {"native": native_value, "agnara": agnara_value}
        finally:
            native.stop()
            agnara.stop()

"""External-host consumer that retains FastAPI routing and lifecycle ownership."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from agnara import Agnara, App, CapabilityId, Principal
from agnara.di import DIContainer, DIRegistry
from agnara.execution import (
    CapabilityRuntime,
    ExecutionContext,
    ExecutionPlan,
    Failure,
    Invocation,
    Success,
)


@dataclass
class State:
    runtime: CapabilityRuntime | None = None
    container: DIContainer | None = None
    plan: ExecutionPlan | None = None
    closed: bool = False


def compile_runtime() -> tuple[CapabilityRuntime, DIContainer, ExecutionPlan]:
    project = Agnara("dogfood_embedded")
    app = App("orders")

    @app.capability(scopes=("orders:read",))
    def summary(order_id: str) -> dict[str, str]:
        return {"order": order_id, "status": "ready"}

    project.include(app)
    capabilities = project.compile()
    registry = DIRegistry()
    container = DIContainer(registry)
    plan = ExecutionPlan.compile(capabilities["orders.summary"], registry)
    return CapabilityRuntime(capabilities, (plan,), container), container, plan


def build_host(state: State) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.runtime, state.container, state.plan = compile_runtime()
        try:
            yield
        finally:
            assert state.runtime is not None
            await state.runtime.aclose()
            state.runtime = state.container = state.plan = None
            state.closed = True

    host = FastAPI(lifespan=lifespan)

    @host.get("/native")
    async def native() -> dict[str, str]:
        return {"owner": "fastapi"}

    @host.get("/orders/{order_id}")
    async def summary(
        order_id: str, authorization: str | None = Header(default=None)
    ) -> JSONResponse:
        if authorization != "Bearer consumer":
            raise HTTPException(status_code=401, detail="host authentication failed")
        assert state.runtime is not None and state.container is not None and state.plan is not None
        result = await state.runtime.invoke_result(
            ExecutionContext(
                Invocation(CapabilityId.parse("orders.summary"), {"order_id": order_id}, {}),
                state.container,
                principal=Principal("consumer", scopes=("orders:read",)),
            )
        )
        if isinstance(result, Success):
            return JSONResponse(result.value)
        assert isinstance(result, Failure)
        return JSONResponse({"code": result.code.value}, status_code=403)

    return host


async def request(
    host: FastAPI, path: str, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, object]]:
    sent: list[dict[str, Any]] = []
    received = False

    async def receive() -> MutableMapping[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: MutableMapping[str, Any]) -> None:
        sent.append(dict(message))

    await host(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(key.encode(), value.encode()) for key, value in (headers or {}).items()],
            "client": ("127.0.0.1", 9000),
            "server": ("test", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent)
    return int(start["status"]), json.loads(body)


async def main() -> None:
    state = State()
    host = build_host(state)
    async with host.router.lifespan_context(host):
        assert await request(host, "/native") == (200, {"owner": "fastapi"})
        status, body = await request(host, "/orders/A-1", {"authorization": "Bearer consumer"})
        assert status == 200 and body == {"order": "A-1", "status": "ready"}
        status, _ = await request(host, "/orders/A-1")
        assert status == 401
    assert state.closed
    print("EMBEDDED_DOGFOOD_OK")


if __name__ == "__main__":
    asyncio.run(main())

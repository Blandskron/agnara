"""Run exact application-owned sources against installed wheels and real TCP."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def snapshot(state: Any) -> dict[str, Any]:
    return {
        "effects": list(state.effects),
        "lifecycle": list(state.lifecycle),
        "pools_closed": [p.closed for p in state.pools],
        "ledgers_closed": [r.closed for r in state.ledgers],
        "active": state.active,
    }


def validate(outcome: dict[str, Any]) -> None:
    # The same independent wire/effect validator checks the base guide in
    # unwrapped and opt-in modes; no checkout import is required under -I.
    runpy.run_path(str(HERE / "a2a_guide.py"))["validate"](outcome["in_process"])
    assert set(outcome["disconnects"]) == {"mid_body", "handler"}
    for stage, case in outcome["disconnects"].items():
        assert case["responses_after_disconnect"] == []
        assert case["active_after_disconnect"] == 0 and case["recovery"] == 8
        expected = (
            []
            if stage == "mid_body"
            else [
                "pool.open",
                "ledger.open",
                "handler.enter",
                "handler.cancel",
                "handler.close",
                "ledger.close",
            ]
        )
        assert case["disconnect_effects"] == expected
        expected += (["pool.open"] if stage == "mid_body" else []) + [
            "ledger.open",
            "handler.enter",
            "handler.close",
            "ledger.close",
            "pool.close",
        ]
        assert case["effects"] == expected
        assert case["pools_closed"] == [True]
        assert case["ledgers_closed"] == [True] * (1 if stage == "mid_body" else 2)
    limits = outcome["limits"]
    assert limits["unauthenticated"] == 401 and limits["body_read_before_refusal"] is False
    assert limits["invalid"] == "invalid_input" and limits["denied"] == "forbidden"
    assert limits["oversized"] == 413 and limits["rejected_effects"] == []
    assert limits["recovery"] == 8
    assert limits["effects"] == [
        "pool.open",
        "ledger.open",
        "handler.enter",
        "handler.close",
        "ledger.close",
        "pool.close",
    ]
    shutdown = outcome["shutdown"]
    assert shutdown["resources_alive_during_drain"] is True and shutdown["result"] == -4
    assert shutdown["effects"] == limits["effects"]
    assert limits["ledgers_closed"] == shutdown["ledgers_closed"] == [True]
    assert shutdown["lifecycle"].index("request.close") < shutdown["lifecycle"].index(
        "container.close"
    )
    for case in (*outcome["disconnects"].values(), limits, shutdown):
        assert case["active"] == 0
        assert case["lifecycle"][-3:] == ["requests.drained", "container.close", "lifespan.close"]
        assert case["pools_closed"] == [True] and all(case["ledgers_closed"])


async def run_guide(path: Path, *, network_fixture: Path | None = None) -> dict[str, Any]:
    import httpx

    recipe = runpy.run_path(str(path))
    demonstration = runpy.run_path(str(path.parent / "a2a_service.py"))
    host = runpy.run_path(str(network_fixture or HERE / "a2a_network_fixture.py"))
    wrap = recipe["cancel_on_disconnect"]
    serve, official, envelope = host["serve"], host["official"], host["envelope"]
    raw_client, category = host["raw_client"], host["category"]
    before = asyncio.all_tasks()
    result: dict[str, Any] = {"disconnects": {}}
    async with asyncio.timeout(25):
        result["in_process"] = await demonstration["demonstrate"](wrap=wrap)
        for stage in ("mid_body", "handler"):
            # A 30s kernel deadline cannot explain success inside the host's
            # outer 15s bound. The recipe must cancel and join on actual EOF.
            async with serve(timeout=30, wrap=wrap) as (url, state, _):
                payload = b"{" if stage == "mid_body" else json.dumps(envelope(-1)).encode()
                _, writer = await raw_client(
                    url, payload, 1000 if stage == "mid_body" else len(payload)
                )
                try:
                    await (state.body_received if stage == "mid_body" else state.entered).wait()
                finally:
                    writer.close()
                    await writer.wait_closed()
                await state.request_closed.wait()
                case = {
                    "responses_after_disconnect": list(state.outcomes),
                    "disconnect_effects": list(state.effects),
                    "active_after_disconnect": state.active,
                }
                async with httpx.AsyncClient(
                    base_url=url, headers=host["HEADERS"], trust_env=False
                ) as http:
                    case["recovery"] = await official(http, url, 4)
            case.update(snapshot(state))
            result["disconnects"][stage] = case

        async with (
            serve(timeout=30, wrap=wrap, max_body_bytes=1024) as (url, state, _),
            httpx.AsyncClient(base_url=url, headers=host["HEADERS"], trust_env=False) as http,
        ):
            response = await http.post("/", content=b"{", headers={"Authorization": "unknown"})
            limits = {
                "unauthenticated": response.status_code,
                "body_read_before_refusal": state.body_received.is_set(),
            }
            invalid = await http.post("/", json=envelope("bad"))
            denied = await http.post(
                "/", json=envelope(3), headers={"Authorization": "Bearer fixture-unscoped"}
            )
            oversized = await http.post("/", content=b"x" * 1025)
            limits.update(
                {
                    "invalid": category(invalid.json()),
                    "denied": category(denied.json()),
                    "oversized": oversized.status_code,
                    "rejected_effects": list(state.effects),
                    "recovery": await official(http, url, 4),
                }
            )
        limits.update(snapshot(state))
        result["limits"] = limits

        async with (
            serve(timeout=5, wrap=wrap) as (url, state, server),
            httpx.AsyncClient(
                base_url=url, headers=host["HEADERS"], trust_env=False, timeout=10
            ) as http,
        ):
            async with asyncio.TaskGroup() as owned:
                request = owned.create_task(http.post("/", json=envelope(-2)))
                await state.entered.wait()
                server.should_exit = True
                while any(s.is_serving() for s in server.servers):
                    await asyncio.sleep(0.01)
                alive = not state.pools[0].closed and not state.ledgers[0].closed
                state.release.set()
            wire_result = request.result().json()["result"]["message"]["parts"][0]["data"]["result"]
        result["shutdown"] = {
            **snapshot(state),
            "resources_alive_during_drain": alive,
            "result": wire_result,
        }
    assert asyncio.all_tasks() == before, "recipe/host tasks survived installed-source teardown"
    return result


if __name__ == "__main__":
    assert sys.flags.isolated, "installed-source evidence requires Python -I"
    validate(asyncio.run(run_guide(Path(sys.argv[1]).resolve())))
    print("A2A_DISCONNECT_RECIPE_ARTIFACT_OK")

"""Exercise the public A2A example and its actual resource ownership."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from examples.a2a_service import connect, demonstrate, resolve_principal, send

from agnara import Principal
from tests.reference_apps.a2a_guide import validate


@pytest.fixture(scope="module")
def outcome():
    async def run():
        before = asyncio.all_tasks()
        result = await demonstrate()
        assert asyncio.all_tasks() == before
        return result

    return asyncio.run(run())


def test_guide_outcomes_and_effects(outcome) -> None:
    validate(outcome)


def test_resolver_uses_only_host_verified_identity() -> None:
    assert resolve_principal({"headers": [(b"authorization", b"Bearer demo-reader")]}) is None
    principal = Principal("verified", scopes={"catalog:read"})
    assert resolve_principal({"demo.verified_principal": principal}) is principal


@pytest.mark.parametrize("failure", ["error", "cancel"])
def test_client_work_failure_closes_http_lifespan_and_container(failure: str) -> None:
    async def run():
        events: list[str] = []
        entered = asyncio.Event()
        clients = []

        async def work():
            async with connect(events) as (http, client):
                clients.append(http)
                await send(client, 3)
                entered.set()
                if failure == "error":
                    raise ValueError("client work failed")
                await asyncio.Event().wait()

        before = asyncio.all_tasks()
        async with asyncio.timeout(10):
            if failure == "error":
                with pytest.raises(ExceptionGroup, match="TaskGroup") as caught:
                    await work()
                assert isinstance(caught.value.exceptions[0], ValueError)
            else:
                async with asyncio.TaskGroup() as owned:
                    task = owned.create_task(work())
                    await entered.wait()
                    task.cancel()
                assert task.cancelled()
        assert clients[0].is_closed
        assert events == [
            "pool.open",
            "ledger.open",
            "total:3",
            "ledger.close",
            "client.close",
            "http.close",
            "lifespan.close",
            "pool.close",
            "container.close",
        ]
        assert asyncio.all_tasks() == before

    asyncio.run(run())


@pytest.mark.parametrize("corruption", ["effects", "result", "failure", "cleanup", "identity"])
def test_artifact_validator_rejects_incorrect_evidence(outcome, corruption: str) -> None:
    changed = deepcopy(outcome)
    if corruption == "effects":
        changed["rejected_effects"] = ["pool.open"]
    elif corruption == "result":
        changed["results"]["valid"]["message"]["parts"][0]["data"]["result"] = 31
    elif corruption == "failure":
        changed["results"]["denied"]["error"]["data"][0]["metadata"]["agnaraCode"] = "timeout"
    elif corruption == "identity":
        changed["results"]["recovered"]["message"]["messageId"] = changed["results"]["valid"][
            "message"
        ]["messageId"]
    else:
        changed["events"][-2:] = reversed(changed["events"][-2:])
    with pytest.raises(AssertionError):
        validate(changed)


def test_example_runs_outside_checkout(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2] / "examples" / "a2a_service.py"
    completed = subprocess.run(
        [sys.executable, str(source)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines()[:8] == [
        "protocol: 1.0",
        "unauthenticated: 401",
        "invalid_input: invalid_input",
        "forged_dependency: invalid_input",
        "denied: forbidden",
        "valid: 30.0",
        "handler_failure: internal_failure",
        "recovered: 10.0",
    ]

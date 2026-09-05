"""E8.10: publication boundaries across every Explorer view and outcome."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from agnara.introspection import DiscoveryVisibility, Hiding, ScopeVisible
from agnara.policy import Principal
from agnara_http._discovery import _compile_discovery, _DiscoveryDispatcher, _DiscoveryRoute
from agnara_http._dispatch import _compile_exposures
from agnara_http._explorer import _compile_explorer, _ExplorerDispatcher
from tests.http.test_explorer_shell import BASE, Fallback, built, dispatcher, request, route

PAGES = (BASE, f"{BASE}/app/billing", f"{BASE}/billing.refund")


@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("identity", [None, "invalid", "raises"])
def test_every_view_fails_closed_before_publishing(path: str, identity: str | None) -> None:
    def resolve(scope: Any) -> Any:
        if identity == "raises":
            raise RuntimeError("credential-store-secret")
        return identity

    served, _ = dispatcher(route(principals=resolve))
    status, headers, body = request(served, path)
    assert status == (401 if identity is None else 500)
    assert "credential-store-secret" not in body
    assert "Refund a captured payment" not in body
    if identity is None:
        assert headers[b"www-authenticate"] == b"Bearer"


@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("outcome", ["success", "anonymous", "broken", "hidden", "method"])
def test_all_outcomes_prevent_storage_and_head_preserves_headers(path: str, outcome: str) -> None:
    overrides: dict[str, Any] = {}
    if outcome == "anonymous":
        overrides["principals"] = lambda scope: None
    elif outcome == "broken":
        overrides["principals"] = lambda scope: "not a principal"
    elif outcome == "hidden":
        overrides["visibility"] = DiscoveryVisibility.agent_safe(
            Hiding({"billing.refund", "billing.health"}, ScopeVisible())
        )
    served, _ = dispatcher(route(**overrides))
    method = "POST" if outcome == "method" else "GET"
    status, headers, body = request(served, path, method)
    expected = {"success": 200, "anonymous": 401, "broken": 500, "method": 405}
    assert status == expected.get(outcome, 200 if path == BASE else 404)
    assert headers[b"cache-control"] == b"private, no-store"
    assert headers[b"vary"] == b"Authorization"
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert b"frame-ancestors 'none'" in headers[b"content-security-policy"]
    assert body
    if method == "GET":
        assert request(served, path, "HEAD") == (status, headers, "")
    else:
        assert headers[b"allow"] == b"GET, HEAD"


@pytest.mark.parametrize("path", PAGES)
def test_identity_only_view_withholds_metadata_on_every_page(path: str) -> None:
    served, _ = dispatcher(route(visibility=DiscoveryVisibility.identity_only(ScopeVisible())))
    status, _, body = request(served, path)
    assert status == 200
    assert "Partial view." in body
    for withheld in (
        "Refund a captured payment",
        "financial-write",
        "billing:write",
        "Ledger",
        "POST /refunds",
        "payment_id",
    ):
        assert withheld not in body


def test_hidden_application_and_absent_application_have_equivalent_problems() -> None:
    served, _ = dispatcher(
        route(
            visibility=DiscoveryVisibility.agent_safe(
                Hiding({"billing.refund", "billing.health"}, ScopeVisible())
            )
        )
    )
    answers = [request(served, f"{BASE}/app/{name}") for name in ("billing", "absent")]
    problems = []
    for status, headers, body in answers:
        assert status == 404
        assert headers[b"cache-control"] == b"private, no-store"
        document = json.loads(body)
        document.pop("instance", None)
        problems.append(document)
    assert problems[0] == problems[1]


def test_anonymous_opt_in_still_filters_scoped_capabilities() -> None:
    served, _ = dispatcher(
        route(principals=lambda scope: None, allow_anonymous=True, challenge=None)
    )
    status, headers, body = request(served)
    assert status == 200
    assert b"www-authenticate" not in headers
    assert "billing.health" in body
    assert "billing.refund" not in body
    assert request(served, PAGES[2])[0] == 404


def test_errors_ignore_a_configured_private_page_cache_lifetime() -> None:
    served, _ = dispatcher(route(cache_control="private, max-age=60"))
    assert request(served)[1][b"cache-control"] == b"private, max-age=60"
    status, headers, _ = request(served, f"{BASE}/missing")
    assert status == 404
    assert headers[b"cache-control"] == b"private, no-store"


def test_overlapping_requests_do_not_reuse_another_viewers_document() -> None:
    original = built()
    before = original.json_data()
    served, _ = dispatcher(route(snapshot=original, principals=lambda scope: scope["viewer"]))

    async def exchange(path: str, privileged: bool) -> tuple[int, str]:
        events: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            raise AssertionError("read-only Explorer must not consume a body")

        async def send(message: dict[str, Any]) -> None:
            await asyncio.sleep(0)
            events.append(message)

        await served(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "root_path": "",
                "viewer": Principal(
                    "writer" if privileged else "reader",
                    scopes={"billing:write"} if privileged else set(),
                ),
            },
            receive,
            send,
        )
        return events[0]["status"], b"".join(event.get("body", b"") for event in events).decode()

    async def run() -> None:
        async with asyncio.TaskGroup() as group:
            cases = [
                (path, privileged)
                for _ in range(3)
                for path in PAGES
                for privileged in (True, False)
            ]
            tasks = [group.create_task(exchange(path, privileged)) for path, privileged in cases]
        for (path, privileged), task in zip(cases, tasks, strict=True):
            status, body = task.result()
            assert status == (404 if not privileged and path == PAGES[2] else 200)
            assert ("Refund a captured payment" in body) is privileged

    asyncio.run(run())
    assert original.json_data() == before


@pytest.mark.parametrize("enabled", [False, True])
def test_explorer_can_be_omitted_while_machine_discovery_remains_available(enabled: bool) -> None:
    declared = route()
    fallback = Fallback()
    discovery = _DiscoveryDispatcher(
        _compile_discovery(
            _DiscoveryRoute(
                path="/discovery",
                snapshot=declared.snapshot,
                visibility=declared.visibility,
                principals=declared.principals,
                challenge="Bearer",
            ),
            _compile_exposures(()),
        ),
        fallback,
    )
    served: Any = (
        _ExplorerDispatcher(_compile_explorer(declared, _compile_exposures(())), discovery)
        if enabled
        else discovery
    )
    for path in PAGES:
        assert request(served, path)[0] == (200 if enabled else 299)
    status, headers, body = request(served, "/discovery")
    assert status == 200
    assert headers[b"content-type"].startswith(b"application/json")
    assert json.loads(body)["format"] == "agnara-introspection"

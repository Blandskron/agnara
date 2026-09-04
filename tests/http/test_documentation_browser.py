"""Real-browser conformance for the pinned documentation providers (E6.18)."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from agnara_http._documentation import (
    _DocumentationRegistry,
    _DocumentationRequest,
    _DocumentationUnavailable,
)
from agnara_http._redoc import _ReDocProvider
from agnara_http._scalar import _ScalarProvider
from agnara_http._swagger import _SwaggerUIProvider
from tests.http.browser._host import DocumentationHost, documentation_app, empty_app, header_map

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("AGNARA_RUN_BROWSER_TESTS") != "1",
        reason="real-browser tests run only in their explicit CI job",
    ),
]

_XSS_MARKER = "agnara_xss_executed"
_XSS = (
    '<img src="https://evil.invalid/agnara.png" '
    f'onerror="window.{_XSS_MARKER}=true">'
    f"<script>window.{_XSS_MARKER}=true</script>"
)


@dataclass(frozen=True, slots=True)
class ProviderCase:
    name: str
    provider: object
    openapi_version: str
    ready_selector: str
    expected_blocked_origin: str | None = None


CASES = (
    ProviderCase("swagger-ui", _SwaggerUIProvider(), "3.2.0", "#swagger-ui .info"),
    ProviderCase(
        "redoc",
        _ReDocProvider(),
        "3.1.0",
        "#redoc-container h1",
        "https://cdn.redoc.ly",
    ),
    ProviderCase(
        "scalar",
        _ScalarProvider(),
        "3.2.0",
        "#scalar-api-reference",
        "https://fonts.scalar.com",
    ),
)

type _OpenedPage = tuple[
    BrowserContext,
    Page,
    DocumentationHost,
    list[str],
    list[str],
    list[str],
    list[str],
    list[str],
]


def _document(version: str) -> bytes:
    document = {
        "openapi": version,
        "info": {
            "title": "Agnara Browser Fixture",
            "version": "1.0.0",
            "description": _XSS,
        },
        "paths": {
            "/widgets": {
                "get": {
                    "operationId": "widgets.list",
                    "summary": "List widgets",
                    "description": _XSS,
                    "security": [{"browserOAuth": ["widgets:read"]}],
                    "responses": {
                        "200": {
                            "description": "Widgets returned",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "browserOAuth": {
                    "type": "oauth2",
                    "flows": {
                        "authorizationCode": {
                            "authorizationUrl": "/oauth/authorize",
                            "tokenUrl": "/oauth/token",
                            "scopes": {"widgets:read": "Read widgets"},
                        }
                    },
                }
            }
        },
    }
    return json.dumps(document, separators=(",", ":")).encode("utf-8")


def _request(case: ProviderCase, *, try_it: bool = False) -> _DocumentationRequest:
    return _DocumentationRequest(
        document_url="/openapi.json",
        title=f"Agnara </title><script>window.{_XSS_MARKER}=true</script>",
        assets_url=f"/{case.name}/assets",
        openapi_version=case.openapi_version,
        try_it=try_it,
    )


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        channel = os.environ.get("AGNARA_BROWSER_CHANNEL")
        options: dict[str, Any] = {"headless": True}
        if channel:
            options["channel"] = channel
        launched = playwright.chromium.launch(**options)
        try:
            yield launched
        finally:
            launched.close()


def _render(case: ProviderCase, *, try_it: bool = False):
    request = _request(case, try_it=try_it)
    registry = _DocumentationRegistry()
    provider = registry.register(case.provider)
    page = registry.render(provider.name, request)
    return request, page, _document(case.openapi_version)


@contextmanager
def _open(
    browser: Browser,
    case: ProviderCase,
    *,
    try_it: bool = False,
    viewport: Any = None,
) -> Iterator[_OpenedPage]:
    request, rendered, document = _render(case, try_it=try_it)
    with DocumentationHost(documentation_app(rendered, request, document)) as host:
        context = browser.new_context(viewport=viewport)
        page = context.new_page()
        page_errors: list[str] = []
        console_errors: list[str] = []
        external_requests: list[str] = []
        external_responses: list[str] = []
        error_responses: list[str] = []

        def record_request(request: Any) -> None:
            parsed = urlsplit(request.url)
            if parsed.scheme in {"http", "https"} and parsed.netloc != urlsplit(host.origin).netloc:
                external_requests.append(request.url)

        def record_response(response: Any) -> None:
            if response.url.startswith(f"blob:{host.origin}/"):
                return
            if urlsplit(response.url).netloc != urlsplit(host.origin).netloc:
                external_responses.append(response.url)
            elif response.status >= 400:
                error_responses.append(f"{response.status} {response.url}")

        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("request", record_request)
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on("response", record_response)
        page.goto(host.url("/docs"), wait_until="domcontentloaded")
        page.locator(case.ready_selector).first.wait_for(state="visible")
        try:
            yield (
                context,
                page,
                host,
                page_errors,
                console_errors,
                external_requests,
                external_responses,
                error_responses,
            )
        finally:
            context.close()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_provider_renders_with_enforced_csp_and_no_successful_external_requests(
    browser: Browser, case: ProviderCase
) -> None:
    with _open(browser, case) as (
        _context,
        page,
        host,
        page_errors,
        console_errors,
        external_requests,
        external_responses,
        error_responses,
    ):
        response = page.request.get(host.url("/docs"))
        headers = header_map(response.headers)
        csp = headers["content-security-policy"]

        assert response.status == 200
        assert "default-src 'none'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        if case.name == "redoc":
            assert "worker-src 'self' blob:" in csp
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["x-frame-options"] == "DENY"
        assert headers["cache-control"] == "no-store"
        assert page.get_by_text("Agnara Browser Fixture", exact=False).first.is_visible()
        assert page.evaluate(f"window.{_XSS_MARKER} === true") is False
        assert page_errors == []
        assert any("https://evil.invalid/agnara.png" in message for message in console_errors)
        if case.expected_blocked_origin is not None:
            assert any(case.expected_blocked_origin in message for message in console_errors)

        unexpected_console = [
            message
            for message in console_errors
            if "https://evil.invalid/agnara.png" not in message
            and (
                case.expected_blocked_origin is None or case.expected_blocked_origin not in message
            )
            and "Failed to load resource" not in message
        ]
        assert unexpected_console == []

        expected_origins = {"https://evil.invalid"}
        if case.expected_blocked_origin is not None:
            expected_origins.add(case.expected_blocked_origin)
        observed_origins = {
            f"{urlsplit(url).scheme}://{urlsplit(url).netloc}" for url in external_requests
        }
        assert observed_origins == expected_origins
        assert external_responses == []
        assert error_responses == []


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_provider_has_keyboard_and_mobile_smoke_evidence(
    browser: Browser, case: ProviderCase
) -> None:
    viewport = {"width": 390, "height": 844}
    with _open(browser, case, viewport=viewport) as (
        _context,
        page,
        _host,
        page_errors,
        _console_errors,
        _external_requests,
        _external_responses,
        _error_responses,
    ):
        dimensions = page.evaluate(
            """() => ({
              viewport: window.innerWidth,
              document: document.documentElement.scrollWidth,
              body: document.body.scrollWidth
            })"""
        )
        page.keyboard.press("Tab")
        active = page.evaluate("document.activeElement && document.activeElement.tagName")
        aria = page.locator("body").aria_snapshot()

        assert dimensions["document"] <= dimensions["viewport"] + 1
        assert dimensions["body"] <= dimensions["viewport"] + 1
        assert active not in {None, "BODY", "HTML"}
        assert "Agnara Browser Fixture" in aria
        assert page_errors == []


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_credentials_are_not_persisted_by_default(browser: Browser, case: ProviderCase) -> None:
    with _open(browser, case) as (
        _context,
        page,
        _host,
        _page_errors,
        _console_errors,
        _external_requests,
        _external_responses,
        _error_responses,
    ):
        keys = page.evaluate(
            """() => ({
              local: Object.keys(localStorage),
              session: Object.keys(sessionStorage)
            })"""
        )
        sensitive = re.compile(r"auth|token|bearer|credential", re.IGNORECASE)
        assert [key for key in (*keys["local"], *keys["session"]) if sensitive.search(key)] == []


@pytest.mark.parametrize(
    "case",
    (CASES[0], CASES[2]),
    ids=lambda case: case.name,
)
def test_try_it_controls_follow_the_independent_selection(
    browser: Browser, case: ProviderCase
) -> None:
    pattern = re.compile(r"try it out|test request|send request", re.IGNORECASE)
    with _open(browser, case) as (
        _context,
        page,
        _host,
        _page_errors,
        _console_errors,
        _external_requests,
        _external_responses,
        _error_responses,
    ):
        page.get_by_text("List widgets", exact=False).first.click()
        assert page.get_by_role("button", name=pattern).count() == 0

    with _open(browser, case, try_it=True) as (
        _context,
        page,
        _host,
        _page_errors,
        _console_errors,
        _external_requests,
        _external_responses,
        _error_responses,
    ):
        page.get_by_text("List widgets", exact=False).first.click()
        page.get_by_role("button", name=pattern).first.wait_for(state="visible")


def test_swagger_oauth_redirect_boundary_is_same_origin_unpublished_and_secretless(
    browser: Browser,
) -> None:
    case = CASES[0]
    with _open(browser, case, try_it=True) as (
        _context,
        page,
        host,
        _page_errors,
        _console_errors,
        _external_requests,
        _external_responses,
        _error_responses,
    ):
        page.wait_for_function("window.ui && window.ui.getConfigs")
        redirect = page.evaluate("window.ui.getConfigs().oauth2RedirectUrl")
        assert redirect == host.url("/oauth2-redirect.html")
        assert page.request.get(redirect).status == 404
        assert "client_secret" not in page.content().lower()


def test_disabled_documentation_route_is_absent_in_a_real_browser(browser: Browser) -> None:
    with DocumentationHost(empty_app()) as host:
        context = browser.new_context()
        page = context.new_page()
        response = page.goto(host.url("/docs"))
        try:
            assert response is not None
            assert response.status == 404
            assert page.locator("text=not found").is_visible()
        finally:
            context.close()


def test_redoc_refuses_canonical_openapi_32_before_a_browser_can_render_it() -> None:
    registry = _DocumentationRegistry()
    provider = _ReDocProvider()
    registry.register(provider)
    request = _DocumentationRequest(
        document_url="/openapi.json",
        title="Agnara Browser Fixture",
        assets_url="/redoc/assets",
        openapi_version="3.2.0",
    )

    with pytest.raises(_DocumentationUnavailable, match=r"does not support OpenAPI 3\.2\.0"):
        registry.render(provider.name, request)

"""Browser smoke coverage for the supported documentation composition API."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, sync_playwright

from agnara import Agnara
from agnara_http import (
    Binding,
    BindingSource,
    Http,
    HttpDocumentation,
    OpenApiInfo,
    OpenApiOperation,
)
from tests.http.browser._host import DocumentationHost

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("AGNARA_RUN_BROWSER_TESTS") != "1",
        reason="real-browser tests run only in their explicit CI job",
    ),
]


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


def _application():
    app = Agnara("public_docs")

    @app.capability(description="Read the public documentation fixture.")
    def show(widget_id: str) -> dict[str, str]:
        return {"id": widget_id}

    http = Http()
    http.get(
        "/widgets/{widget_id}",
        show,
        Binding("widget_id", BindingSource.PATH),
        openapi=OpenApiOperation(summary="Show a widget", publish_description=True),
    )
    return http.compile(
        app.compile(),
        openapi=OpenApiInfo("Public documentation fixture", "1.0.0"),
        documentation=HttpDocumentation(),
    )


def test_default_public_swagger_page_renders_from_the_compiled_asgi_app(browser: Browser) -> None:
    asgi = _application()
    with DocumentationHost(asgi) as host:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        requests: list[str] = []
        page.on("request", lambda request: requests.append(request.url))
        try:
            response = page.goto(host.url("/docs"), wait_until="networkidle")
            assert response is not None and response.status == 200
            page.locator("#swagger-ui .info").wait_for()
            # Swagger UI renders the title as a bare text node beside the version
            # spans, so the heading's own text is never the title alone.
            title = page.locator("#swagger-ui .info .title").text_content()
            assert title is not None and title.startswith("Public documentation fixture")
            assert page.get_by_text("Show a widget", exact=True).count() >= 1
            assert all(url.startswith(host.origin) for url in requests)
            assert page.locator("body").evaluate("node => node.scrollWidth <= window.innerWidth")
        finally:
            page.close()

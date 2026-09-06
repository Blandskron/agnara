"""E8.11: bounded Chromium accessibility and navigation evidence for Explorer.

ARIA snapshots check the browser accessibility tree, not a screen reader.
These representative fixtures do not establish WCAG conformance.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from agnara.introspection import DiscoveryVisibility, Hiding, ScopeVisible
from agnara_http._dispatch import _compile_exposures
from agnara_http._explorer import _compile_explorer, _ExplorerDispatcher
from tests.http.browser._host import DocumentationHost, empty_app
from tests.http.test_explorer_shell import BASE, route
from tests.http.test_explorer_views import described

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("AGNARA_RUN_BROWSER_TESTS") != "1",
        reason="real-browser tests run only in their explicit CI job",
    ),
]

PAGES = (
    (BASE, "Agnara Explorer"),
    (f"{BASE}/app/billing", "Application billing"),
    (f"{BASE}/billing.refund", "billing.refund"),
)


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(headless=True)
        try:
            yield launched
        finally:
            launched.close()


@contextmanager
def opened(
    browser: Browser,
    *,
    width: int = 1280,
    visibility: DiscoveryVisibility | None = None,
) -> Iterator[tuple[Page, DocumentationHost]]:
    declared = route(
        snapshot=described(),
        visibility=visibility or DiscoveryVisibility.unrestricted(ScopeVisible()),
    )
    app = _ExplorerDispatcher(_compile_explorer(declared, _compile_exposures(())), empty_app())
    with DocumentationHost(app) as host:
        context = browser.new_context(viewport={"width": width, "height": 844})
        try:
            yield context.new_page(), host
        finally:
            context.close()


@pytest.mark.parametrize(("path", "title"), PAGES)
def test_every_view_has_a_named_heading_language_and_main_landmark(
    browser: Browser, path: str, title: str
) -> None:
    with opened(browser) as (page, host):
        response = page.goto(host.url(path))
        assert response is not None and response.status == 200
        expect(page).to_have_title(title)
        expect(page.locator("html")).to_have_attribute("lang", "en")
        expect(page.get_by_role("main")).to_have_count(1)
        expect(page.get_by_role("heading", level=1)).to_have_count(1)
        expect(
            page.get_by_role("main").get_by_role("heading", name=title, exact=True)
        ).to_be_visible()
        aria = page.get_by_role("main").aria_snapshot()
        assert f'heading "{title}" [level=1]' in aria
        assert "not permission to invoke it" in aria
        links = page.get_by_role("link")
        for index in range(links.count()):
            assert links.nth(index).inner_text().strip()


def test_keyboard_round_trip_and_reverse_tab_order(browser: Browser) -> None:
    with opened(browser) as (page, host):
        page.goto(host.url(BASE))
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Application billing", exact=True)).to_be_focused()
        page.keyboard.press("Enter")
        expect(page).to_have_url(host.url(f"{BASE}/app/billing"))
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Back to the index")).to_be_focused()
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="billing.refund", exact=True)).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(page.get_by_role("link", name="Back to the index")).to_be_focused()
        page.keyboard.press("Tab")
        page.keyboard.press("Enter")
        expect(page).to_have_url(host.url(f"{BASE}/billing.refund"))
        page.keyboard.press("Tab")
        expect(page.get_by_role("link", name="Back to the index")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page).to_have_url(host.url(BASE))


@pytest.mark.parametrize(("path", "title"), PAGES[1:])
def test_direct_links_reload_and_browser_history(browser: Browser, path: str, title: str) -> None:
    with opened(browser) as (page, host):
        page.goto(host.url(path))
        expect(page.get_by_role("heading", level=1)).to_have_text(title)
        page.reload()
        expect(page).to_have_url(host.url(path))
        expect(page.get_by_role("heading", level=1)).to_have_text(title)
        page.get_by_role("link", name="Back to the index").click()
        page.go_back()
        expect(page).to_have_url(host.url(path))
        expect(page.get_by_role("heading", level=1)).to_have_text(title)


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize(("path", "title"), PAGES)
def test_representative_views_fit_the_viewport_without_assets(
    browser: Browser, width: int, path: str, title: str
) -> None:
    with opened(browser, width=width) as (page, host):
        requests: list[str] = []
        page.on("request", lambda request: requests.append(request.url))
        response = page.goto(host.url(path))
        assert response is not None
        assert response.headers["content-security-policy"] == (
            "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert page.evaluate("document.body.scrollWidth <= window.innerWidth")
        assert requests == [host.url(path)]
        expect(page.locator("script, style, link, img, form, input, button")).to_have_count(0)


def test_accessibility_tree_contains_schema_and_provider_structure(browser: Browser) -> None:
    with opened(browser) as (page, host):
        page.goto(host.url(f"{BASE}/billing.refund"))
        aria = page.locator("body").aria_snapshot()
        assert 'heading "Inputs" [level=2]' in aria
        assert "payment_id (required)" in aria
        assert "amount_cents" in aria
        assert "currency" in aria
        page.goto(host.url(f"{BASE}/app/billing"))
        aria = page.locator("body").aria_snapshot()
        assert 'heading "Providers" [level=2]' in aria
        assert "Ledger: invocation async_generator requires Audit" in aria


@pytest.mark.parametrize(("path", "title"), PAGES)
def test_partial_view_names_withheld_fields_in_the_accessibility_tree(
    browser: Browser, path: str, title: str
) -> None:
    with opened(browser, visibility=DiscoveryVisibility.identity_only(ScopeVisible())) as (
        page,
        host,
    ):
        page.goto(host.url(path))
        aria = page.locator("body").aria_snapshot()
        assert title in aria
        assert "Partial view." in aria
        assert "inputs" in aria
        assert "providers" in aria
        for withheld in ("amount_cents", "financial-write", "Ledger", "Refund a captured payment"):
            assert withheld not in aria


def test_empty_view_is_announced_as_empty_and_has_no_hidden_links(browser: Browser) -> None:
    visibility = DiscoveryVisibility.agent_safe(
        Hiding({"billing.refund", "billing.health"}, ScopeVisible())
    )
    with opened(browser, visibility=visibility) as (page, host):
        page.goto(host.url(BASE))
        aria = page.locator("body").aria_snapshot()
        assert "No capabilities are visible to you." in aria
        expect(page.get_by_role("link")).to_have_count(0)
        assert "billing.refund" not in aria

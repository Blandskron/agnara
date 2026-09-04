"""Swagger UI provider pinning, compatibility and secure defaults (E6.15)."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any

import pytest

from agnara_http._documentation import (
    _DocumentationDefinitionError,
    _DocumentationRegistry,
    _DocumentationRequest,
    _DocumentationUnavailable,
)
from agnara_http._swagger import (
    _ASSET_EVIDENCE,
    _SWAGGER_UI_VERSION,
    _UNSUPPORTED_OPENAPI_32_FEATURES,
    _SwaggerUIProvider,
)


def request(**overrides: Any) -> _DocumentationRequest:
    fields: dict[str, Any] = {
        "document_url": "/openapi.json",
        "title": "Agnara API",
        "assets_url": "/docs/assets",
        "openapi_version": "3.2.0",
    }
    fields.update(overrides)
    return _DocumentationRequest(**fields)


def test_local_provider_serves_only_verified_same_origin_assets() -> None:
    provider = _SwaggerUIProvider()
    registry = _DocumentationRegistry()
    registry.register(provider)

    page = registry.render(provider.name, request())
    rendered = page.html.decode()

    assert provider.name == "swagger-ui"
    assert page.csp.external_origins == ()
    assert page.remote_assets == ()
    assert page.csp.inline_script is False
    assert page.csp.inline_style is True
    assert set(page.assets) == {
        "swagger-ui-bundle.js",
        "swagger-ui.css",
        "swagger-initializer.js",
    }
    assert 'href="/docs/assets/swagger-ui.css"' in rendered
    assert 'src="/docs/assets/swagger-ui-bundle.js"' in rendered
    assert 'src="/docs/assets/swagger-initializer.js"' in rendered
    assert "unpkg.com" not in rendered
    assert "integrity=" not in rendered


def test_local_provider_handles_an_asset_root_at_the_origin_root() -> None:
    page = _SwaggerUIProvider().render(request(assets_url="/"))
    rendered = page.html.decode()
    assert 'href="/swagger-ui.css"' in rendered
    assert 'src="/swagger-ui-bundle.js"' in rendered


def test_security_defaults_are_explicit_in_a_non_inline_initializer() -> None:
    page = _SwaggerUIProvider().render(request())
    initializer = page.assets["swagger-initializer.js"].body.decode()

    assert 'url: "/openapi.json"' in initializer
    assert "validatorUrl: null" in initializer
    assert "persistAuthorization: false" in initializer
    assert "queryConfigEnabled: false" in initializer
    assert "withCredentials: false" in initializer
    assert "supportedSubmitMethods: []" in initializer
    assert "<script>" not in page.html.decode()


def test_try_it_enables_only_the_explicit_submit_method_list() -> None:
    page = _SwaggerUIProvider().render(request(try_it=True))
    initializer = page.assets["swagger-initializer.js"].body.decode()

    assert (
        'supportedSubmitMethods: ["get","put","post","delete","options","head",'
        '"patch","trace","query"]'
    ) in initializer
    assert "validatorUrl: null" in initializer
    assert "persistAuthorization: false" in initializer


def test_inline_filtered_document_needs_no_schema_route() -> None:
    document = b'{"openapi":"3.2.0","info":{"title":"Filtered","version":"1"},"paths":{}}'
    page = _SwaggerUIProvider().render(request(document_url=None, document=document))
    initializer = page.assets["swagger-initializer.js"].body.decode()

    assert 'spec: JSON.parse("{\\"openapi\\":\\"3.2.0\\"' in initializer
    assert "url:" not in initializer


@pytest.mark.parametrize("document", [b"not json", b"[]", b'"value"', b"\xff"])
def test_malformed_inline_document_is_refused(document: bytes) -> None:
    with pytest.raises(_DocumentationDefinitionError, match="inline OpenAPI document"):
        _SwaggerUIProvider().render(request(document_url=None, document=document))


def test_untrusted_title_is_html_escaped_and_never_enters_javascript() -> None:
    title = '</title><script src="//evil.test/x.js"></script>'
    page = _SwaggerUIProvider().render(request(title=title))
    rendered = page.html.decode()
    initializer = page.assets["swagger-initializer.js"].body.decode()

    assert title not in rendered
    assert "&lt;/title&gt;&lt;script" in rendered
    assert title not in initializer


def test_cdn_provider_uses_exact_urls_sri_and_a_local_initializer() -> None:
    provider = _SwaggerUIProvider(cdn=True)
    registry = _DocumentationRegistry()
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable, match="has not permitted"):
        registry.render(provider.name, request())

    page = registry.render(
        provider.name,
        request(),
        allowed_remote_origins=frozenset({"https://unpkg.com"}),
    )
    rendered = page.html.decode()
    root = f"https://unpkg.com/swagger-ui-dist@{_SWAGGER_UI_VERSION}"

    assert provider.name == "swagger-ui-cdn"
    assert page.csp.external_origins == ("https://unpkg.com",)
    assert {asset.url for asset in page.remote_assets} == {
        "https://unpkg.com/swagger-ui-dist@5.32.14/swagger-ui-bundle.js",
        "https://unpkg.com/swagger-ui-dist@5.32.14/swagger-ui.css",
    }
    assert set(page.assets) == {"swagger-initializer.js"}
    assert f'{root}/swagger-ui.css" integrity="{_ASSET_EVIDENCE["swagger-ui.css"][2]}' in rendered
    assert (
        f'{root}/swagger-ui-bundle.js" '
        f'integrity="{_ASSET_EVIDENCE["swagger-ui-bundle.js"][2]}' in rendered
    )
    assert "@latest" not in rendered
    assert 'src="/docs/assets/swagger-initializer.js"' in rendered


def test_vendored_manifest_license_and_bytes_match_runtime_evidence() -> None:
    root = files("agnara_http").joinpath("_vendor", "swagger_ui", _SWAGGER_UI_VERSION)
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))

    assert manifest["version"] == _SWAGGER_UI_VERSION
    assert manifest["license"] == "Apache-2.0"
    assert "Apache License" in root.joinpath("LICENSE").read_text(encoding="utf-8")
    assert root.joinpath("NOTICE").read_text(encoding="utf-8").startswith("swagger-ui")
    for name, (size, sha256, sri) in _ASSET_EVIDENCE.items():
        body = root.joinpath(name).read_bytes()
        assert len(body) == size == manifest["assets"][name]["bytes"]
        assert hashlib.sha256(body).hexdigest() == sha256 == manifest["assets"][name]["sha256"]
        assert sri == manifest["assets"][name]["sri"]


def test_openapi_32_compatibility_claim_names_every_upstream_deferred_feature() -> None:
    provider = _SwaggerUIProvider()

    assert provider.supported_openapi == ("3.2.0",)
    assert provider.unsupported_features == _UNSUPPORTED_OPENAPI_32_FEATURES
    assert provider.unsupported_features == (
        "$self base URI resolution",
        "additionalOperations custom HTTP methods",
        "Components Object mediaTypes",
        "Components Object pathItems",
        "Tag Object summary, kind and parent",
        "querystring parameter location",
        "itemSchema for streaming responses",
    )


def test_cdn_mode_must_be_a_real_boolean() -> None:
    with pytest.raises(_DocumentationDefinitionError, match="cdn mode must be a boolean"):
        _SwaggerUIProvider(cdn="yes")  # ty: ignore[invalid-argument-type]

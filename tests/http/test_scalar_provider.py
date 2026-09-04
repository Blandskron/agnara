"""Scalar provider pinning, compatibility and security evidence (E6.17)."""

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
from agnara_http._scalar import (
    _ASSET_EVIDENCE,
    _SCALAR_VERSION,
    _UNSUPPORTED_FEATURES,
    _ScalarProvider,
)


def request(**overrides: Any) -> _DocumentationRequest:
    fields: dict[str, Any] = {
        "document_url": "/openapi.json",
        "title": "Agnara API",
        "assets_url": "/scalar/assets",
        "openapi_version": "3.2.0",
    }
    fields.update(overrides)
    return _DocumentationRequest(**fields)


def test_local_provider_serves_the_verified_self_contained_bundle() -> None:
    provider = _ScalarProvider()
    registry = _DocumentationRegistry()
    registry.register(provider)

    page = registry.render(provider.name, request())
    rendered = page.html.decode()

    assert provider.name == "scalar"
    assert page.csp.external_origins == ()
    assert page.remote_assets == ()
    assert page.csp.inline_script is False
    assert page.csp.inline_style is True
    assert page.csp.blob_worker is False
    assert set(page.assets) == {*_ASSET_EVIDENCE, "scalar-initializer.js"}
    assert 'src="/scalar/assets/standalone.js"' in rendered
    assert 'src="/scalar/assets/scalar-initializer.js"' in rendered
    assert "cdn.jsdelivr.net" not in rendered
    assert "integrity=" not in rendered


def test_local_provider_handles_an_asset_root_at_the_origin_root() -> None:
    page = _ScalarProvider().render(request(assets_url="/"))
    rendered = page.html.decode()
    assert 'src="/standalone.js"' in rendered
    assert 'src="/scalar-initializer.js"' in rendered


def test_security_defaults_are_explicit_in_a_non_inline_initializer() -> None:
    page = _ScalarProvider().render(request())
    initializer = page.assets["scalar-initializer.js"].body.decode()

    assert 'url: "/openapi.json"' in initializer
    assert "telemetry: false" in initializer
    assert "persistAuth: false" in initializer
    assert "hideClientButton: true" in initializer
    assert "hideTestRequestButton: true" in initializer
    assert 'documentDownloadType: "none"' in initializer
    assert 'showDeveloperTools: "never"' in initializer
    assert "isEditable: false" in initializer
    assert "agent: { disabled: true }" in initializer
    assert "mcp: { disabled: true }" in initializer
    assert "pluginUrls: []" in initializer
    assert "proxyUrl" not in initializer
    assert "authentication" not in initializer
    assert "<script>" not in page.html.decode()


def test_try_it_exposes_the_client_only_when_explicitly_selected() -> None:
    page = _ScalarProvider().render(request(try_it=True))
    initializer = page.assets["scalar-initializer.js"].body.decode()

    assert "hideClientButton: false" in initializer
    assert "hideTestRequestButton: false" in initializer
    assert "persistAuth: false" in initializer
    assert "telemetry: false" in initializer


def test_inline_filtered_document_needs_no_schema_route() -> None:
    document = b'{"openapi":"3.2.0","info":{"title":"Filtered","version":"1"},"paths":{}}'
    page = _ScalarProvider().render(request(document_url=None, document=document))
    initializer = page.assets["scalar-initializer.js"].body.decode()

    assert 'content: JSON.parse("{\\"openapi\\":\\"3.2.0\\"' in initializer
    assert "url:" not in initializer


@pytest.mark.parametrize("document", [b"not json", b"[]", b'"value"', b"\xff"])
def test_malformed_inline_document_is_refused(document: bytes) -> None:
    with pytest.raises(_DocumentationDefinitionError, match="inline OpenAPI document"):
        _ScalarProvider().render(request(document_url=None, document=document))


def test_untrusted_title_is_html_escaped_and_never_enters_javascript() -> None:
    title = '</title><script src="//evil.test/x.js"></script>'
    page = _ScalarProvider().render(request(title=title))
    rendered = page.html.decode()
    initializer = page.assets["scalar-initializer.js"].body.decode()

    assert title not in rendered
    assert "&lt;/title&gt;&lt;script" in rendered
    assert title not in initializer


def test_cdn_provider_uses_exact_entrypoint_sri_and_local_initializer() -> None:
    provider = _ScalarProvider(cdn=True)
    registry = _DocumentationRegistry()
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable, match="has not permitted"):
        registry.render(provider.name, request())

    page = registry.render(
        provider.name,
        request(),
        allowed_remote_origins=frozenset({"https://cdn.jsdelivr.net"}),
    )
    rendered = page.html.decode()
    root = f"https://cdn.jsdelivr.net/npm/@scalar/api-reference@{_SCALAR_VERSION}/dist/browser"

    assert provider.name == "scalar-cdn"
    assert page.csp.external_origins == ("https://cdn.jsdelivr.net",)
    assert tuple(asset.url for asset in page.remote_assets) == (
        "https://cdn.jsdelivr.net/npm/@scalar/api-reference@1.67.0/dist/browser/standalone.js",
    )
    assert set(page.assets) == {"scalar-initializer.js"}
    assert f'{root}/standalone.js" integrity="{_ASSET_EVIDENCE["standalone.js"][2]}' in rendered
    assert "@latest" not in rendered
    assert 'src="/scalar/assets/scalar-initializer.js"' in rendered


def test_vendored_manifest_license_and_bytes_match_runtime_evidence() -> None:
    root = files("agnara_http").joinpath("_vendor", "scalar", _SCALAR_VERSION)
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))

    assert manifest["version"] == _SCALAR_VERSION
    assert manifest["license"] == "MIT"
    assert manifest["acquisition"]["install_scripts_executed"] is False
    assert manifest["acquisition"]["declared_dependencies_not_installed"] == 25
    assert manifest["runtime"]["standalone_bundle_is_self_contained"] is True
    assert root.joinpath("LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    for name, (size, sha256, sri) in _ASSET_EVIDENCE.items():
        body = root.joinpath(*name.split("/")).read_bytes()
        assert len(body) == size == manifest["assets"][name]["bytes"]
        assert hashlib.sha256(body).hexdigest() == sha256 == manifest["assets"][name]["sha256"]
        assert sri == manifest["assets"][name]["sri"]


def test_bundle_evidence_matches_declared_network_and_responsive_boundaries() -> None:
    root = files("agnara_http").joinpath("_vendor", "scalar", _SCALAR_VERSION)
    bundle = root.joinpath("standalone.js").read_bytes()
    page = _ScalarProvider().render(request())

    assert b"fonts.scalar.com" in bundle
    assert b"fonts.googleapis.com" not in bundle
    assert b"telemetry" in bundle
    assert b"@media" in bundle
    assert b"aria-label" in bundle
    # The remote font origin is deliberately absent, so the eventual CSP
    # blocks it and the CSS font stack falls back to local system fonts.
    assert page.csp.external_origins == ()


def test_standalone_bundle_needs_no_chunks_and_dynamic_plugins_are_disabled() -> None:
    root = files("agnara_http").joinpath("_vendor", "scalar", _SCALAR_VERSION)
    bundle = root.joinpath("standalone.js").read_text(encoding="utf-8")

    assert "chunks/" not in bundle
    assert "AgentScalarChatInterface" in bundle
    assert (
        "agent: { disabled: true }"
        in _ScalarProvider().render(request()).assets["scalar-initializer.js"].body.decode()
    )
    assert set(_ASSET_EVIDENCE) == {"standalone.js"}


def test_compatibility_claim_is_partial_and_names_unverified_boundaries() -> None:
    provider = _ScalarProvider()

    assert provider.supported_openapi == ("3.2.0",)
    assert provider.unsupported_features == _UNSUPPORTED_FEATURES
    assert provider.unsupported_features == (
        "complete end-to-end OpenAPI 3.2 conformance",
        "OpenAPI 3.2 workspace-store schema selection",
        "complete WCAG conformance (browser validation deferred to E6.18)",
    )


def test_unclaimed_openapi_version_is_refused_instead_of_relabelled() -> None:
    registry = _DocumentationRegistry()
    provider = _ScalarProvider()
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable, match=r"does not support OpenAPI 3\.1\.0"):
        registry.render(provider.name, request(openapi_version="3.1.0"))


def test_cdn_mode_must_be_a_real_boolean() -> None:
    with pytest.raises(_DocumentationDefinitionError, match="cdn mode must be a boolean"):
        _ScalarProvider(cdn="yes")  # ty: ignore[invalid-argument-type]

"""ReDoc provider pinning, compatibility and security evidence (E6.16)."""

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
from agnara_http._redoc import (
    _ASSET_EVIDENCE,
    _REDOC_VERSION,
    _UNSUPPORTED_FEATURES,
    _ReDocProvider,
)


def request(**overrides: Any) -> _DocumentationRequest:
    fields: dict[str, Any] = {
        "document_url": "/openapi.json",
        "title": "Agnara Reference",
        "assets_url": "/redoc/assets",
        "openapi_version": "3.1.0",
    }
    fields.update(overrides)
    return _DocumentationRequest(**fields)


def test_local_provider_serves_verified_same_origin_assets() -> None:
    provider = _ReDocProvider()
    registry = _DocumentationRegistry()
    registry.register(provider)

    page = registry.render(provider.name, request())
    rendered = page.html.decode()

    assert provider.name == "redoc"
    assert page.csp.external_origins == ()
    assert page.remote_assets == ()
    assert page.csp.inline_script is False
    assert page.csp.inline_style is True
    assert page.csp.blob_worker is True
    assert set(page.assets) == {"redoc.standalone.js", "redoc-initializer.js"}
    assert 'src="/redoc/assets/redoc.standalone.js"' in rendered
    assert 'src="/redoc/assets/redoc-initializer.js"' in rendered
    assert "cdn.redoc.ly" not in rendered
    assert "integrity=" not in rendered


def test_local_provider_handles_an_asset_root_at_the_origin_root() -> None:
    page = _ReDocProvider().render(request(assets_url="/"))
    rendered = page.html.decode()
    assert 'src="/redoc.standalone.js"' in rendered
    assert 'src="/redoc-initializer.js"' in rendered


def test_initializer_treats_the_spec_as_untrusted_and_keeps_download_separate() -> None:
    page = _ReDocProvider().render(request())
    initializer = page.assets["redoc-initializer.js"].body.decode()

    assert 'Redoc.init(\n  "/openapi.json"' in initializer
    assert "untrustedSpec: true" in initializer
    assert "hideDownloadButtons: true" in initializer
    assert "<script>" not in page.html.decode()


def test_inline_filtered_document_needs_no_schema_route() -> None:
    document = b'{"openapi":"3.1.0","info":{"title":"Filtered","version":"1"},"paths":{}}'
    page = _ReDocProvider().render(request(document_url=None, document=document))
    initializer = page.assets["redoc-initializer.js"].body.decode()

    assert 'JSON.parse("{\\"openapi\\":\\"3.1.0\\"' in initializer
    assert '"/openapi.json"' not in initializer


@pytest.mark.parametrize("document", [b"not json", b"[]", b'"value"', b"\xff"])
def test_malformed_inline_document_is_refused(document: bytes) -> None:
    with pytest.raises(_DocumentationDefinitionError, match="inline OpenAPI document"):
        _ReDocProvider().render(request(document_url=None, document=document))


def test_untrusted_title_is_html_escaped_and_never_enters_javascript() -> None:
    title = '</title><script src="//evil.test/x.js"></script>'
    page = _ReDocProvider().render(request(title=title))
    rendered = page.html.decode()
    initializer = page.assets["redoc-initializer.js"].body.decode()

    assert title not in rendered
    assert "&lt;/title&gt;&lt;script" in rendered
    assert title not in initializer


def test_try_it_is_refused_because_community_edition_has_no_console() -> None:
    registry = _DocumentationRegistry()
    provider = _ReDocProvider()
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable, match=r"does not provide.*try-it"):
        registry.render(provider.name, request(try_it=True))


def test_openapi_32_is_unavailable_instead_of_silently_downgraded() -> None:
    registry = _DocumentationRegistry()
    provider = _ReDocProvider()
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable, match=r"does not support OpenAPI 3\.2\.0"):
        registry.render(provider.name, request(openapi_version="3.2.0"))


def test_compatibility_claim_is_exact_and_names_provider_gaps() -> None:
    provider = _ReDocProvider()
    assert provider.supported_openapi == ("3.1.0",)
    assert provider.unsupported_features == _UNSUPPORTED_FEATURES
    assert provider.unsupported_features == (
        "OpenAPI 3.2 documents",
        "interactive try-it console",
    )


def test_cdn_provider_uses_exact_url_sri_and_a_local_initializer() -> None:
    provider = _ReDocProvider(cdn=True)
    registry = _DocumentationRegistry()
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable, match="has not permitted"):
        registry.render(provider.name, request())

    page = registry.render(
        provider.name,
        request(),
        allowed_remote_origins=frozenset({"https://cdn.redoc.ly"}),
    )
    rendered = page.html.decode()
    expected_url = f"https://cdn.redoc.ly/redoc/v{_REDOC_VERSION}/bundles/redoc.standalone.js"
    expected_sri = _ASSET_EVIDENCE["redoc.standalone.js"][2]

    assert provider.name == "redoc-cdn"
    assert page.csp.external_origins == ("https://cdn.redoc.ly",)
    assert tuple(asset.url for asset in page.remote_assets) == (
        "https://cdn.redoc.ly/redoc/v2.5.3/bundles/redoc.standalone.js",
    )
    assert page.csp.blob_worker is True
    assert set(page.assets) == {"redoc-initializer.js"}
    assert f'{expected_url}" integrity="{expected_sri}' in rendered
    assert "/latest/" not in rendered
    assert 'src="/redoc/assets/redoc-initializer.js"' in rendered


def test_vendored_manifest_license_and_bytes_match_runtime_evidence() -> None:
    root = files("agnara_http").joinpath("_vendor", "redoc", _REDOC_VERSION)
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))

    assert manifest["version"] == _REDOC_VERSION
    assert manifest["license"] == "MIT"
    assert "The MIT License" in root.joinpath("LICENSE").read_text(encoding="utf-8")
    for name, (size, sha256, sri) in _ASSET_EVIDENCE.items():
        body = root.joinpath(name).read_bytes()
        assert len(body) == size == manifest["assets"][name]["bytes"]
        assert hashlib.sha256(body).hexdigest() == sha256 == manifest["assets"][name]["sha256"]
        assert sri == manifest["assets"][name]["sri"]


def test_bundle_evidence_matches_the_declared_local_csp_requirements() -> None:
    root = files("agnara_http").joinpath("_vendor", "redoc", _REDOC_VERSION)
    body = root.joinpath("redoc.standalone.js").read_bytes()
    page = _ReDocProvider().render(request())

    assert b"new Worker" in body
    assert b"URL.createObjectURL" in body
    assert b"fonts.googleapis.com" not in body
    assert b"fonts.gstatic.com" not in body
    # The upstream footer tries its own remote logo and falls back to text on
    # error. Local mode deliberately does not authorize that origin, so the
    # eventual CSP blocks the image before it becomes a network dependency.
    assert b"https://cdn.redoc.ly/redoc/logo-mini.svg" in body
    assert page.csp.external_origins == ()
    assert page.csp.blob_worker is True


def test_cdn_mode_must_be_a_real_boolean() -> None:
    with pytest.raises(_DocumentationDefinitionError, match="cdn mode must be a boolean"):
        _ReDocProvider(cdn="yes")  # ty: ignore[invalid-argument-type]

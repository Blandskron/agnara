"""Pinned Scalar API Reference documentation providers."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from types import MappingProxyType

from agnara_http._documentation import (
    _Asset,
    _ContentSecurityPolicy,
    _DocumentationDefinitionError,
    _DocumentationPage,
    _DocumentationRequest,
    _RemoteAsset,
)

_SCALAR_VERSION = "1.67.0"
_SCALAR_ORIGIN = "https://cdn.jsdelivr.net"
_SCALAR_ROOT = f"{_SCALAR_ORIGIN}/npm/@scalar/api-reference@{_SCALAR_VERSION}/dist/browser"
_BUNDLE_NAME = "standalone.js"
_INITIALIZER_NAME = "scalar-initializer.js"

_ASSET_EVIDENCE = MappingProxyType(
    {
        _BUNDLE_NAME: (
            3_736_898,
            "d150e6d9ec333062cb15870704bb9eb6ec6fa99ce3fe5b164a53bc0470e838ee",
            "sha384-6c7Vmx+i0yi8gBbltn0x1cavD+zsMGw2xmXXVyacPJLIGBxwaVimW5TW0WiW17Ir",
        ),
    }
)

_UNSUPPORTED_FEATURES = (
    "complete end-to-end OpenAPI 3.2 conformance",
    "OpenAPI 3.2 workspace-store schema selection",
    "complete WCAG conformance (browser validation deferred to E6.18)",
)


@dataclass(frozen=True, slots=True)
class _ScalarProvider:
    """Render Scalar from pinned local assets or an exact-version CDN."""

    supported_openapi = ("3.2.0",)
    unsupported_features = _UNSUPPORTED_FEATURES

    cdn: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.cdn, bool):
            raise _DocumentationDefinitionError("Scalar cdn mode must be a boolean")

    @property
    def name(self) -> str:
        return "scalar-cdn" if self.cdn else "scalar"

    def render(self, request: _DocumentationRequest) -> _DocumentationPage:
        initializer_asset = _Asset("text/javascript; charset=utf-8", _initializer(request))
        initializer_url = _join_url(request.assets_url, _INITIALIZER_NAME)

        if self.cdn:
            bundle_url = f"{_SCALAR_ROOT}/{_BUNDLE_NAME}"
            assets: Mapping[str, _Asset] = {_INITIALIZER_NAME: initializer_asset}
            csp = _ContentSecurityPolicy(
                inline_style=True,
                external_origins=(_SCALAR_ORIGIN,),
            )
            remote_assets = (
                _RemoteAsset(
                    url=bundle_url,
                    version=_SCALAR_VERSION,
                    integrity=_ASSET_EVIDENCE[_BUNDLE_NAME][2],
                ),
            )
            integrity = True
        else:
            bundle_url = _join_url(request.assets_url, _BUNDLE_NAME)
            assets = {**_bundled_assets(), _INITIALIZER_NAME: initializer_asset}
            csp = _ContentSecurityPolicy(inline_style=True)
            remote_assets = ()
            integrity = False

        return _DocumentationPage(
            html=_html(
                title=request.title,
                bundle_url=bundle_url,
                initializer_url=initializer_url,
                integrity=integrity,
            ),
            csp=csp,
            assets=assets,
            remote_assets=remote_assets,
        )


@cache
def _bundled_assets() -> Mapping[str, _Asset]:
    """Load and verify the self-contained interactive browser bundle."""
    root = files("agnara_http").joinpath("_vendor", "scalar", _SCALAR_VERSION)
    loaded: dict[str, _Asset] = {}
    for name, (expected_size, expected_sha256, _) in _ASSET_EVIDENCE.items():
        body = root.joinpath(*name.split("/")).read_bytes()
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if len(body) != expected_size or actual_sha256 != expected_sha256:
            raise _DocumentationDefinitionError(
                f"vendored Scalar asset {name!r} failed its pinned integrity check"
            )
        loaded[name] = _Asset("text/javascript; charset=utf-8", body)
    return MappingProxyType(loaded)


def _initializer(request: _DocumentationRequest) -> bytes:
    if request.document_url is not None:
        source = f"url: {json.dumps(request.document_url)},"
    else:
        document_json = _document_json(request.document)
        source = f"content: JSON.parse({json.dumps(document_json)}),"

    hidden = json.dumps(not request.try_it)
    script = f""""use strict";
Scalar.createApiReference("#scalar-api-reference", {{
  {source}
  telemetry: false,
  persistAuth: false,
  hideClientButton: {hidden},
  hideTestRequestButton: {hidden},
  documentDownloadType: "none",
  showDeveloperTools: "never",
  isEditable: false,
  agent: {{ disabled: true }},
  mcp: {{ disabled: true }},
  pluginUrls: []
}});
"""
    return script.encode("utf-8")


def _document_json(document: bytes | None) -> str:
    if document is None:  # The request contract makes this unreachable.
        raise _DocumentationDefinitionError("Scalar needs one OpenAPI document source")
    try:
        parsed = json.loads(document.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _DocumentationDefinitionError(
            "inline OpenAPI document must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise _DocumentationDefinitionError("inline OpenAPI document must be a JSON object")
    return json.dumps(parsed, ensure_ascii=True, separators=(",", ":"))


def _join_url(base: str, name: str) -> str:
    return f"/{name}" if base == "/" else f"{base.rstrip('/')}/{name}"


def _html(*, title: str, bundle_url: str, initializer_url: str, integrity: bool) -> bytes:
    escaped_title = html.escape(title, quote=True)
    escaped_bundle = html.escape(bundle_url, quote=True)
    escaped_initializer = html.escape(initializer_url, quote=True)
    if integrity:
        sri = html.escape(_ASSET_EVIDENCE[_BUNDLE_NAME][2], quote=True)
        bundle_attributes = f' integrity="{sri}" crossorigin="anonymous"'
    else:
        bundle_attributes = ""

    page = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
</head>
<body>
  <div id="scalar-api-reference"></div>
  <script src="{escaped_bundle}"{bundle_attributes}></script>
  <script src="{escaped_initializer}"></script>
</body>
</html>
'''
    return page.encode("utf-8")

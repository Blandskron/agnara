"""Pinned Swagger UI documentation providers.

The local provider is the production baseline.  The CDN provider has a
different name and declares its network requirement so the documentation
registry can enforce the deployment's explicit remote-assets decision.
"""

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
)

_SWAGGER_UI_VERSION = "5.32.14"
_SWAGGER_UI_ORIGIN = "https://unpkg.com"
_SWAGGER_UI_ROOT = f"{_SWAGGER_UI_ORIGIN}/swagger-ui-dist@{_SWAGGER_UI_VERSION}"
_BUNDLE_NAME = "swagger-ui-bundle.js"
_STYLESHEET_NAME = "swagger-ui.css"
_INITIALIZER_NAME = "swagger-initializer.js"

_ASSET_EVIDENCE = MappingProxyType(
    {
        _BUNDLE_NAME: (
            1_553_809,
            "16d93d5cc19e54c98fb0b81157dbb3bd90780aa36b914e128a643b31e54a93f4",
            "sha384-Dt83RhU85ZmX7werw9uTFCzmauXUoSyx3pdzTQMABtsnFmooJy4Vz9/ACh7n5m1A",
        ),
        _STYLESHEET_NAME: (
            185_784,
            "d7f39f764aa18c7b47dd05b9af5613e373e4ac0f3557c2693d52d0abc2464d76",
            "sha384-fgyWYkUAamzuI8mJFu/xpRP0JWCJRwkwUwsYDoOYVHUJ8NQE5cENn8ib3ppwFFSX",
        ),
    }
)

# Swagger UI 5.32.0 added basic OAS 3.2 support.  Its upstream implementation
# explicitly deferred these features; keeping them machine-visible prevents a
# patch-version bump from becoming an accidental compatibility claim.
_UNSUPPORTED_OPENAPI_32_FEATURES = (
    "$self base URI resolution",
    "additionalOperations custom HTTP methods",
    "Components Object mediaTypes",
    "Components Object pathItems",
    "Tag Object summary, kind and parent",
    "querystring parameter location",
    "itemSchema for streaming responses",
)

_SUBMIT_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace", "query")


@dataclass(frozen=True, slots=True)
class _SwaggerUIProvider:
    """Render Swagger UI from pinned local assets or an exact-version CDN."""

    supported_openapi = ("3.2.0",)
    unsupported_features = _UNSUPPORTED_OPENAPI_32_FEATURES

    cdn: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.cdn, bool):
            raise _DocumentationDefinitionError("Swagger UI cdn mode must be a boolean")

    @property
    def name(self) -> str:
        return "swagger-ui-cdn" if self.cdn else "swagger-ui"

    @property
    def remote_assets(self) -> bool:
        return self.cdn

    def render(self, request: _DocumentationRequest) -> _DocumentationPage:
        initializer = _initializer(request)
        initializer_asset = _Asset("text/javascript; charset=utf-8", initializer)
        initializer_url = _join_url(request.assets_url, _INITIALIZER_NAME)

        if self.cdn:
            bundle_url = f"{_SWAGGER_UI_ROOT}/{_BUNDLE_NAME}"
            stylesheet_url = f"{_SWAGGER_UI_ROOT}/{_STYLESHEET_NAME}"
            assets: Mapping[str, _Asset] = {_INITIALIZER_NAME: initializer_asset}
            csp = _ContentSecurityPolicy(
                inline_style=True,
                external_origins=(_SWAGGER_UI_ORIGIN,),
            )
            integrity = True
        else:
            bundle_url = _join_url(request.assets_url, _BUNDLE_NAME)
            stylesheet_url = _join_url(request.assets_url, _STYLESHEET_NAME)
            assets = {**_bundled_assets(), _INITIALIZER_NAME: initializer_asset}
            csp = _ContentSecurityPolicy(inline_style=True)
            integrity = False

        rendered = _html(
            title=request.title,
            bundle_url=bundle_url,
            stylesheet_url=stylesheet_url,
            initializer_url=initializer_url,
            integrity=integrity,
        )
        return _DocumentationPage(html=rendered, csp=csp, assets=assets)


@cache
def _bundled_assets() -> Mapping[str, _Asset]:
    """Load and verify immutable package resources once per interpreter."""
    root = files("agnara_http").joinpath("_vendor", "swagger_ui", _SWAGGER_UI_VERSION)
    loaded: dict[str, _Asset] = {}
    media_types = {
        _BUNDLE_NAME: "text/javascript; charset=utf-8",
        _STYLESHEET_NAME: "text/css; charset=utf-8",
    }
    for name, (expected_size, expected_sha256, _) in _ASSET_EVIDENCE.items():
        body = root.joinpath(name).read_bytes()
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if len(body) != expected_size or actual_sha256 != expected_sha256:
            raise _DocumentationDefinitionError(
                f"vendored Swagger UI asset {name!r} failed its pinned integrity check"
            )
        loaded[name] = _Asset(media_types[name], body)
    return MappingProxyType(loaded)


def _initializer(request: _DocumentationRequest) -> bytes:
    if request.document_url is not None:
        source = f"url: {json.dumps(request.document_url)},"
    else:
        document_json = _document_json(request.document)
        source = f"spec: JSON.parse({json.dumps(document_json)}),"

    methods = _SUBMIT_METHODS if request.try_it else ()
    method_json = json.dumps(methods, separators=(",", ":"))
    script = f""""use strict";
window.ui = SwaggerUIBundle({{
  {source}
  dom_id: "#swagger-ui",
  deepLinking: true,
  queryConfigEnabled: false,
  persistAuthorization: false,
  validatorUrl: null,
  withCredentials: false,
  supportedSubmitMethods: {method_json}
}});
"""
    return script.encode("utf-8")


def _document_json(document: bytes | None) -> str:
    if document is None:  # The request contract makes this unreachable.
        raise _DocumentationDefinitionError("Swagger UI needs one OpenAPI document source")
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


def _html(
    *,
    title: str,
    bundle_url: str,
    stylesheet_url: str,
    initializer_url: str,
    integrity: bool,
) -> bytes:
    escaped_title = html.escape(title, quote=True)
    escaped_bundle = html.escape(bundle_url, quote=True)
    escaped_stylesheet = html.escape(stylesheet_url, quote=True)
    escaped_initializer = html.escape(initializer_url, quote=True)
    if integrity:
        css_sri = html.escape(_ASSET_EVIDENCE[_STYLESHEET_NAME][2], quote=True)
        js_sri = html.escape(_ASSET_EVIDENCE[_BUNDLE_NAME][2], quote=True)
        stylesheet_attributes = f' integrity="{css_sri}" crossorigin="anonymous"'
        bundle_attributes = f' integrity="{js_sri}" crossorigin="anonymous"'
    else:
        stylesheet_attributes = ""
        bundle_attributes = ""

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <link rel="stylesheet" href="{escaped_stylesheet}"{stylesheet_attributes}>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{escaped_bundle}"{bundle_attributes}></script>
  <script src="{escaped_initializer}"></script>
</body>
</html>
"""
    return page.encode("utf-8")

"""Pinned ReDoc Community Edition documentation providers."""

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
    _DocumentationUnavailable,
    _RemoteAsset,
)

_REDOC_VERSION = "2.5.3"
_REDOC_ORIGIN = "https://cdn.redoc.ly"
_REDOC_ROOT = f"{_REDOC_ORIGIN}/redoc/v{_REDOC_VERSION}/bundles"
_BUNDLE_NAME = "redoc.standalone.js"
_INITIALIZER_NAME = "redoc-initializer.js"

_ASSET_EVIDENCE = MappingProxyType(
    {
        _BUNDLE_NAME: (
            1_097_271,
            "1320f442151c57c447d3b70c7ffc6c4f86d08464020fe34c8cc5d3164e9944f0",
            "sha384-xiEssMQFSpSfLbzRZCGfxxIM5QDb2DTrU6vyoZdp2sV1L6pmOMy6MpTtUoLbpC96",
        )
    }
)

_UNSUPPORTED_FEATURES = (
    "OpenAPI 3.2 documents",
    "interactive try-it console",
)


@dataclass(frozen=True, slots=True)
class _ReDocProvider:
    """Render the read-only ReDoc CE interface from local or remote assets."""

    supported_openapi = ("3.1.0",)
    unsupported_features = _UNSUPPORTED_FEATURES

    cdn: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.cdn, bool):
            raise _DocumentationDefinitionError("ReDoc cdn mode must be a boolean")

    @property
    def name(self) -> str:
        return "redoc-cdn" if self.cdn else "redoc"

    def render(self, request: _DocumentationRequest) -> _DocumentationPage:
        if request.try_it:
            raise _DocumentationUnavailable(
                "ReDoc Community Edition does not provide an interactive try-it console"
            )

        initializer_asset = _Asset(
            "text/javascript; charset=utf-8",
            _initializer(request),
        )
        initializer_url = _join_url(request.assets_url, _INITIALIZER_NAME)
        if self.cdn:
            bundle_url = f"{_REDOC_ROOT}/{_BUNDLE_NAME}"
            assets: Mapping[str, _Asset] = {_INITIALIZER_NAME: initializer_asset}
            csp = _ContentSecurityPolicy(
                inline_style=True,
                blob_worker=True,
                external_origins=(_REDOC_ORIGIN,),
            )
            remote_assets = (
                _RemoteAsset(
                    url=bundle_url,
                    version=_REDOC_VERSION,
                    integrity=_ASSET_EVIDENCE[_BUNDLE_NAME][2],
                ),
            )
            integrity = True
        else:
            bundle_url = _join_url(request.assets_url, _BUNDLE_NAME)
            assets = {**_bundled_assets(), _INITIALIZER_NAME: initializer_asset}
            csp = _ContentSecurityPolicy(inline_style=True, blob_worker=True)
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
    """Load and verify the immutable ReDoc package resource once."""
    root = files("agnara_http").joinpath("_vendor", "redoc", _REDOC_VERSION)
    loaded: dict[str, _Asset] = {}
    for name, (expected_size, expected_sha256, _) in _ASSET_EVIDENCE.items():
        body = root.joinpath(name).read_bytes()
        actual_sha256 = hashlib.sha256(body).hexdigest()
        if len(body) != expected_size or actual_sha256 != expected_sha256:
            raise _DocumentationDefinitionError(
                f"vendored ReDoc asset {name!r} failed its pinned integrity check"
            )
        loaded[name] = _Asset("text/javascript; charset=utf-8", body)
    return MappingProxyType(loaded)


def _initializer(request: _DocumentationRequest) -> bytes:
    if request.document_url is not None:
        source = json.dumps(request.document_url)
    else:
        document_json = _document_json(request.document)
        source = f"JSON.parse({json.dumps(document_json)})"

    script = f""""use strict";
Redoc.init(
  {source},
  {{
    untrustedSpec: true,
    hideDownloadButtons: true
  }},
  document.getElementById("redoc-container")
);
"""
    return script.encode("utf-8")


def _document_json(document: bytes | None) -> str:
    if document is None:  # The request contract makes this unreachable.
        raise _DocumentationDefinitionError("ReDoc needs one OpenAPI document source")
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

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
</head>
<body>
  <div id="redoc-container"></div>
  <script src="{escaped_bundle}"{bundle_attributes}></script>
  <script src="{escaped_initializer}"></script>
</body>
</html>
"""
    return page.encode("utf-8")

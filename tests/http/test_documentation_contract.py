"""The replaceable documentation-provider contract (E6.12)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from agnara_http._documentation import (
    _Asset,
    _ContentSecurityPolicy,
    _DocumentationDefinitionError,
    _DocumentationPage,
    _DocumentationProvider,
    _DocumentationRegistry,
    _DocumentationRequest,
    _DocumentationUnavailable,
    _validate_provider,
)

OPENAPI = "3.2.0"


def request(**overrides: Any) -> _DocumentationRequest:
    fields: dict[str, Any] = {
        "document_url": "/openapi.json",
        "title": "Reference",
        "assets_url": "/docs/assets",
        "openapi_version": OPENAPI,
    }
    fields.update(overrides)
    return _DocumentationRequest(**fields)


class Provider:
    """A minimal conforming provider, with every declaration a real one needs."""

    def __init__(
        self,
        name: str = "example",
        *,
        supported_openapi: tuple[str, ...] = (OPENAPI,),
        unsupported_features: tuple[str, ...] = (),
        remote_assets: bool = False,
        page: _DocumentationPage | None = None,
        returns: Any = None,
    ) -> None:
        self.name = name
        self.supported_openapi = supported_openapi
        self.unsupported_features = unsupported_features
        self.remote_assets = remote_assets
        self.seen: list[_DocumentationRequest] = []
        self._page = page
        self._returns = returns

    def render(self, request: _DocumentationRequest) -> _DocumentationPage:
        self.seen.append(request)
        if self._returns is not None:
            return self._returns
        return self._page or _DocumentationPage(html=b"<!doctype html><title>x</title>")


# --- what a provider is given ----------------------------------------------


def test_a_provider_is_given_the_document_and_nothing_that_could_reveal_more() -> None:
    # The whole point of the boundary: a provider renders what the projection
    # already decided to publish. A future field that carried the registry, an
    # exposure or a plan would make an unpublished capability reachable, so the
    # field set itself is the assertion.
    names = {field.name for field in dataclasses.fields(_DocumentationRequest)}

    assert names == {
        "document_url",
        "title",
        "assets_url",
        "openapi_version",
        "document",
        "try_it",
    }
    forbidden = ("routes", "registry", "exposure", "exposures", "plan", "capability", "container")
    for term in forbidden:
        assert not any(term in name for name in names), f"{term!r} must not reach a provider"


def test_try_it_is_off_unless_it_is_asked_for() -> None:
    assert request().try_it is False
    assert request(try_it=True).try_it is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"document_url": "https://cdn.example/openapi.json"}, "same-origin absolute path"),
        ({"document_url": "openapi.json"}, "same-origin absolute path"),
        ({"assets_url": "//evil.test/assets"}, "same-origin absolute path"),
        ({"title": "  "}, "title must be a non-empty string"),
        ({"openapi_version": ""}, "openapi_version must be a non-empty string"),
        ({"document": "not bytes"}, "document must be the serialized bytes"),
        ({"try_it": "yes"}, "try_it must be a boolean"),
    ],
)
def test_an_unusable_request_is_refused(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(_DocumentationDefinitionError, match=message):
        request(**overrides)


@pytest.mark.parametrize("url", ["//cdn.example/openapi.json", "//evil.test/assets"])
def test_a_protocol_relative_url_is_not_a_same_origin_path(url: str) -> None:
    # `//host/path` is a network reference wearing a local path's clothes. It
    # starts with a slash, so a naive same-origin check accepts it and the
    # deployment quietly gains an external dependency.
    with pytest.raises(_DocumentationDefinitionError, match="same-origin absolute path"):
        request(document_url=url)
    with pytest.raises(_DocumentationDefinitionError, match="same-origin absolute path"):
        request(assets_url=url)


@pytest.mark.parametrize(
    "path", ["../escape.js", "ui/../../escape.js", "..", ".", "ui/./app.js", "ui/../app.js"]
)
def test_an_asset_path_cannot_traverse_out_of_its_root(path: str) -> None:
    # A provider names the files it needs served; a traversal segment would
    # let it name a file outside the asset root it was given.
    with pytest.raises(_DocumentationDefinitionError, match="invalid asset path"):
        _DocumentationPage(html=b"<x>", assets={path: _Asset("text/javascript", b"")})


def test_ordinary_dotted_asset_names_still_work() -> None:
    page = _DocumentationPage(
        html=b"<x>",
        assets={
            "swagger-ui.min.css": _Asset("text/css", b""),
            "ui/app.bundle.js": _Asset("text/javascript", b""),
            "fonts/inter-v13.woff2": _Asset("font/woff2", b""),
        },
    )
    assert len(page.assets) == 3


def test_a_provider_may_receive_the_serialized_document_directly() -> None:
    provider = Provider()
    registry = _DocumentationRegistry()
    registry.register(provider)

    registry.render("example", request(document=b'{"openapi":"3.2.0"}'))
    assert provider.seen[0].document == b'{"openapi":"3.2.0"}'


# --- what a provider must declare ------------------------------------------


def test_a_conforming_provider_validates() -> None:
    assert _validate_provider(Provider()) is not None
    assert isinstance(Provider(), _DocumentationProvider)


def test_a_provider_that_claims_compatibility_by_silence_is_refused() -> None:
    # An untested compatibility claim is the one ADR 0018 refuses to accept.
    with pytest.raises(_DocumentationDefinitionError, match="must name the OpenAPI versions"):
        _validate_provider(Provider(supported_openapi=()))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "Example"}, "invalid provider name"),
        ({"name": "9lives"}, "invalid provider name"),
        ({"name": ""}, "invalid provider name"),
        ({"supported_openapi": ("",)}, "declares an empty OpenAPI version"),
        ({"supported_openapi": [OPENAPI]}, "must name the OpenAPI versions"),
        ({"unsupported_features": ("",)}, "must declare its unsupported features"),
        ({"unsupported_features": "webhooks"}, "must declare its unsupported features"),
        ({"remote_assets": "yes"}, "remote_assets must be a boolean"),
    ],
)
def test_a_malformed_declaration_is_refused(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(_DocumentationDefinitionError, match=message):
        _validate_provider(Provider(**kwargs))


def test_an_object_that_is_not_a_provider_is_refused() -> None:
    with pytest.raises(_DocumentationDefinitionError, match="does not implement"):
        _validate_provider(object())


def test_declaring_no_unsupported_features_is_allowed_but_must_be_explicit() -> None:
    # An empty tuple is a claim; a missing attribute is not.
    assert _validate_provider(Provider(unsupported_features=())).unsupported_features == ()


# --- compatibility ---------------------------------------------------------


def test_an_unsupported_document_version_makes_the_provider_unavailable() -> None:
    registry = _DocumentationRegistry()
    provider = Provider(supported_openapi=("3.1.0",))
    registry.register(provider)

    with pytest.raises(_DocumentationUnavailable) as raised:
        registry.render("example", request())

    assert "does not support OpenAPI 3.2.0" in str(raised.value)
    assert "3.1.0" in str(raised.value)
    assert provider.seen == [], "an incompatible provider must not be asked to render"


def test_a_supported_version_renders() -> None:
    registry = _DocumentationRegistry()
    registry.register(Provider(supported_openapi=("3.1.0", OPENAPI)))

    page = registry.render("example", request())
    assert page.html.startswith(b"<!doctype html>")


def test_an_unknown_provider_name_is_unavailable_rather_than_a_key_error() -> None:
    with pytest.raises(_DocumentationUnavailable, match="no documentation provider named"):
        _DocumentationRegistry().render("absent", request())


# --- assets and policy -----------------------------------------------------


def test_a_provider_declares_its_assets_rather_than_the_adapter_inferring_them() -> None:
    page = _DocumentationPage(
        html=b"<!doctype html>",
        assets={
            "ui.css": _Asset("text/css", b"body{}"),
            "ui/app.js": _Asset("text/javascript", b""),
        },
    )
    assert set(page.assets) == {"ui.css", "ui/app.js"}
    assert page.assets["ui.css"].media_type == "text/css"


def test_page_assets_are_read_only() -> None:
    page = _DocumentationPage(html=b"<!doctype html>", assets={"ui.css": _Asset("text/css", b"")})
    mutable: Any = page.assets
    with pytest.raises(TypeError):
        mutable["evil.js"] = _Asset("text/javascript", b"")


@pytest.mark.parametrize("path", ["../escape.js", "/absolute.js", "with space.js", ""])
def test_an_unusable_asset_path_is_refused(path: str) -> None:
    with pytest.raises(_DocumentationDefinitionError, match="invalid asset path"):
        _DocumentationPage(html=b"<x>", assets={path: _Asset("text/javascript", b"")})


def test_a_local_policy_requires_no_network() -> None:
    assert _ContentSecurityPolicy().requires_network is False
    assert _ContentSecurityPolicy(inline_style=True).requires_network is False
    assert _ContentSecurityPolicy(external_origins=("https://cdn.test",)).requires_network is True


@pytest.mark.parametrize("origin", ["http://cdn.test", "cdn.test", "//cdn.test"])
def test_an_external_origin_must_be_https(origin: str) -> None:
    with pytest.raises(_DocumentationDefinitionError, match="must be an https URL"):
        _ContentSecurityPolicy(external_origins=(origin,))


def test_a_provider_that_needs_a_cdn_without_declaring_it_is_a_definition_error() -> None:
    registry = _DocumentationRegistry()
    registry.register(
        Provider(
            page=_DocumentationPage(
                html=b"<x>", csp=_ContentSecurityPolicy(external_origins=("https://cdn.test",))
            )
        )
    )

    with pytest.raises(_DocumentationDefinitionError, match="does not declare remote_assets"):
        registry.render("example", request(), allow_remote_assets=True)


def test_a_declared_cdn_still_needs_the_application_to_permit_it() -> None:
    # Pinned local assets are the secure baseline; the network is opt-in twice,
    # once by the provider and once by the deployment.
    registry = _DocumentationRegistry()
    registry.register(
        Provider(
            remote_assets=True,
            page=_DocumentationPage(
                html=b"<x>", csp=_ContentSecurityPolicy(external_origins=("https://cdn.test",))
            ),
        )
    )

    with pytest.raises(_DocumentationUnavailable, match="has not permitted"):
        registry.render("example", request())

    permitted = registry.render("example", request(), allow_remote_assets=True)
    assert permitted.csp.external_origins == ("https://cdn.test",)


def test_a_local_provider_needs_no_permission() -> None:
    registry = _DocumentationRegistry()
    registry.register(Provider())
    assert registry.render("example", request()).csp.requires_network is False


# --- the registry ----------------------------------------------------------


def test_no_provider_is_a_supported_deployment_rather_than_a_broken_one() -> None:
    registry = _DocumentationRegistry()

    assert len(registry) == 0
    assert list(registry) == []
    assert registry.get("example") is None
    assert "example" not in registry


def test_two_providers_cannot_share_a_name() -> None:
    registry = _DocumentationRegistry()
    registry.register(Provider("swagger"))
    registry.register(Provider("redoc"))

    with pytest.raises(_DocumentationDefinitionError, match="already registered"):
        registry.register(Provider("swagger"))
    assert {provider.name for provider in registry} == {"swagger", "redoc"}


def test_registration_validates_before_anything_is_stored() -> None:
    registry = _DocumentationRegistry()
    with pytest.raises(_DocumentationDefinitionError):
        registry.register(Provider(supported_openapi=()))
    assert len(registry) == 0


def test_a_provider_returning_the_wrong_type_is_a_definition_error() -> None:
    registry = _DocumentationRegistry()
    registry.register(Provider(returns="<html>"))

    with pytest.raises(_DocumentationDefinitionError, match="not a _DocumentationPage"):
        registry.render("example", request())


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"html": b""}, "html must be non-empty bytes"),
        ({"html": "<x>"}, "html must be non-empty bytes"),
        ({"html": b"<x>", "csp": object()}, "csp must be a _ContentSecurityPolicy"),
        ({"html": b"<x>", "assets": [("a.js", None)]}, "assets must be a mapping"),
        ({"html": b"<x>", "assets": {"a.js": object()}}, "is not an _Asset"),
    ],
)
def test_a_malformed_page_is_refused(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(_DocumentationDefinitionError, match=message):
        _DocumentationPage(**kwargs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"media_type": "", "body": b""}, "media_type must be a non-empty string"),
        ({"media_type": "text/css", "body": "x"}, "body must be bytes"),
    ],
)
def test_a_malformed_asset_is_refused(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(_DocumentationDefinitionError, match=message):
        _Asset(**kwargs)

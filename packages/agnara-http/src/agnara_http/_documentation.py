"""The replaceable documentation-provider contract.

ADR 0018 and RFC 0003 decided that browser documentation sits behind an
optional, replaceable boundary. This module is that boundary expressed as a
contract, so the guarantees are enforced by construction rather than by
review.

Three of them are negative, and they are the reason this module exists:

- a provider is handed an already-filtered document, never the compiled
  registry, so it cannot reach an exposure the projection deliberately
  withheld;
- a provider that does not support the canonical document version becomes
  unavailable with a diagnostic, because documentation that is wrong is worse
  than documentation that is absent;
- a provider may not require an external origin unless remote assets were
  explicitly permitted, so a production deployment does not silently acquire a
  network dependency.

None of this is authorization. Filtering happens before a provider is reached
(ADR 0018 guardrail 7); this contract governs presentation only.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, runtime_checkable

_PROVIDER_NAME = re.compile(r"[a-z][a-z0-9-]*\Z")

#: One relative asset path segment. `.` and `..` are excluded by the negative
#: lookahead: a traversal segment would let a provider name a file outside the
#: asset root it was given.
_ASSET_SEGMENT = r"(?!\.\.?/)(?!\.\.?\Z)[A-Za-z0-9._-]+"
_ASSET_PATH = re.compile(rf"{_ASSET_SEGMENT}(?:/{_ASSET_SEGMENT})*\Z")

#: A same-origin absolute path. The second character may not be another
#: slash: `//host/path` is a protocol-relative URL, which is a network
#: reference wearing a local path's clothes.
_LOCAL_URL = re.compile(r"/(?!/)[A-Za-z0-9._~!$&'()*+,;=:@%/-]*\Z")


class _DocumentationDefinitionError(ValueError):
    """A provider declaration violates the documentation-provider contract."""


class _DocumentationUnavailable(RuntimeError):
    """A provider cannot render this document, and says so instead of trying."""


@dataclass(frozen=True, slots=True)
class _Asset:
    """One file a provider needs served from this application's own origin."""

    media_type: str
    body: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise _DocumentationDefinitionError("asset media_type must be a non-empty string")
        if not isinstance(self.body, bytes):
            raise _DocumentationDefinitionError("asset body must be bytes")


@dataclass(frozen=True, slots=True)
class _ContentSecurityPolicy:
    """What a page needs, declared by the provider rather than inferred.

    ``external_origins`` is the only way to reach the network, and a provider
    that lists one without ``remote_assets`` permission is refused.
    ``blob_worker`` separately declares a local object-URL worker requirement;
    it is an explicit CSP privilege but not a remote network dependency. RFC
    0003 makes pinned local assets the secure baseline; this is where that
    stops being advice.
    """

    inline_style: bool = False
    inline_script: bool = False
    blob_worker: bool = False
    external_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for flag in ("inline_style", "inline_script", "blob_worker"):
            if not isinstance(getattr(self, flag), bool):
                raise _DocumentationDefinitionError(f"{flag} must be a boolean")
        if not isinstance(self.external_origins, tuple):
            raise _DocumentationDefinitionError("external_origins must be a tuple")
        for origin in self.external_origins:
            if not isinstance(origin, str) or not origin.startswith("https://"):
                raise _DocumentationDefinitionError(
                    f"an external origin must be an https URL, got {origin!r}"
                )

    @property
    def requires_network(self) -> bool:
        return bool(self.external_origins)


@dataclass(frozen=True, slots=True)
class _DocumentationRequest:
    """Everything a provider is given, and deliberately nothing else.

    There is no route registry, no compiled exposure, no execution plan and no
    capability here. A provider renders what the projection already decided to
    publish; it does not get to look further.
    """

    document_url: str | None
    title: str
    assets_url: str
    openapi_version: str
    document: bytes | None = None
    try_it: bool = False

    def __post_init__(self) -> None:
        if self.document_url is not None and (
            not isinstance(self.document_url, str) or not _LOCAL_URL.fullmatch(self.document_url)
        ):
            raise _DocumentationDefinitionError(
                "document_url must be a same-origin absolute path or None, "
                f"got {self.document_url!r}"
            )
        if not isinstance(self.assets_url, str) or not _LOCAL_URL.fullmatch(self.assets_url):
            raise _DocumentationDefinitionError(
                f"assets_url must be a same-origin absolute path, got {self.assets_url!r}"
            )
        if not isinstance(self.title, str) or not self.title.strip():
            raise _DocumentationDefinitionError("title must be a non-empty string")
        if not isinstance(self.openapi_version, str) or not self.openapi_version.strip():
            raise _DocumentationDefinitionError("openapi_version must be a non-empty string")
        if self.document is not None and not isinstance(self.document, bytes):
            raise _DocumentationDefinitionError("document must be the serialized bytes or None")
        if self.document == b"":
            raise _DocumentationDefinitionError("document bytes must not be empty")
        if (self.document_url is None) == (self.document is None):
            raise _DocumentationDefinitionError(
                "exactly one of document_url or document must be supplied"
            )
        if not isinstance(self.try_it, bool):
            raise _DocumentationDefinitionError("try_it must be a boolean")


@dataclass(frozen=True, slots=True)
class _DocumentationPage:
    """One rendered page, its local assets and the policy it requires."""

    html: bytes
    csp: _ContentSecurityPolicy = field(default_factory=_ContentSecurityPolicy)
    assets: Mapping[str, _Asset] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.html, bytes) or not self.html:
            raise _DocumentationDefinitionError("page html must be non-empty bytes")
        if not isinstance(self.csp, _ContentSecurityPolicy):
            raise _DocumentationDefinitionError("page csp must be a _ContentSecurityPolicy")
        if not isinstance(self.assets, Mapping):
            raise _DocumentationDefinitionError("page assets must be a mapping")
        copied: dict[str, _Asset] = {}
        for path, asset in self.assets.items():
            if not isinstance(path, str) or not _ASSET_PATH.fullmatch(path):
                raise _DocumentationDefinitionError(f"invalid asset path: {path!r}")
            if not isinstance(asset, _Asset):
                raise _DocumentationDefinitionError(f"asset {path!r} is not an _Asset")
            copied[path] = asset
        object.__setattr__(self, "assets", MappingProxyType(copied))


def _documentation_security_headers(
    policy: _ContentSecurityPolicy,
) -> tuple[tuple[bytes, bytes], ...]:
    """Serialize one provider declaration into restrictive browser headers.

    The provider describes only the privileges its page needs.  This function
    owns the shared production baseline around those privileges, so browser
    tests and eventual route composition cannot drift into separate policies.
    """
    if not isinstance(policy, _ContentSecurityPolicy):
        raise _DocumentationDefinitionError(
            "documentation security headers require a _ContentSecurityPolicy"
        )

    origins = tuple(sorted(policy.external_origins))
    script_sources = ["'self'", *origins]
    style_sources = ["'self'", *origins]
    if policy.inline_script:
        script_sources.append("'unsafe-inline'")
    if policy.inline_style:
        style_sources.append("'unsafe-inline'")

    worker_sources = ["'self'"]
    if policy.blob_worker:
        worker_sources.append("blob:")

    directives = (
        "default-src 'none'",
        "base-uri 'none'",
        "connect-src 'self'",
        "font-src 'self' data:",
        "frame-ancestors 'none'",
        "img-src 'self' data: blob:",
        "object-src 'none'",
        f"script-src {' '.join(script_sources)}",
        f"style-src {' '.join(style_sources)}",
        f"worker-src {' '.join(worker_sources)}",
    )
    return (
        (b"cache-control", b"no-store"),
        (b"content-security-policy", "; ".join(directives).encode("ascii")),
        (b"referrer-policy", b"no-referrer"),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
    )


@runtime_checkable
class _DocumentationProvider(Protocol):
    """What an optional browser documentation UI must implement.

    ``supported_openapi`` and ``unsupported_features`` are required rather
    than optional: a compatibility claim made by silence is the one this
    project refuses to accept (ADR 0018 guardrail on named tested versions).
    """

    name: str
    supported_openapi: tuple[str, ...]
    unsupported_features: tuple[str, ...]
    remote_assets: bool

    def render(self, request: _DocumentationRequest) -> _DocumentationPage: ...


def _validate_provider(provider: object) -> _DocumentationProvider:
    """Check one provider's declaration before it is ever asked to render."""
    if not isinstance(provider, _DocumentationProvider):
        raise _DocumentationDefinitionError(
            f"{type(provider).__name__} does not implement the documentation-provider contract"
        )

    name = provider.name
    if not isinstance(name, str) or not _PROVIDER_NAME.fullmatch(name):
        raise _DocumentationDefinitionError(f"invalid provider name: {name!r}")

    supported = provider.supported_openapi
    if not isinstance(supported, tuple) or not supported:
        raise _DocumentationDefinitionError(
            f"provider {name!r} must name the OpenAPI versions it was tested against"
        )
    for version in supported:
        if not isinstance(version, str) or not version.strip():
            raise _DocumentationDefinitionError(
                f"provider {name!r} declares an empty OpenAPI version"
            )

    unsupported = provider.unsupported_features
    if not isinstance(unsupported, tuple) or any(
        not isinstance(feature, str) or not feature.strip() for feature in unsupported
    ):
        raise _DocumentationDefinitionError(
            f"provider {name!r} must declare its unsupported features, even if none"
        )

    if not isinstance(provider.remote_assets, bool):
        raise _DocumentationDefinitionError(f"provider {name!r} remote_assets must be a boolean")
    return provider


class _DocumentationRegistry:
    """The optional providers one application offers, validated at startup.

    An empty registry is the supported no-UI deployment, not a degraded one:
    OpenAPI generation never requires a browser interface (RFC 0003).
    """

    __slots__ = ("_providers",)

    def __init__(self) -> None:
        self._providers: dict[str, _DocumentationProvider] = {}

    def __len__(self) -> int:
        return len(self._providers)

    def __iter__(self) -> Iterator[_DocumentationProvider]:
        return iter(tuple(self._providers.values()))

    def __contains__(self, name: object) -> bool:
        return name in self._providers

    def register(self, provider: object) -> _DocumentationProvider:
        validated = _validate_provider(provider)
        if validated.name in self._providers:
            raise _DocumentationDefinitionError(
                f"a documentation provider named {validated.name!r} is already registered"
            )
        self._providers[validated.name] = validated
        return validated

    def get(self, name: str) -> _DocumentationProvider | None:
        return self._providers.get(name)

    def render(
        self,
        name: str,
        request: _DocumentationRequest,
        *,
        allow_remote_assets: bool = False,
    ) -> _DocumentationPage:
        """Render through one provider, refusing rather than degrading."""
        provider = self._providers.get(name)
        if provider is None:
            raise _DocumentationUnavailable(f"no documentation provider named {name!r}")
        _check_compatibility(provider, request.openapi_version)

        page = provider.render(request)
        if not isinstance(page, _DocumentationPage):
            raise _DocumentationDefinitionError(
                f"provider {name!r} returned {type(page).__name__}, not a _DocumentationPage"
            )
        _check_assets(provider, page, allow_remote_assets=allow_remote_assets)
        return page


def _check_compatibility(provider: _DocumentationProvider, openapi_version: str) -> None:
    """Refuse a renderer that was never tested against this document version.

    Rendering anyway would publish documentation that is wrong, and the
    canonical contract is never rewritten to suit a renderer (RFC 0003).
    """
    if openapi_version in provider.supported_openapi:
        return
    raise _DocumentationUnavailable(
        f"provider {provider.name!r} does not support OpenAPI {openapi_version}; "
        f"it declares {', '.join(provider.supported_openapi)}"
    )


def _check_assets(
    provider: _DocumentationProvider,
    page: _DocumentationPage,
    *,
    allow_remote_assets: bool,
) -> None:
    """Keep the pinned-local-asset baseline from eroding at render time."""
    if not page.csp.requires_network:
        return
    if not provider.remote_assets:
        raise _DocumentationDefinitionError(
            f"provider {provider.name!r} requires {page.csp.external_origins} "
            "but does not declare remote_assets"
        )
    if not allow_remote_assets:
        raise _DocumentationUnavailable(
            f"provider {provider.name!r} requires the external origins "
            f"{page.csp.external_origins}, which this application has not permitted"
        )

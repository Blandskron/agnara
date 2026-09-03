"""RFC 9457 problem responses for canonical capability failures.

Core failures are protocol-neutral: a stable :class:`FailureCode`, a message
and immutable details. This module owns the only place where those outcomes
acquire an HTTP status, a media type and a wire document. The status table is
authorization-relevant, so it is explicit and exhaustive rather than derived
from capability metadata.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from agnara.execution import CanonicalResult, Failure, FailureCode, Success
from agnara_http._response import (
    _ResponseSerializationError,
    _serialize_success,
    _SerializedResponse,
    _to_json_value,
)

_ABOUT_BLANK = "about:blank"
_PROBLEM_MEDIA_TYPE = b"application/problem+json"
_REDACTED_DETAIL = "The server could not complete the capability invocation."


class _ProblemDefinitionError(ValueError):
    """A problem-type configuration is invalid, detected at startup."""


@dataclass(frozen=True, slots=True)
class _ProblemMapping:
    """One reviewed projection of a failure code onto an HTTP problem shape."""

    status: int
    title: str


# RFC 9457 section 3.1: `title` is a short, occurrence-independent summary, so
# it is fixed per failure code and never carries the failure message.
_PROBLEMS: Mapping[FailureCode, _ProblemMapping] = MappingProxyType(
    {
        FailureCode.INVALID_INPUT: _ProblemMapping(400, "Invalid Input"),
        FailureCode.UNAUTHENTICATED: _ProblemMapping(401, "Unauthenticated"),
        FailureCode.FORBIDDEN: _ProblemMapping(403, "Forbidden"),
        FailureCode.NOT_FOUND: _ProblemMapping(404, "Not Found"),
        FailureCode.CONFLICT: _ProblemMapping(409, "Conflict"),
        FailureCode.INTERACTION_REQUIRED: _ProblemMapping(428, "Interaction Required"),
        FailureCode.RATE_LIMITED: _ProblemMapping(429, "Rate Limited"),
        FailureCode.INTERNAL_FAILURE: _ProblemMapping(500, "Internal Server Error"),
        FailureCode.UNAVAILABLE: _ProblemMapping(503, "Service Unavailable"),
        FailureCode.TIMEOUT: _ProblemMapping(504, "Timeout"),
    }
)


class _TransportFailure(StrEnum):
    """A request that failed before any capability could run.

    These are transport conditions, not capability outcomes, so they are not
    ``FailureCode`` members and never will be. ``FailureCode`` describes what
    a capability decided; this describes why one was never reached.
    """

    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    INVALID_INPUT = "invalid_input"
    CONTENT_TOO_LARGE = "content_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"


_TRANSPORT_PROBLEMS: Mapping[_TransportFailure, _ProblemMapping] = MappingProxyType(
    {
        _TransportFailure.INVALID_INPUT: _ProblemMapping(400, "Invalid Input"),
        _TransportFailure.NOT_FOUND: _ProblemMapping(404, "Not Found"),
        _TransportFailure.METHOD_NOT_ALLOWED: _ProblemMapping(405, "Method Not Allowed"),
        _TransportFailure.CONTENT_TOO_LARGE: _ProblemMapping(413, "Content Too Large"),
        _TransportFailure.UNSUPPORTED_MEDIA_TYPE: _ProblemMapping(415, "Unsupported Media Type"),
    }
)


def _problem_codes() -> tuple[str, ...]:
    """Every value the ``code`` extension member can take, deduplicated.

    Capability and transport failures share one problem-type namespace,
    because ``code`` is what a client actually reads. Where the semantics
    coincide, so does the code: a capability that reports ``not_found`` and a
    target that has no route document the same thing.
    """
    seen: dict[str, None] = {}
    for code in FailureCode:
        seen[code.value] = None
    for transport in _TransportFailure:
        seen[transport.value] = None
    return tuple(seen)


_ABOUT_BLANK_TYPES: Mapping[str, str] = MappingProxyType(
    dict.fromkeys(_problem_codes(), _ABOUT_BLANK)
)


def _compile_problem_types(base_uri: str | None = None) -> Mapping[str, str]:
    """Compile the immutable problem-type URIs used by one HTTP application.

    Agnara does not invent a hosted documentation origin. Without an explicit
    ``base_uri`` every problem keeps the RFC 9457 default type
    ``about:blank``, and the machine-readable discriminator stays the ``code``
    extension member.
    """
    if base_uri is None:
        return _ABOUT_BLANK_TYPES
    if not isinstance(base_uri, str) or not base_uri:
        raise _ProblemDefinitionError("problem type base URI must be a non-empty string")
    if not _is_uri_text(base_uri):
        raise _ProblemDefinitionError(f"invalid problem type base URI: {base_uri!r}")
    parts = urlsplit(base_uri)
    if not parts.scheme:
        raise _ProblemDefinitionError("problem type base URI must be absolute")
    if parts.query or parts.fragment:
        raise _ProblemDefinitionError("problem type base URI must not carry a query or fragment")
    if not base_uri.endswith("/"):
        raise _ProblemDefinitionError("problem type base URI must end with '/'")
    return MappingProxyType(
        {code: f"{base_uri}{code.replace('_', '-')}" for code in _problem_codes()}
    )


def _serialize_transport_failure(
    failure: _TransportFailure,
    detail: str,
    *,
    details: Mapping[str, Any] | None = None,
    headers: Iterable[tuple[bytes, bytes]] = (),
    problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES,
    instance: str | None = None,
) -> _SerializedResponse:
    """Project one pre-capability failure onto a ``problem+json`` response.

    ``headers`` carries what the status requires rather than what a caller
    would like: RFC 9110 requires ``Allow`` on ``405``, and attaching it here
    means it cannot be forgotten at emission time.
    """
    if not isinstance(failure, _TransportFailure):
        raise TypeError(f"failure must be a _TransportFailure, got {type(failure).__name__}")
    if not isinstance(detail, str) or not detail:
        raise TypeError("detail must be a non-empty string")
    mapping = _TRANSPORT_PROBLEMS[failure]
    problem_type = problem_types.get(failure.value)
    if not isinstance(problem_type, str) or not problem_type:
        raise _ResponseSerializationError(f"transport failure {failure!r} has no problem type")

    document: dict[str, Any] = {
        "type": problem_type,
        "title": mapping.title,
        "status": mapping.status,
        "code": failure.value,
        "detail": detail,
    }
    if details:
        document["details"] = _to_json_value(dict(details), set(), path="$.details")
    if instance is not None:
        document["instance"] = _checked_instance(instance)

    body = _encode(document)
    return _with_headers(
        _SerializedResponse(
            status=mapping.status,
            headers=(
                (b"content-type", _PROBLEM_MEDIA_TYPE),
                (b"content-length", str(len(body)).encode("ascii")),
            ),
            body=body,
        ),
        headers,
    )


def _with_headers(
    response: _SerializedResponse,
    headers: Iterable[tuple[bytes, bytes]],
) -> _SerializedResponse:
    """Append required headers without letting them shadow the representation."""
    extra = tuple(headers)
    if not extra:
        return response
    reserved = {b"content-type", b"content-length"}
    for name, value in extra:
        if not isinstance(name, bytes) or not isinstance(value, bytes):
            raise TypeError("response headers must be byte pairs")
        if name.lower() in reserved:
            raise _ResponseSerializationError(
                f"{name.decode('ascii')} is owned by the response boundary"
            )
    return replace(response, headers=(*response.headers, *extra))


def _allow_header(methods: Iterable[str]) -> tuple[tuple[bytes, bytes], ...]:
    """Build the RFC 9110 ``Allow`` header for a 405, preserving order."""
    listed = tuple(methods)
    if not listed:
        raise _ResponseSerializationError("a 405 problem requires at least one allowed method")
    return ((b"allow", ", ".join(listed).encode("ascii")),)


def _serialize_failure(
    result: Failure,
    *,
    problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES,
    instance: str | None = None,
) -> _SerializedResponse:
    """Project one canonical failure onto a complete ``problem+json`` response."""
    if not isinstance(result, Failure):
        raise TypeError(f"result must be Failure, got {type(result).__name__}")
    mapping = _PROBLEMS.get(result.code)
    if mapping is None:  # pragma: no cover - guarded by an exhaustiveness test
        raise _ResponseSerializationError(f"failure code {result.code!r} has no reviewed status")
    problem_type = problem_types.get(result.code.value)
    if not isinstance(problem_type, str) or not problem_type:
        raise _ResponseSerializationError(f"failure code {result.code!r} has no problem type")

    document: dict[str, Any] = {
        "type": problem_type,
        "title": mapping.title,
        "status": mapping.status,
        "code": result.code.value,
    }
    if result.code is FailureCode.INTERNAL_FAILURE:
        # An internal failure carries server-side context that a client must
        # never receive, whatever the handler placed in it.
        document["detail"] = _REDACTED_DETAIL
    else:
        document["detail"] = result.message
        if result.details:
            details = _to_json_value(dict(result.details), set(), path="$.details")
            document["details"] = details
    if instance is not None:
        document["instance"] = _checked_instance(instance)

    body = _encode(document)
    return _SerializedResponse(
        status=mapping.status,
        headers=(
            (b"content-type", _PROBLEM_MEDIA_TYPE),
            (b"content-length", str(len(body)).encode("ascii")),
        ),
        body=body,
    )


def _serialize_result(
    result: CanonicalResult[Any],
    *,
    problem_types: Mapping[str, str] = _ABOUT_BLANK_TYPES,
    instance: str | None = None,
) -> _SerializedResponse:
    """Serialize either half of a canonical outcome through its own boundary."""
    if isinstance(result, Failure):
        return _serialize_failure(result, problem_types=problem_types, instance=instance)
    if isinstance(result, Success):
        return _serialize_success(result)
    raise TypeError(f"result must be Success or Failure, got {type(result).__name__}")


def _checked_instance(instance: str) -> str:
    """Accept a percent-encoded request target, not a decoded ASGI path."""
    if not isinstance(instance, str) or not instance:
        raise _ResponseSerializationError("problem instance must be a non-empty string")
    if not _is_uri_text(instance):
        raise _ResponseSerializationError(f"problem instance is not a URI reference: {instance!r}")
    return instance


def _is_uri_text(value: str) -> bool:
    """Reject anything a URI reference cannot carry unencoded."""
    return value.isascii() and not any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
        for character in value
    )


def _encode(document: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:  # pragma: no cover - defensive
        raise _ResponseSerializationError("problem document is not valid UTF-8 JSON") from error


# Last resort for a dispatcher that cannot serialize an outcome. Built once at
# import so emitting it can never itself fail, and immutable so it is shared
# without locks.
_INTERNAL_PROBLEM: _SerializedResponse = _serialize_failure(
    Failure(FailureCode.INTERNAL_FAILURE, "capability invocation failed")
)

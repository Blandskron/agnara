"""Compiled, explicit HTTP request binding for capability inputs."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from urllib.parse import unquote_to_bytes

from agnara.execution import ExecutionPlan
from agnara.schema import TypeSchema

_INTEGER = re.compile(r"[+-]?\d+\Z")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
_HEADER_NAME = re.compile(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
_BAD_PERCENT = re.compile(rb"%(?![0-9A-Fa-f]{2})")
#: RFC 6265 cookie-name is an HTTP token, same grammar as a header name.
_COOKIE_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+\Z")
#: RFC 7578 boundary: 1-70 characters from a restricted set, no trailing space.
_BOUNDARY = re.compile(rb"[0-9A-Za-z'()+_,\-./:=? ]{1,70}\Z")
#: A multipart part name, from `Content-Disposition: form-data; name="..."`.
_DISPOSITION_PARAMETER = re.compile(r';\s*([!#$%&\'*+\-.^_`|~0-9A-Za-z]+)\s*=\s*("([^"]*)"|[^";]*)')

#: Most parts one multipart body may contain. A body under `max_body_bytes`
#: can still carry tens of thousands of empty parts, and each one costs a
#: dictionary entry and a header parse. Bounded independently of total size.
_DEFAULT_MAX_PARTS = 64

type _Message = dict[str, Any]
type _Receive = Callable[[], Awaitable[_Message]]


class _BindingDefinitionError(ValueError):
    """A binding declaration is invalid or ambiguous."""


class _BindingFailure(StrEnum):
    """Why request data could not be bound, for a dispatcher to branch on.

    A dispatcher must not read the message text to decide a status, so the
    reason is part of the error's contract.
    """

    MALFORMED = "malformed"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    CONTENT_TOO_LARGE = "content_too_large"
    DISCONNECTED = "disconnected"


class _RequestBindingError(ValueError):
    """HTTP request data cannot be bound to the declared input."""

    def __init__(
        self,
        message: str,
        *,
        location: str,
        failure: _BindingFailure = _BindingFailure.MALFORMED,
    ) -> None:
        super().__init__(f"{location}: {message}")
        self.message = message
        self.location = location
        self.failure = failure


class _BindingSource(StrEnum):
    """Where one capability input is read from.

    ``BODY``, ``FORM`` and ``UPLOAD`` all consume the request body and are
    therefore mutually exclusive per route: a request has one body, and
    ADR 0072 refuses to guess which encoding an application meant.
    """

    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    BODY = "body"
    COOKIE = "cookie"
    FORM = "form"
    UPLOAD = "upload"


#: Sources that read the request body, and the content type each requires.
_BODY_SOURCES: Mapping[_BindingSource, str] = MappingProxyType(
    {
        _BindingSource.BODY: "application/json",
        _BindingSource.FORM: "",
        _BindingSource.UPLOAD: "multipart/form-data",
    }
)

#: Content types a ``FORM`` binding accepts. An HTML form posts one of these
#: depending on its ``enctype``, so both are the same declaration to an
#: application: it asked for a form field, not for an encoding.
_FORM_MEDIA_TYPES = frozenset({"application/x-www-form-urlencoded", "multipart/form-data"})


@dataclass(frozen=True, slots=True)
class _InputBinding:
    input_name: str
    source: _BindingSource
    wire_name: str | None = None


@dataclass(frozen=True, slots=True)
class _CompiledBinding:
    input_name: str
    source: _BindingSource
    wire_name: str
    scalar_type: str | None
    binary: bool = False
    schema: TypeSchema | None = None


@dataclass(frozen=True, slots=True)
class _HTTPBindingPlan:
    bindings: tuple[_CompiledBinding, ...]
    max_body_bytes: int
    max_parts: int = _DEFAULT_MAX_PARTS

    @classmethod
    def compile(
        cls,
        execution_plan: ExecutionPlan,
        path_parameter_names: Iterable[str],
        bindings: Iterable[_InputBinding],
        *,
        max_body_bytes: int = 1_048_576,
        max_parts: int = _DEFAULT_MAX_PARTS,
    ) -> _HTTPBindingPlan:
        if not isinstance(execution_plan, ExecutionPlan):
            raise _BindingDefinitionError("execution_plan must be an ExecutionPlan")
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or max_body_bytes < 1
        ):
            raise _BindingDefinitionError("max_body_bytes must be a positive integer")
        if isinstance(max_parts, bool) or not isinstance(max_parts, int) or max_parts < 1:
            raise _BindingDefinitionError("max_parts must be a positive integer")

        path_names = tuple(path_parameter_names)
        if len(path_names) != len(set(path_names)):
            raise _BindingDefinitionError("path parameter names must be unique")
        declared = tuple(bindings)
        seen_inputs: set[str] = set()
        seen_wire: set[tuple[_BindingSource, str]] = set()
        body_count = 0
        compiled: list[_CompiledBinding] = []

        for binding in declared:
            if not isinstance(binding, _InputBinding):
                raise _BindingDefinitionError("bindings must contain _InputBinding values")
            if not isinstance(binding.source, _BindingSource):
                raise _BindingDefinitionError(
                    f"binding source must be a _BindingSource, got {type(binding.source).__name__}"
                )
            if binding.input_name not in execution_plan.input_schemas:
                raise _BindingDefinitionError(f"unknown capability input: {binding.input_name!r}")
            if binding.input_name in seen_inputs:
                raise _BindingDefinitionError(f"input {binding.input_name!r} has multiple sources")
            seen_inputs.add(binding.input_name)

            wire_name = binding.wire_name or binding.input_name
            if not wire_name:
                raise _BindingDefinitionError("wire names must not be empty")
            if binding.source is _BindingSource.HEADER:
                try:
                    encoded_name = wire_name.encode("ascii")
                except UnicodeEncodeError as error:
                    raise _BindingDefinitionError(
                        f"invalid HTTP header name: {wire_name!r}"
                    ) from error
                if not _HEADER_NAME.fullmatch(encoded_name):
                    raise _BindingDefinitionError(f"invalid HTTP header name: {wire_name!r}")
                wire_name = wire_name.lower()
            if binding.source is _BindingSource.COOKIE and not _COOKIE_NAME.fullmatch(wire_name):
                # RFC 6265 cookie-name is an HTTP token. Unlike a header it is
                # case-sensitive, so it is checked but never folded.
                raise _BindingDefinitionError(f"invalid cookie name: {wire_name!r}")
            if binding.source is _BindingSource.PATH and wire_name not in path_names:
                raise _BindingDefinitionError(f"unknown route path parameter: {wire_name!r}")

            key = (binding.source, wire_name)
            if key in seen_wire:
                raise _BindingDefinitionError(
                    f"{binding.source.value} value {wire_name!r} binds more than one input"
                )
            seen_wire.add(key)

            scalar_type: str | None = None
            binary = False
            if binding.source is _BindingSource.BODY:
                body_count += 1
                if body_count > 1:
                    raise _BindingDefinitionError("only one JSON body input is supported")
            else:
                fragment = execution_plan.input_schemas[binding.input_name].json_schema()
                scalar = _scalar_descriptor(fragment)
                if scalar is None:
                    raise _BindingDefinitionError(
                        f"{binding.source.value} input {binding.input_name!r} "
                        "must have a scalar schema"
                    )
                scalar_type, binary = scalar
                if binding.source is _BindingSource.UPLOAD and not binary:
                    # An upload is file content, and the only schema that says
                    # so is `bytes`. Accepting `str` would decode arbitrary
                    # uploaded bytes as text and fail on the first PNG.
                    raise _BindingDefinitionError(
                        f"upload input {binding.input_name!r} must be annotated `bytes`"
                    )
            compiled.append(
                _CompiledBinding(
                    binding.input_name,
                    binding.source,
                    wire_name,
                    scalar_type,
                    binary,
                    execution_plan.input_schemas[binding.input_name],
                )
            )

        missing = sorted(execution_plan.required_inputs.difference(seen_inputs))
        if missing:
            raise _BindingDefinitionError(f"required input {missing[0]!r} has no HTTP binding")
        bound_paths = {item.wire_name for item in compiled if item.source is _BindingSource.PATH}
        unbound_paths = sorted(set(path_names).difference(bound_paths))
        if unbound_paths:
            raise _BindingDefinitionError(f"route path parameter {unbound_paths[0]!r} is not bound")

        # One request has one body. JSON, form fields and uploads are three
        # different readings of it, and a route that declares two of them has
        # not decided what it accepts (ADR 0072).
        body_kinds = {item.source for item in compiled}.intersection(_BODY_SOURCES)
        if _BindingSource.BODY in body_kinds and len(body_kinds) > 1:
            other = sorted(kind.value for kind in body_kinds - {_BindingSource.BODY})
            raise _BindingDefinitionError(
                f"a JSON body input cannot be combined with {other[0]} inputs; "
                "one request has one body"
            )
        return cls(tuple(compiled), max_body_bytes, max_parts)


async def _bind_request(
    plan: _HTTPBindingPlan,
    *,
    path_parameters: Mapping[str, str],
    query_string: bytes,
    headers: Iterable[tuple[bytes, bytes]],
    receive: _Receive,
) -> dict[str, Any]:
    """Extract one request payload; semantic validation remains in core."""
    query = _parse_query(query_string)
    header_values = _parse_headers(headers)
    payload: dict[str, Any] = {}
    body_kinds = {item.source for item in plan.bindings}.intersection(_BODY_SOURCES)
    cookies: dict[str, list[str]] | None = None

    for binding in plan.bindings:
        if binding.source in _BODY_SOURCES:
            continue
        source: Mapping[str, list[str]]
        if binding.source is _BindingSource.PATH:
            source = {name: [value] for name, value in path_parameters.items()}
        elif binding.source is _BindingSource.QUERY:
            source = query
        elif binding.source is _BindingSource.COOKIE:
            if cookies is None:
                # Parsed once per request, and only when a cookie is bound, so
                # a route that reads no cookie never pays for a Cookie header.
                cookies = _parse_cookies(header_values.get("cookie", ()))
            source = cookies
        else:
            source = header_values
        values = source.get(binding.wire_name)
        if values is None:
            continue
        if len(values) != 1:
            raise _RequestBindingError(
                "duplicate scalar value", location=f"{binding.source.value}.{binding.wire_name}"
            )
        payload[binding.input_name] = _convert_scalar(values[0], binding)

    if body_kinds:
        # The media type is settled before a single byte is read. ADR 0026
        # forbids reading a body without a binding, and the same reasoning
        # applies to a body this route cannot decode: buffering megabytes only
        # to answer 415 is work an unauthenticated client should not be able
        # to ask for.
        decoding = _decoding(plan, body_kinds, header_values)
        raw_body = await _read_body(receive, plan.max_body_bytes)
        _bind_body(payload, plan, decoding, raw_body)
    return payload


@dataclass(frozen=True, slots=True)
class _BodyDecoding:
    """How this route reads the one request body, decided before reading it."""

    #: ``BODY``, ``FORM`` or ``UPLOAD``: which reading the route declared.
    kind: _BindingSource
    #: The media type the request actually sent, already normalized.
    media_type: str
    #: The validated multipart boundary, or ``None`` for the other kinds.
    boundary: bytes | None


def _decoding(
    plan: _HTTPBindingPlan,
    body_kinds: set[_BindingSource],
    header_values: Mapping[str, list[str]],
) -> _BodyDecoding:
    """Settle the body encoding from the headers alone, before reading it."""
    media_type, parameters = _content_type(header_values)
    if _BindingSource.BODY in body_kinds:
        if media_type != "application/json":
            raise _RequestBindingError(
                "expected application/json",
                location="header.content-type",
                failure=_BindingFailure.UNSUPPORTED_MEDIA_TYPE,
            )
        return _BodyDecoding(_BindingSource.BODY, media_type, None)

    uploads_declared = _BindingSource.UPLOAD in body_kinds
    if media_type == "multipart/form-data":
        return _BodyDecoding(_BindingSource.UPLOAD, media_type, _boundary(parameters))
    if media_type == "application/x-www-form-urlencoded" and not uploads_declared:
        return _BodyDecoding(_BindingSource.FORM, media_type, None)
    raise _RequestBindingError(
        "expected multipart/form-data"
        if uploads_declared
        else "expected application/x-www-form-urlencoded or multipart/form-data",
        location="header.content-type",
        failure=_BindingFailure.UNSUPPORTED_MEDIA_TYPE,
    )


def _bind_body(
    payload: dict[str, Any],
    plan: _HTTPBindingPlan,
    decoding: _BodyDecoding,
    raw_body: bytes,
) -> None:
    """Decode the one request body the way `_decoding` already settled."""
    if decoding.kind is _BindingSource.BODY:
        _bind_json(payload, plan, raw_body)
        return
    if decoding.boundary is None:
        fields = _parse_query(raw_body)
        files: dict[str, bytes] = {}
    else:
        fields, files = _parse_multipart(raw_body, decoding.boundary, plan.max_parts)

    for binding in plan.bindings:
        if binding.source is _BindingSource.FORM:
            values = fields.get(binding.wire_name)
            if values is None:
                continue
            if len(values) != 1:
                raise _RequestBindingError(
                    "duplicate form field", location=f"form.{binding.wire_name}"
                )
            payload[binding.input_name] = _convert_scalar(values[0], binding)
        elif binding.source is _BindingSource.UPLOAD:
            content = files.get(binding.wire_name)
            if content is not None:
                payload[binding.input_name] = content


def _bind_json(payload: dict[str, Any], plan: _HTTPBindingPlan, raw_body: bytes) -> None:
    binding = next(item for item in plan.bindings if item.source is _BindingSource.BODY)
    if not raw_body:
        return
    try:
        text = raw_body.decode("utf-8")
        decoded = json.loads(
            text,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            object_pairs_hook=_object_without_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _RequestBindingError("invalid UTF-8 JSON body", location="body") from error
    payload[binding.input_name] = decoded


def _content_type(header_values: Mapping[str, list[str]]) -> tuple[str, str]:
    """Split the one Content-Type header into media type and parameters.

    A missing header, and two of them, both yield an empty media type: no
    supported reading matches it, so the caller answers with the same
    "expected <type>" the route would give for any other wrong type. Naming
    what to send is more useful than naming what was wrong with the header.
    """
    values = header_values.get("content-type", [])
    if len(values) != 1:
        return "", ""
    media_type, _, parameters = values[0].partition(";")
    return media_type.strip().lower(), parameters


def _parse_cookies(raw_values: Iterable[str]) -> dict[str, list[str]]:
    """Parse RFC 6265 cookie pairs from every Cookie header.

    A cookie value is opaque text. Percent, base64 and quoted forms are left
    exactly as sent, because guessing an encoding would corrupt a value the
    capability is about to validate.

    A pair whose name is not a token is skipped rather than failing the
    request: a browser sends cookies this application never set, and one
    malformed pair from an unrelated origin must not become a 400 for
    everything else on the route.
    """
    values: dict[str, list[str]] = {}
    for raw in raw_values:
        for pair in raw.split(";"):
            name, separator, value = pair.partition("=")
            if not separator:
                continue
            stripped = name.strip()
            if not _COOKIE_NAME.fullmatch(stripped):
                continue
            values.setdefault(stripped, []).append(value.strip())
    return values


def _parse_multipart(
    raw_body: bytes,
    boundary: bytes,
    max_parts: int,
) -> tuple[dict[str, list[str]], dict[str, bytes]]:
    """Parse one bounded multipart/form-data body into fields and files.

    The whole body is already inside `max_body_bytes`: it was read under that
    limit before this function saw it, so no part can be larger than the
    limit the route declared.

    Nothing here touches the filesystem, so there is no temporary file to leak
    and nothing to clean up on cancellation or error. An upload is bytes owned
    by the invocation payload and released with it.

    The client filename is deliberately not returned. It is attacker
    controlled, every safe use of it requires generating a name anyway, and
    exposing one needs the value type ADR 0072 defers.
    """
    delimiter = b"--" + boundary
    if not raw_body.startswith(delimiter):
        raise _RequestBindingError("malformed multipart body", location="body")
    fields: dict[str, list[str]] = {}
    files: dict[str, bytes] = {}
    segments = raw_body.split(b"\r\n" + delimiter)
    segments[0] = segments[0][len(delimiter) :]
    if len(segments) > max_parts + 1:
        raise _RequestBindingError(
            f"multipart body carries more than {max_parts} parts",
            location="body",
            failure=_BindingFailure.CONTENT_TOO_LARGE,
        )
    for index, segment in enumerate(segments):
        if segment.rstrip(b"\r\n") == b"--":
            if index == 0:
                raise _RequestBindingError("multipart body has no parts", location="body")
            return fields, files
        if not segment:
            # The body stopped at a delimiter without the closing "--", so the
            # sender was cut off rather than sending a malformed part.
            raise _RequestBindingError("multipart body is not terminated", location="body")
        if not segment.startswith(b"\r\n"):
            raise _RequestBindingError("malformed multipart part", location="body")
        head, separator, content = segment[2:].partition(b"\r\n\r\n")
        if not separator:
            raise _RequestBindingError("multipart part has no header block", location="body")
        name, is_file = _part_name(head)
        if is_file:
            if name in files:
                raise _RequestBindingError(f"duplicate upload part {name!r}", location="body")
            files[name] = content
        else:
            try:
                fields.setdefault(name, []).append(content.decode("utf-8"))
            except UnicodeDecodeError as error:
                raise _RequestBindingError(
                    "multipart field is not valid UTF-8", location=f"form.{name}"
                ) from error
    raise _RequestBindingError("multipart body is not terminated", location="body")


def _boundary(parameters: str) -> bytes:
    """Extract and validate the boundary the sender declared."""
    for match in _DISPOSITION_PARAMETER.finditer(f";{parameters}"):
        if match.group(1).lower() != "boundary":
            continue
        value = match.group(3) if match.group(3) is not None else match.group(2).strip()
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError as error:
            raise _RequestBindingError(
                "invalid multipart boundary", location="header.content-type"
            ) from error
        if not _BOUNDARY.fullmatch(encoded) or encoded.endswith(b" "):
            raise _RequestBindingError("invalid multipart boundary", location="header.content-type")
        return encoded
    raise _RequestBindingError(
        "multipart/form-data requires a boundary", location="header.content-type"
    )


def _part_name(head: bytes) -> tuple[str, bool]:
    """Read one part name, and whether the part is a file.

    A part is a file exactly when its Content-Disposition carries a
    `filename` parameter, which is what RFC 7578 says and what browsers do.
    The value is never read.
    """
    text = head.decode("latin-1")
    disposition: str | None = None
    for line in text.split("\r\n"):
        field, separator, value = line.partition(":")
        if separator and field.strip().lower() == "content-disposition":
            disposition = value
            break
    if disposition is None:
        raise _RequestBindingError("multipart part has no content-disposition", location="body")
    kind, _, parameters = disposition.partition(";")
    if kind.strip().lower() != "form-data":
        raise _RequestBindingError("multipart part is not form-data", location="body")
    name: str | None = None
    is_file = False
    for match in _DISPOSITION_PARAMETER.finditer(f";{parameters}"):
        key = match.group(1).lower()
        value = match.group(3) if match.group(3) is not None else match.group(2).strip()
        if key == "name" and name is None:
            name = value
        elif key == "filename":
            is_file = True
    if not name:
        raise _RequestBindingError("multipart part has no name", location="body")
    return name, is_file


def _parse_query(raw: bytes) -> dict[str, list[str]]:
    if not isinstance(raw, bytes):
        raise _RequestBindingError("query string must be bytes", location="query")
    values: dict[str, list[str]] = {}
    for pair in raw.split(b"&") if raw else ():
        name, separator, value = pair.partition(b"=")
        if _BAD_PERCENT.search(name) or _BAD_PERCENT.search(value):
            raise _RequestBindingError("invalid percent encoding", location="query")
        try:
            decoded_name = unquote_to_bytes(name.replace(b"+", b" ")).decode("utf-8")
            decoded_value = unquote_to_bytes(value.replace(b"+", b" ")).decode("utf-8")
        except UnicodeDecodeError as error:
            raise _RequestBindingError("invalid UTF-8", location="query") from error
        values.setdefault(decoded_name, []).append(decoded_value if separator else "")
    return values


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            raise ValueError(f"duplicate JSON object key: {name}")
        value[name] = item
    return value


def _parse_headers(headers: Iterable[tuple[bytes, bytes]]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for name, value in headers:
        if (
            not isinstance(name, bytes)
            or not isinstance(value, bytes)
            or not _HEADER_NAME.fullmatch(name)
        ):
            raise _RequestBindingError("invalid raw header", location="headers")
        values.setdefault(name.decode("ascii").lower(), []).append(value.decode("latin-1"))
    return values


def _convert_scalar(value: str, binding: _CompiledBinding) -> Any:
    location = f"{binding.source.value}.{binding.wire_name}"
    try:
        if binding.binary:
            return value.encode("latin-1")
        if binding.scalar_type == "string":
            return value
        if binding.scalar_type == "integer" and _INTEGER.fullmatch(value):
            return int(value)
        if binding.scalar_type == "number" and _NUMBER.fullmatch(value):
            number = float(value)
            if math.isfinite(number):
                return number
        if binding.scalar_type == "boolean" and value in {"true", "false"}:
            return value == "true"
    except UnicodeEncodeError, OverflowError, ValueError:
        pass
    raise _RequestBindingError(f"invalid {binding.scalar_type} value", location=location)


async def _read_body(receive: _Receive, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if not isinstance(message, dict):
            raise _RequestBindingError("ASGI event must be a dictionary", location="body")
        message_type = message.get("type")
        if message_type == "http.disconnect":
            raise _RequestBindingError(
                "client disconnected",
                location="body",
                failure=_BindingFailure.DISCONNECTED,
            )
        if message_type != "http.request":
            raise _RequestBindingError("unexpected ASGI event", location="body")
        chunk = message.get("body", b"")
        if not isinstance(chunk, bytes):
            raise _RequestBindingError("ASGI body chunk must be bytes", location="body")
        size += len(chunk)
        if size > limit:
            raise _RequestBindingError(
                "request body exceeds configured limit",
                location="body",
                failure=_BindingFailure.CONTENT_TOO_LARGE,
            )
        chunks.append(chunk)
        more = message.get("more_body", False)
        if not isinstance(more, bool):
            raise _RequestBindingError("ASGI more_body must be boolean", location="body")
        if not more:
            return b"".join(chunks)


def _scalar_descriptor(fragment: Mapping[str, Any]) -> tuple[str, bool] | None:
    """Return the HTTP scalar shape, accepting a scalar-or-null schema."""
    candidate = fragment
    alternatives = fragment.get("anyOf")
    if isinstance(alternatives, list):
        non_null = [
            item for item in alternatives if isinstance(item, dict) and item.get("type") != "null"
        ]
        nulls = [
            item for item in alternatives if isinstance(item, dict) and item.get("type") == "null"
        ]
        if len(non_null) != 1 or len(nulls) != 1 or len(alternatives) != 2:
            return None
        candidate = non_null[0]
    scalar_type = candidate.get("type")
    if scalar_type not in {"string", "integer", "number", "boolean"}:
        return None
    return scalar_type, scalar_type == "string" and candidate.get("format") == "binary"

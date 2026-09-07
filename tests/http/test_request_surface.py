"""I7: cookies, forms and uploads, and everything they refuse.

ADR 0072 fixes what `0.1.0a4` owns of the HTTP request surface. This module
tests the three new binding sources at the binding layer: the matrix every
source owes — missing, present, required, optional, repeated, decoded, badly
encoded, name-conflicting, type-checked, malformed — plus the multipart
parser's own failure modes and the limits that bound it.

`test_public_composition.py` covers the same features through public API and
a served request; this file is where the edges live.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from agnara.capability import CapabilityDefinition, CapabilityId
from agnara.core.di import DIRegistry
from agnara.execution import ExecutionPlan
from agnara_http._binding import (
    _bind_request,
    _BindingDefinitionError,
    _BindingFailure,
    _BindingSource,
    _HTTPBindingPlan,
    _InputBinding,
    _RequestBindingError,
)

BOUNDARY = "----agnara9Zx"


def plan(
    handler: Callable[..., Any],
    *bindings: _InputBinding,
    max_body_bytes: int = 1_048_576,
    max_parts: int = 64,
    path_parameters: tuple[str, ...] = (),
) -> _HTTPBindingPlan:
    return _HTTPBindingPlan.compile(
        ExecutionPlan.compile(
            CapabilityDefinition(CapabilityId("tests", "target"), handler), DIRegistry()
        ),
        path_parameters,
        bindings,
        max_body_bytes=max_body_bytes,
        max_parts=max_parts,
    )


def bind(
    binding_plan: _HTTPBindingPlan,
    *,
    headers: tuple[tuple[bytes, bytes], ...] = (),
    body: bytes = b"",
    query: bytes = b"",
) -> dict[str, Any]:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return asyncio.run(
        _bind_request(
            binding_plan,
            path_parameters={},
            query_string=query,
            headers=headers,
            receive=receive,
        )
    )


def cookie(value: str) -> tuple[tuple[bytes, bytes], ...]:
    return ((b"cookie", value.encode("latin-1")),)


def urlencoded(body: str) -> dict[str, Any]:
    return {
        "headers": ((b"content-type", b"application/x-www-form-urlencoded"),),
        "body": body.encode("utf-8"),
    }


def multipart(*parts: bytes, boundary: str = BOUNDARY, terminate: bool = True) -> dict[str, Any]:
    """Assemble a multipart body exactly as a client would put it on the wire."""
    delimiter = f"--{boundary}".encode("ascii")
    chunks = [delimiter]
    for part in parts:
        chunks.append(b"\r\n" + part + b"\r\n" + delimiter)
    body = b"".join(chunks) + (b"--\r\n" if terminate else b"")
    return {
        "headers": ((b"content-type", f'multipart/form-data; boundary="{boundary}"'.encode()),),
        "body": body,
    }


def field(name: str, value: str) -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"'.encode()
    return disposition + b"\r\n\r\n" + value.encode("utf-8")


def upload(name: str, filename: str, content: bytes, media: str = "text/plain") -> bytes:
    disposition = f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode()
    return disposition + f"\r\nContent-Type: {media}".encode() + b"\r\n\r\n" + content


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------


def test_a_cookie_binds_by_name() -> None:
    def handler(session: str) -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    assert bind(compiled, headers=cookie("session=abc123")) == {"session": "abc123"}


def test_a_missing_cookie_stays_absent_so_core_applies_the_default() -> None:
    def handler(session: str = "anonymous") -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    assert bind(compiled, headers=cookie("other=1")) == {}
    assert bind(compiled) == {}


def test_one_cookie_is_read_from_several_pairs_and_several_headers() -> None:
    def handler(session: str, theme: str) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("session", _BindingSource.COOKIE),
        _InputBinding("theme", _BindingSource.COOKIE),
    )
    headers = ((b"cookie", b"session=abc; unrelated=x"), (b"cookie", b"theme=dark"))

    assert bind(compiled, headers=headers) == {"session": "abc", "theme": "dark"}


def test_a_repeated_cookie_is_refused_rather_than_resolved() -> None:
    def handler(session: str) -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    with pytest.raises(_RequestBindingError, match=r"cookie\.session: duplicate scalar value"):
        bind(compiled, headers=cookie("session=a; session=b"))


def test_a_cookie_name_is_case_sensitive_unlike_a_header() -> None:
    def handler(session: str = "none") -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    assert bind(compiled, headers=cookie("SESSION=abc")) == {}


@pytest.mark.parametrize(
    "raw",
    [
        "session=abc; =nameless",
        "session=abc; bad name=1",
        "session=abc; novalue",
        "session=abc;;",
    ],
)
def test_an_unparseable_pair_never_fails_the_request(raw: str) -> None:
    """A browser sends cookies this application never set."""

    def handler(session: str) -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    assert bind(compiled, headers=cookie(raw)) == {"session": "abc"}


def test_a_cookie_value_is_opaque_text() -> None:
    """Guessing an encoding would corrupt a value core is about to validate."""

    def handler(session: str) -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    assert bind(compiled, headers=cookie("session=%2Fa+b%3D")) == {"session": "%2Fa+b%3D"}
    assert bind(compiled, headers=cookie('session="quoted"')) == {"session": '"quoted"'}


def test_a_cookie_is_type_checked_like_any_scalar() -> None:
    def handler(visits: int) -> None: ...

    compiled = plan(handler, _InputBinding("visits", _BindingSource.COOKIE))

    assert bind(compiled, headers=cookie("visits=7")) == {"visits": 7}
    with pytest.raises(_RequestBindingError, match=r"cookie\.visits: invalid integer value"):
        bind(compiled, headers=cookie("visits=many"))


def test_a_cookie_can_be_renamed_on_the_wire() -> None:
    def handler(session: str) -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE, "sid"))

    assert bind(compiled, headers=cookie("sid=abc")) == {"session": "abc"}


@pytest.mark.parametrize("name", ["has space", "a=b", "sémantique", "a;b"])
def test_an_invalid_cookie_name_fails_at_compile(name: str) -> None:
    def handler(session: str) -> None: ...

    with pytest.raises(_BindingDefinitionError):
        plan(handler, _InputBinding("session", _BindingSource.COOKIE, name))


def test_a_cookie_input_must_be_scalar() -> None:
    def handler(session: dict[str, str]) -> None: ...

    with pytest.raises(_BindingDefinitionError, match="must have a scalar schema"):
        plan(handler, _InputBinding("session", _BindingSource.COOKIE))


def test_a_cookie_and_a_query_may_share_a_name() -> None:
    """The name conflict rule is per source, because the sources are separate."""

    def handler(token: str, key: str) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("token", _BindingSource.COOKIE, "id"),
        _InputBinding("key", _BindingSource.QUERY, "id"),
    )

    assert bind(compiled, headers=cookie("id=c"), query=b"id=q") == {"token": "c", "key": "q"}


def test_two_inputs_cannot_bind_one_cookie() -> None:
    def handler(first: str, second: str) -> None: ...

    with pytest.raises(_BindingDefinitionError, match="binds more than one input"):
        plan(
            handler,
            _InputBinding("first", _BindingSource.COOKIE, "sid"),
            _InputBinding("second", _BindingSource.COOKIE, "sid"),
        )


# ---------------------------------------------------------------------------
# URL-encoded forms
# ---------------------------------------------------------------------------


def test_a_form_field_binds_from_an_urlencoded_body() -> None:
    def handler(email: str, remember: bool) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("email", _BindingSource.FORM),
        _InputBinding("remember", _BindingSource.FORM),
    )

    assert bind(compiled, **urlencoded("email=a%40b.com&remember=true")) == {
        "email": "a@b.com",
        "remember": True,
    }


def test_a_form_field_decodes_plus_as_space() -> None:
    def handler(note: str) -> None: ...

    compiled = plan(handler, _InputBinding("note", _BindingSource.FORM))

    assert bind(compiled, **urlencoded("note=hello+world")) == {"note": "hello world"}


def test_a_missing_form_field_stays_absent() -> None:
    def handler(email: str, remember: bool = False) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("email", _BindingSource.FORM),
        _InputBinding("remember", _BindingSource.FORM),
    )

    assert bind(compiled, **urlencoded("email=a%40b.com")) == {"email": "a@b.com"}


def test_a_repeated_form_field_is_refused() -> None:
    """ADR 0026 rejects repeated scalars; a list needs the collection design."""

    def handler(tag: str) -> None: ...

    compiled = plan(handler, _InputBinding("tag", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match=r"form\.tag: duplicate form field"):
        bind(compiled, **urlencoded("tag=a&tag=b"))


def test_a_form_field_is_type_checked() -> None:
    def handler(quantity: int) -> None: ...

    compiled = plan(handler, _InputBinding("quantity", _BindingSource.FORM))

    assert bind(compiled, **urlencoded("quantity=3")) == {"quantity": 3}
    with pytest.raises(_RequestBindingError, match=r"form\.quantity: invalid integer value"):
        bind(compiled, **urlencoded("quantity=three"))


@pytest.mark.parametrize("body", ["note=%zz", "note=%2"])
def test_invalid_percent_encoding_in_a_form_is_refused(body: str) -> None:
    def handler(note: str) -> None: ...

    compiled = plan(handler, _InputBinding("note", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="invalid percent encoding"):
        bind(compiled, **urlencoded(body))


def test_invalid_utf8_in_a_form_is_refused() -> None:
    def handler(note: str) -> None: ...

    compiled = plan(handler, _InputBinding("note", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="invalid UTF-8"):
        bind(
            compiled,
            headers=((b"content-type", b"application/x-www-form-urlencoded"),),
            body=b"note=%ff",
        )


def test_a_form_route_declines_a_json_body() -> None:
    def handler(email: str) -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError) as raised:
        bind(compiled, headers=((b"content-type", b"application/json"),), body=b"{}")
    assert raised.value.failure is _BindingFailure.UNSUPPORTED_MEDIA_TYPE
    assert "application/x-www-form-urlencoded" in raised.value.message


def test_a_form_input_must_be_scalar() -> None:
    def handler(payload: dict[str, str]) -> None: ...

    with pytest.raises(_BindingDefinitionError, match="must have a scalar schema"):
        plan(handler, _InputBinding("payload", _BindingSource.FORM))


# ---------------------------------------------------------------------------
# Multipart form fields
# ---------------------------------------------------------------------------


def test_a_form_field_binds_from_a_multipart_body() -> None:
    """One declaration reads either encoding: an application asked for a field."""

    def handler(email: str) -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    assert bind(compiled, **multipart(field("email", "a@b.com"))) == {"email": "a@b.com"}


def test_a_multipart_field_decodes_as_utf8() -> None:
    def handler(name: str) -> None: ...

    compiled = plan(handler, _InputBinding("name", _BindingSource.FORM))

    assert bind(compiled, **multipart(field("name", "ñandú"))) == {"name": "ñandú"}


def test_a_non_utf8_multipart_field_is_refused() -> None:
    def handler(name: str) -> None: ...

    compiled = plan(handler, _InputBinding("name", _BindingSource.FORM))
    part = b'Content-Disposition: form-data; name="name"\r\n\r\n\xff\xfe'

    with pytest.raises(
        _RequestBindingError, match=r"form\.name: multipart field is not valid UTF-8"
    ):
        bind(compiled, **multipart(part))


def test_a_part_without_a_header_block_is_refused() -> None:
    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="no header block"):
        bind(compiled, **multipart(b"no header block here"))


def test_a_repeated_multipart_field_is_refused() -> None:
    def handler(tag: str) -> None: ...

    compiled = plan(handler, _InputBinding("tag", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="duplicate form field"):
        bind(compiled, **multipart(field("tag", "a"), field("tag", "b")))


def test_an_unquoted_part_name_is_accepted() -> None:
    def handler(email: str) -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))
    part = b"Content-Disposition: form-data; name=email\r\n\r\na@b.com"

    assert bind(compiled, **multipart(part)) == {"email": "a@b.com"}


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def test_an_upload_binds_its_bytes() -> None:
    def handler(avatar: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("avatar", _BindingSource.UPLOAD))
    content = b"\x89PNG\r\n\x1a\n binary \x00 bytes"

    assert bind(compiled, **multipart(upload("avatar", "me.png", content))) == {"avatar": content}


def test_an_upload_carries_arbitrary_bytes_including_the_boundary_prefix() -> None:
    def handler(blob: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))
    content = b"--not-the-boundary\r\nstill content"

    assert bind(compiled, **multipart(upload("blob", "f.bin", content))) == {"blob": content}


def test_an_empty_upload_binds_empty_bytes_rather_than_being_absent() -> None:
    """A user who submitted an empty file did submit a file."""

    def handler(blob: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))

    assert bind(compiled, **multipart(upload("blob", "empty.txt", b""))) == {"blob": b""}


def test_a_missing_upload_stays_absent() -> None:
    def handler(blob: bytes = b"") -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))

    assert bind(compiled, **multipart(field("other", "x"))) == {}


def test_an_upload_and_form_fields_arrive_together() -> None:
    """What an ordinary upload form posts."""

    def handler(title: str, avatar: bytes) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("title", _BindingSource.FORM),
        _InputBinding("avatar", _BindingSource.UPLOAD),
    )

    payload = bind(
        compiled,
        **multipart(field("title", "Portrait"), upload("avatar", "me.png", b"\x89PNG")),
    )

    assert payload == {"title": "Portrait", "avatar": b"\x89PNG"}


def test_the_client_filename_is_never_exposed() -> None:
    """ADR 0072: attacker-controlled, and every safe use generates a name."""

    def handler(blob: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))
    hostile = "../../etc/passwd\x00.png"

    payload = bind(compiled, **multipart(upload("blob", hostile, b"content")))

    assert payload == {"blob": b"content"}
    assert "passwd" not in repr(payload)


def test_two_parts_with_one_upload_name_are_refused() -> None:
    """Several files need the collection binding ADR 0026 deferred."""

    def handler(blob: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))

    with pytest.raises(_RequestBindingError, match="duplicate upload part 'blob'"):
        bind(compiled, **multipart(upload("blob", "a", b"a"), upload("blob", "b", b"b")))


def test_an_upload_input_must_be_annotated_bytes() -> None:
    def handler(blob: str) -> None: ...

    with pytest.raises(_BindingDefinitionError, match="must be annotated `bytes`"):
        plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))


def test_an_upload_route_requires_multipart() -> None:
    def handler(blob: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD))

    with pytest.raises(_RequestBindingError) as raised:
        bind(
            compiled,
            headers=((b"content-type", b"application/x-www-form-urlencoded"),),
            body=b"blob=x",
        )
    assert raised.value.failure is _BindingFailure.UNSUPPORTED_MEDIA_TYPE
    assert raised.value.message == "expected multipart/form-data"


# ---------------------------------------------------------------------------
# Malformed multipart
# ---------------------------------------------------------------------------


DELIMITER = f"--{BOUNDARY}".encode("ascii")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"not a multipart body", "malformed multipart body"),
        (DELIMITER + b"--\r\n", "multipart body has no parts"),
        (b"\r\n" + DELIMITER + b"\r\nlate preamble", "malformed multipart body"),
    ],
)
def test_a_malformed_multipart_body_is_a_structured_failure(body: bytes, message: str) -> None:
    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match=message):
        bind(
            compiled,
            headers=((b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode()),),
            body=body,
        )


def test_an_unterminated_multipart_body_is_refused() -> None:
    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="not terminated"):
        bind(compiled, **multipart(field("email", "a@b.com"), terminate=False))


@pytest.mark.parametrize(
    ("part", "message"),
    [
        (b"X-Other: 1\r\n\r\nvalue", "no content-disposition"),
        (b'Content-Disposition: attachment; name="a"\r\n\r\nv', "not form-data"),
        (b"Content-Disposition: form-data\r\n\r\nv", "has no name"),
        (b'Content-Disposition: form-data; name=""\r\n\r\nv', "has no name"),
    ],
)
def test_a_malformed_part_header_is_refused(part: bytes, message: str) -> None:
    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match=message):
        bind(compiled, **multipart(part))


@pytest.mark.parametrize("boundary", ["", "x" * 71, "bad{brace}", "trailing "])
def test_an_invalid_boundary_is_refused(boundary: str) -> None:
    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="boundary"):
        bind(
            compiled,
            headers=((b"content-type", f'multipart/form-data; boundary="{boundary}"'.encode()),),
            body=b"whatever",
        )


def test_a_missing_boundary_is_refused() -> None:
    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))

    with pytest.raises(_RequestBindingError, match="requires a boundary"):
        bind(compiled, headers=((b"content-type", b"multipart/form-data"),), body=b"x")


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------


def test_the_part_count_is_bounded_independently_of_size() -> None:
    """A small body can still carry thousands of empty parts."""

    def handler(email: str = "") -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM), max_parts=2)

    with pytest.raises(_RequestBindingError) as raised:
        bind(compiled, **multipart(*(field(f"f{index}", "") for index in range(3))))
    assert raised.value.failure is _BindingFailure.CONTENT_TOO_LARGE
    assert "more than 2 parts" in raised.value.message


def test_the_part_limit_admits_exactly_its_bound() -> None:
    def handler(f0: str = "", f1: str = "") -> None: ...

    compiled = plan(
        handler,
        _InputBinding("f0", _BindingSource.FORM),
        _InputBinding("f1", _BindingSource.FORM),
        max_parts=2,
    )

    assert bind(compiled, **multipart(field("f0", "a"), field("f1", "b"))) == {"f0": "a", "f1": "b"}


def test_an_oversized_multipart_upload_is_refused_before_parsing() -> None:
    def handler(blob: bytes) -> None: ...

    compiled = plan(handler, _InputBinding("blob", _BindingSource.UPLOAD), max_body_bytes=32)

    with pytest.raises(_RequestBindingError) as raised:
        bind(compiled, **multipart(upload("blob", "big.bin", b"x" * 512)))
    assert raised.value.failure is _BindingFailure.CONTENT_TOO_LARGE


@pytest.mark.parametrize("limit", [0, -1, True])
def test_a_nonsense_part_limit_fails_at_compile(limit: object) -> None:
    def handler(email: str = "") -> None: ...

    with pytest.raises(_BindingDefinitionError, match="max_parts must be a positive integer"):
        plan(
            handler,
            _InputBinding("email", _BindingSource.FORM),
            max_parts=limit,  # ty: ignore[invalid-argument-type]
        )


def test_a_wrong_media_type_is_refused_without_reading_the_body() -> None:
    """Buffering megabytes only to answer 415 is work a client must not cause."""

    def handler(email: str) -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))
    reads = 0

    async def receive() -> dict[str, Any]:
        nonlocal reads
        reads += 1
        return {"type": "http.request", "body": b"x" * 4096, "more_body": False}

    with pytest.raises(_RequestBindingError):
        asyncio.run(
            _bind_request(
                compiled,
                path_parameters={},
                query_string=b"",
                headers=((b"content-type", b"text/plain"),),
                receive=receive,
            )
        )
    assert reads == 0


def test_two_content_type_headers_are_refused() -> None:
    def handler(email: str) -> None: ...

    compiled = plan(handler, _InputBinding("email", _BindingSource.FORM))
    headers = (
        (b"content-type", b"application/x-www-form-urlencoded"),
        (b"content-type", b"multipart/form-data; boundary=x"),
    )

    with pytest.raises(_RequestBindingError) as raised:
        bind(compiled, headers=headers, body=b"email=a")
    assert raised.value.failure is _BindingFailure.UNSUPPORTED_MEDIA_TYPE


# ---------------------------------------------------------------------------
# One request has one body
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("other", [_BindingSource.FORM, _BindingSource.UPLOAD])
def test_a_json_body_cannot_be_combined_with_a_form_or_upload(other: _BindingSource) -> None:
    def handler(payload: dict[str, str], extra: bytes) -> None: ...

    with pytest.raises(_BindingDefinitionError, match="one request has one body"):
        plan(
            handler,
            _InputBinding("payload", _BindingSource.BODY),
            _InputBinding("extra", other),
        )


def test_forms_and_uploads_combine_freely() -> None:
    def handler(title: str, blob: bytes) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("title", _BindingSource.FORM),
        _InputBinding("blob", _BindingSource.UPLOAD),
    )

    assert len(compiled.bindings) == 2


def test_body_sources_coexist_with_every_other_source() -> None:
    def handler(order_id: int, trace: str, session: str, title: str, blob: bytes) -> None: ...

    compiled = plan(
        handler,
        _InputBinding("order_id", _BindingSource.PATH),
        _InputBinding("trace", _BindingSource.HEADER, "x-trace"),
        _InputBinding("session", _BindingSource.COOKIE),
        _InputBinding("title", _BindingSource.FORM),
        _InputBinding("blob", _BindingSource.UPLOAD),
        path_parameters=("order_id",),
    )

    async def receive() -> dict[str, Any]:
        return {
            "type": "http.request",
            "body": multipart(field("title", "T"), upload("blob", "f", b"B"))["body"],
            "more_body": False,
        }

    payload = asyncio.run(
        _bind_request(
            compiled,
            path_parameters={"order_id": "7"},
            query_string=b"",
            headers=(
                (b"content-type", f'multipart/form-data; boundary="{BOUNDARY}"'.encode()),
                (b"x-trace", b"abc"),
                (b"cookie", b"session=s1"),
            ),
            receive=receive,
        )
    )

    assert payload == {
        "order_id": 7,
        "trace": "abc",
        "session": "s1",
        "title": "T",
        "blob": b"B",
    }


def test_no_body_is_read_when_no_body_source_is_declared() -> None:
    """ADR 0026's guardrail, still true with three body sources."""

    def handler(session: str) -> None: ...

    compiled = plan(handler, _InputBinding("session", _BindingSource.COOKIE))

    async def receive() -> dict[str, Any]:  # pragma: no cover - must not be called
        raise AssertionError("receive must not be called")

    assert asyncio.run(
        _bind_request(
            compiled,
            path_parameters={},
            query_string=b"",
            headers=cookie("session=s"),
            receive=receive,
        )
    ) == {"session": "s"}

"""HTTP correlation and execution-identity projection (ADR 0088)."""

from __future__ import annotations

import re
from collections.abc import Iterable

_REQUEST_ID = b"x-request-id"
_EXECUTION_ID = b"agnara-execution-id"
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
_MAX_CORRELATION_ID = 128


class _RequestIdentityError(ValueError):
    """The untrusted correlation header is absent, duplicated, or malformed."""


def _tracking_id(headers: Iterable[tuple[bytes, bytes]]) -> str | None:
    """Read one bounded opaque correlation value, never an execution selector."""
    values = [value for name, value in headers if name.lower() == _REQUEST_ID]
    if not values:
        return None
    if len(values) != 1:
        raise _RequestIdentityError("request correlation identifier must not be repeated")
    try:
        value = values[0].decode("ascii")
    except UnicodeDecodeError as error:
        raise _RequestIdentityError("request correlation identifier must be ASCII") from error
    if len(value) > _MAX_CORRELATION_ID or not _TOKEN.fullmatch(value):
        raise _RequestIdentityError("request correlation identifier is malformed")
    return value


def _execution_header(execution_id: str) -> tuple[bytes, bytes]:
    """Build the reviewed response header from a runtime-generated token."""
    return _EXECUTION_ID, execution_id.encode("ascii")

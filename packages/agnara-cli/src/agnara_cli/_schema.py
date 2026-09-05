"""``agnara schema openapi``: export the document the application already built.

`ARCHITECTURE.md` forbids `agnara-cli` from importing a sibling adapter, and
core must not depend on OpenAPI tooling, so the CLI cannot project a document
itself. That constraint produces the better design anyway: a second projection
in the CLI could disagree with the one `agnara-http` serves, and nobody would
notice until a client trusted the wrong one.

So the CLI exports what the composition produced. The target names an
attribute the application already exposes, and the contract is structural: the
bytes an HTTP surface would serve, the mapping those bytes come from, or a
callable producing either. When the target supplies bytes, they are emitted
unchanged — the export is byte-identical to what is served, not merely
equivalent to it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from agnara_cli._target import TargetError, resolve_attribute

__all__ = ["add_schema_parser", "run_schema"]

#: The same serialization `agnara_http._serialize_openapi` performs. Duplicated
#: rather than imported, because importing it would breach the package
#: boundary; a cross-surface test asserts the two agree byte for byte.
_JSON_ARGUMENTS: dict[str, Any] = {
    "allow_nan": False,
    "ensure_ascii": False,
    "separators": (",", ":"),
    "sort_keys": True,
}


def add_schema_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``schema`` and its formats on the root parser."""
    parser = subparsers.add_parser(
        "schema",
        help="export a protocol contract the application already produced",
        description=(
            "Export a schema document from a compiled application. The CLI does "
            "not project one: it exports what the composition built, so an "
            "export cannot disagree with what a server serves."
        ),
    )
    formats = parser.add_subparsers(dest="format", required=True, metavar="FORMAT")
    openapi = formats.add_parser(
        "openapi",
        help="export the OpenAPI document the application exposes",
        description=(
            "Export an OpenAPI document named as 'module:attribute'. The "
            "attribute may be the serialized bytes, the mapping they come from, "
            "or a zero-argument callable returning either. Importing the target "
            "executes the module that defines it."
        ),
    )
    openapi.add_argument(
        "target",
        help="the document to export, as 'module:attribute'",
    )
    openapi.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="DIR",
        help="a directory to search for the target module (repeatable)",
    )
    openapi.add_argument(
        "--output",
        metavar="FILE",
        help="write the document to this file instead of stdout",
    )
    openapi.add_argument(
        "--overwrite",
        action="store_true",
        help="allow --output to replace an existing file",
    )
    openapi.add_argument(
        "--pretty",
        action="store_true",
        help=(
            "indent the document for a human reader. The result is no longer "
            "byte-identical to what an HTTP surface serves."
        ),
    )
    openapi.set_defaults(handler=run_schema)


def _document(value: object) -> tuple[dict[str, Any], bytes | None]:
    """Read a target into a document, keeping its exact bytes when it has them.

    Returning both is the point. The parsed document is what gets validated
    and what ``--pretty`` re-renders; the original bytes are what a plain
    export emits, so the CLI never re-serializes something a server already
    serialized.
    """
    if callable(value):
        # Documented as zero-argument. A producer with a different signature
        # raises TypeError here and is reported like any other failure, rather
        # than being probed for an arity this contract does not define.
        producer = cast("Callable[[], object]", value)
        try:
            value = producer()
        except Exception as error:
            raise TargetError(f"producing the OpenAPI document failed: {error}") from error

    served: bytes | None = None
    if isinstance(value, bytes | bytearray):
        served = bytes(value)
        try:
            decoded = served.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TargetError("the OpenAPI document is not valid UTF-8") from error
        try:
            parsed = json.loads(decoded)
        except json.JSONDecodeError as error:
            raise TargetError(f"the OpenAPI document is not valid JSON: {error}") from error
    elif isinstance(value, Mapping):
        parsed = dict(value)
    else:
        raise TargetError(
            "the OpenAPI target must be bytes, a mapping, or a callable returning one, got "
            f"{type(value).__name__}"
        )

    if not isinstance(parsed, dict):
        raise TargetError(
            f"the OpenAPI document must be a JSON object, got {type(parsed).__name__}"
        )
    version = parsed.get("openapi")
    if not isinstance(version, str) or not version:
        raise TargetError(
            "the OpenAPI document must declare a string 'openapi' version; this does not "
            "look like an OpenAPI document"
        )
    return parsed, served


def _encode(document: Mapping[str, Any], served: bytes | None, *, pretty: bool) -> bytes:
    if pretty:
        return json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
    if served is not None:
        # Exactly what a server would send, including whatever the projection
        # chose. Re-serializing here would silently normalize it.
        return served
    try:
        return json.dumps(document, **_JSON_ARGUMENTS).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise TargetError(f"the OpenAPI document cannot be serialized as JSON: {error}") from error


def _write(destination: str, body: bytes, *, overwrite: bool) -> None:
    """Write the document, refusing to destroy a file nobody authorized."""
    path = Path(destination)
    if path.exists() and not overwrite:
        raise TargetError(f"{destination!r} already exists; pass --overwrite to replace it")
    try:
        path.write_bytes(body)
    except OSError as error:
        raise TargetError(f"cannot write {destination!r}: {error}") from error


def run_schema(arguments: argparse.Namespace) -> bytes | None:
    """Export the document, to stdout as exact bytes or to a file."""
    value = resolve_attribute(arguments.target, search_path=arguments.path)
    document, served = _document(value)
    body = _encode(document, served, pretty=arguments.pretty)
    if arguments.output is None:
        return body
    _write(arguments.output, body, overwrite=arguments.overwrite)
    return None

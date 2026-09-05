"""``agnara context``: the filtered snapshot, written for a model to read.

An agent can already read `agnara inspect --json`, and it costs the agent
context window to parse a shape rather than to understand capabilities. This
command renders the same filtered snapshot as prose a model reads directly.

Three rules make it safe to hand to a model rather than merely convenient.

It comes from the shared view, so it cannot describe a capability
``agnara inspect`` would hide from the same viewer. There is no second
discovery path here either.

It never asserts a withheld field. Risk, confirmation and idempotency always
carry a value in the model, so an unpublished one is omitted rather than
printed as its declared default — a model that read "risk: low" because the
real value was withheld would be misled about exactly the thing that matters.

It says what it is. The document states that it describes what a capability
does, not what the reader may do: seeing a capability is not authorization to
invoke it (ADR 0008), and a model reading this must not infer permission from
presence.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable

from agnara.introspection import (
    AppDescriptor,
    CapabilityDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    IntrospectionSnapshot,
)
from agnara_cli._render import schema_summary
from agnara_cli._view import add_view_arguments, resolve_view
from agnara_cli._write import write_document

__all__ = ["add_context_parser", "run_context"]

_NOT_AUTHORIZATION = (
    "Seeing a capability here is not permission to invoke it. Every invocation "
    "is authorized independently at call time, and a call you are not "
    "permitted to make will be refused whether or not it appears below."
)


def add_context_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``context`` and its arguments on the root parser."""
    parser = subparsers.add_parser(
        "context",
        help="write the visible capabilities as context for a model",
        description=(
            "Render the same filtered introspection snapshot 'agnara inspect' "
            "reads as Markdown a model can consume directly. Importing the "
            "target executes the module that defines it."
        ),
    )
    add_view_arguments(parser)
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="write the document to this file instead of stdout",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow --output to replace an existing file",
    )
    parser.set_defaults(handler=run_context)


def _safety(capability: CapabilityDescriptor, visibility: DiscoveryVisibility) -> str | None:
    """Describe what invoking this capability costs, or say nothing at all."""
    if not visibility.publishes(DiscoveryField.SAFETY):
        return None
    parts = [f"risk {capability.risk}"]
    if capability.confirmation != "never":
        parts.append(f"confirmation {capability.confirmation}")
    parts.append(f"idempotency {capability.idempotency}")
    return ", ".join(parts)


def _capability(
    capability: CapabilityDescriptor,
    visibility: DiscoveryVisibility,
) -> Iterable[str]:
    yield f"### `{capability.id}`"
    yield ""
    if capability.description:
        yield capability.description
        yield ""

    safety = _safety(capability, visibility)
    if safety is not None:
        yield f"- Safety: {safety}"
    if capability.effects:
        yield f"- Effects: {', '.join(capability.effects)}"
    if capability.scopes:
        yield f"- Requires scopes: {', '.join(capability.scopes)}"
    if capability.transports:
        yield f"- Reachable through: {', '.join(capability.transports)}"

    if capability.inputs:
        yield "- Inputs:"
        for item in capability.inputs:
            requirement = "required" if item.required else "optional"
            yield f"  - `{item.name}` ({schema_summary(item.schema)}, {requirement})"
    elif visibility.publishes(DiscoveryField.INPUTS):
        yield "- Inputs: none"

    if capability.exposures:
        yield "- Exposures:"
        for exposure in capability.exposures:
            yield f"  - {exposure.transport}: `{exposure.name}`"
    yield ""


def _app(app: AppDescriptor, visibility: DiscoveryVisibility) -> Iterable[str]:
    yield f"## Application `{app.name}`"
    yield ""
    for capability in app.capabilities:
        yield from _capability(capability, visibility)


def render_context(snapshot: IntrospectionSnapshot, visibility: DiscoveryVisibility) -> str:
    """Render the filtered snapshot as Markdown, saying what it is and is not."""
    lines = ["# Available capabilities", ""]
    provenance = f"Generated from `{snapshot.format}` version `{snapshot.version}`"
    if snapshot.project:
        provenance = f"{provenance} for project `{snapshot.project}`"
    lines.append(f"{provenance}.")
    lines.append("")
    lines.append(_NOT_AUTHORIZATION)
    lines.append("")

    withheld = sorted(field.value for field in DiscoveryField if not visibility.publishes(field))
    if withheld:
        # A model should be able to tell "not declared" from "not shown", and
        # it cannot infer that from an absent line.
        lines.append(
            "This view is partial. The following was not published and is "
            f"absent rather than empty: {', '.join(withheld)}."
        )
        lines.append("")

    if not snapshot.apps:
        lines.append("No capabilities are visible to you.")
        return "\n".join(lines)

    for app in snapshot.apps:
        lines.extend(_app(app, visibility))
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def run_context(arguments: argparse.Namespace) -> str | None:
    """Render the context, to stdout or to a file."""
    view = resolve_view(arguments)
    document = render_context(view.snapshot, view.visibility)
    if arguments.output is None:
        return document
    write_document(
        arguments.output,
        f"{document}\n".encode(),
        overwrite=arguments.overwrite,
    )
    return None

"""Present one filtered snapshot as plain text.

Human output may evolve; the JSON form is the stable contract. Even so, this
renderer follows two rules that are not cosmetic.

It never invents. Most withheld fields are simply absent from the snapshot and
print as nothing. Risk, confirmation and idempotency are the exception: a
descriptor always carries a value for them, so a withheld one arrives as the
declared default and would read as a fact. The renderer therefore takes the
visibility decision that produced the snapshot and omits what that decision
did not publish, then names the withheld fields once so a reader knows the
view is partial.

It never decorates. `docs/CLI_SPEC.md` requires no ANSI, and a terminal is not
the only consumer of a text stream.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from agnara.introspection import (
    AppDescriptor,
    CapabilityDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    IntrospectionSnapshot,
)

__all__ = ["render_snapshot", "schema_summary"]

_INDENT = "  "


def _line(depth: int, text: str) -> str:
    return f"{_INDENT * depth}{text}"


def schema_summary(schema: str) -> str:
    """Summarize a JSON Schema fragment in one readable phrase.

    Shared with the agent-context renderer, so a reader of either output sees
    an input described the same way.
    """
    try:
        document = json.loads(schema)
    except json.JSONDecodeError:  # pragma: no cover - descriptors validate this
        return "schema"
    if not isinstance(document, dict):
        return "schema"
    declared = document.get("type")
    if isinstance(declared, str):
        return declared
    if isinstance(declared, list):
        return " | ".join(str(item) for item in declared)
    return "schema"


def _capability(
    capability: CapabilityDescriptor,
    depth: int,
    visibility: DiscoveryVisibility,
) -> Iterable[str]:
    yield _line(depth, capability.id)
    if capability.description:
        yield _line(depth + 1, capability.description)

    if visibility.publishes(DiscoveryField.SAFETY):
        safety = [
            f"risk {capability.risk}",
            f"confirmation {capability.confirmation}",
            f"idempotency {capability.idempotency}",
        ]
        yield _line(depth + 1, ", ".join(safety))

    if capability.effects:
        yield _line(depth + 1, f"effects: {', '.join(capability.effects)}")
    if capability.scopes:
        yield _line(depth + 1, f"scopes: {', '.join(capability.scopes)}")

    if capability.inputs:
        yield _line(depth + 1, "inputs:")
        for item in capability.inputs:
            requirement = "required" if item.required else "optional"
            yield _line(depth + 2, f"{item.name}: {schema_summary(item.schema)} ({requirement})")

    if capability.dependencies:
        yield _line(depth + 1, "dependencies:")
        for dependency in capability.dependencies:
            yield _line(depth + 2, f"{dependency.parameter}: {dependency.type.name}")

    if capability.policies:
        yield _line(depth + 1, f"policies: {', '.join(item.kind for item in capability.policies)}")

    if capability.exposures:
        yield _line(depth + 1, "exposures:")
        for exposure in capability.exposures:
            yield _line(depth + 2, f"{exposure.transport}: {exposure.name}")


def _app(app: AppDescriptor, depth: int, visibility: DiscoveryVisibility) -> Iterable[str]:
    transports = ", ".join(app.transports) if app.transports else "none published"
    count = len(app.capabilities)
    noun = "capability" if count == 1 else "capabilities"
    yield _line(depth, f"app {app.name} ({count} {noun})")
    yield _line(depth + 1, f"transports: {transports}")
    if app.providers:
        yield _line(depth + 1, "providers:")
        for item in app.providers:
            requires = ", ".join(required.name for required in item.requires)
            suffix = f" <- {requires}" if requires else ""
            yield _line(depth + 2, f"{item.provides.name}: {item.scope} {item.kind}{suffix}")
    yield ""
    for capability in app.capabilities:
        yield from _capability(capability, depth + 1, visibility)
        yield ""


def render_snapshot(
    snapshot: IntrospectionSnapshot,
    visibility: DiscoveryVisibility,
) -> str:
    """Render a filtered snapshot, or say plainly that nothing is visible.

    An empty result is a legitimate answer, not an error: the viewer may
    discover nothing. Saying so beats printing an empty document that reads
    like a failure.
    """
    header = f"{snapshot.format} {snapshot.version}"
    if snapshot.project:
        header = f"{header} project {snapshot.project}"
    if not snapshot.filtered:
        header = f"{header} (unfiltered)"
    lines = [header]
    withheld = sorted(field.value for field in DiscoveryField if not visibility.publishes(field))
    if withheld:
        lines.append(f"withheld: {', '.join(withheld)}")
    lines.append("")
    if not snapshot.apps:
        lines.append("No capabilities are visible.")
        return "\n".join(lines)
    for app in snapshot.apps:
        lines.extend(_app(app, 0, visibility))
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)

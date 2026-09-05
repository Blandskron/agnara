"""``agnara graph``: the relationships in the same snapshot ``inspect`` reads.

The requirement that shapes this command is negative. A graph built by walking
the DI registry would answer differently from ``agnara inspect`` under the
same visibility decision, and nothing would reveal the difference until it
mattered. So this reads the filtered snapshot and nothing else.

That has a consequence worth stating rather than hiding: when the visibility
decision withholds dependencies or providers, there is no graph to draw. The
command says which relationship source was withheld instead of printing an
empty tree that reads like an application with no dependencies.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping

from agnara.introspection import (
    AppDescriptor,
    DiscoveryField,
    DiscoveryVisibility,
    ProviderDescriptor,
)
from agnara_cli._view import add_view_arguments, resolve_view

__all__ = ["add_graph_parser", "run_graph"]

_INDENT = "  "


def add_graph_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``graph`` and its arguments on the root parser."""
    parser = subparsers.add_parser(
        "graph",
        help="show how capabilities, dependencies and providers relate",
        description=(
            "Draw the relationships in the same filtered introspection snapshot "
            "'agnara inspect' reads. Importing the target executes the module "
            "that defines it."
        ),
    )
    add_view_arguments(parser)
    parser.set_defaults(handler=run_graph)


def _line(depth: int, text: str) -> str:
    return f"{_INDENT * depth}{text}"


def _provider_tree(
    name: str,
    providers: Mapping[str, ProviderDescriptor],
    depth: int,
    seen: tuple[str, ...],
) -> Iterable[str]:
    """Draw one provider and what it requires, refusing to loop forever.

    A cycle cannot reach a compiled plan — `compile_dag` rejects one — but this
    renderer also runs over a snapshot someone else may have assembled, and a
    drawing tool that hangs is worse than one that says what it found.
    """
    provider = providers.get(name)
    if provider is None:
        yield _line(depth, f"{name} (no provider published)")
        return
    yield _line(depth, f"{name} [{provider.scope} {provider.kind}]")
    if name in seen:
        yield _line(depth + 1, "(cycle)")
        return
    for required in provider.requires:
        yield from _provider_tree(required.name, providers, depth + 1, (*seen, name))


def _reachable(app: AppDescriptor, providers: Mapping[str, ProviderDescriptor]) -> set[str]:
    """Provider names any visible capability reaches, directly or through another.

    Transitive, because a provider that only exists to satisfy another provider
    is used. Reporting it as unreferenced would be a false claim about the
    application, which is worse than saying nothing.
    """
    reached: set[str] = set()
    pending = [
        dependency.type.name
        for capability in app.capabilities
        for dependency in capability.dependencies
    ]
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        provider = providers.get(name)
        if provider is not None:
            pending.extend(required.name for required in provider.requires)
    return reached


def _app(app: AppDescriptor, visibility: DiscoveryVisibility) -> Iterable[str]:
    providers = {provider.provides.name: provider for provider in app.providers}
    yield f"app {app.name}"
    for capability in app.capabilities:
        yield _line(1, capability.id)
        if not visibility.publishes(DiscoveryField.DEPENDENCIES):
            continue
        if not capability.dependencies:
            yield _line(2, "(no dependencies)")
            continue
        for dependency in capability.dependencies:
            yield _line(2, f"{dependency.parameter}:")
            yield from _provider_tree(dependency.type.name, providers, 3, ())

    unreachable = sorted(set(providers) - _reachable(app, providers))
    if unreachable:
        yield ""
        yield _line(
            1,
            "providers no visible capability reaches: " + ", ".join(unreachable),
        )


def run_graph(arguments: argparse.Namespace) -> str:
    """Render the relationship view, or say why there is none to render."""
    view = resolve_view(arguments)
    lines = [f"{view.snapshot.format} {view.snapshot.version} relationships"]

    withheld = [
        field.value
        for field in (DiscoveryField.DEPENDENCIES, DiscoveryField.PROVIDERS)
        if not view.visibility.publishes(field)
    ]
    if withheld:
        lines.append(f"withheld relationship sources: {', '.join(withheld)}")
    lines.append("")

    if not view.snapshot.apps:
        lines.append("No capabilities are visible.")
        return "\n".join(lines)

    for app in view.snapshot.apps:
        lines.extend(_app(app, view.visibility))
        lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)

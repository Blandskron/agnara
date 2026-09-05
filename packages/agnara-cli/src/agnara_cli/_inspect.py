"""``agnara inspect``: one snapshot, one visibility decision, two renderings.

`docs/CLI_SPEC.md` requires that the text and ``--json`` modes consume the
same filtered protocol-neutral snapshot. They do, literally: both call the
same builder and the same filter, and differ only in the last step.

Offline inspection is not a bypass. The visibility decision is a command-line
argument, and `--json` output is a document the operator may go on to publish,
so the same fields can be withheld here as anywhere else.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from agnara.introspection import (
    AllCapabilitiesVisible,
    DiscoveryVisibility,
    ExposureDescriptor,
    Hiding,
    IntrospectionSnapshot,
    ScopeVisible,
    VisibilityRule,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara.policy import AnonymousPrincipal, Principal
from agnara_cli._render import render_snapshot
from agnara_cli._target import ResolvedTarget, resolve_target

__all__ = ["add_inspect_parser", "run_inspect"]

#: Named publication postures, so the decision is a word rather than a list of
#: field names an operator has to keep in their head.
_POSTURES = {
    "full": DiscoveryVisibility.unrestricted,
    "agent": DiscoveryVisibility.agent_safe,
    "identity": DiscoveryVisibility.identity_only,
}


def add_inspect_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register ``inspect`` and its arguments on the root parser."""
    parser = subparsers.add_parser(
        "inspect",
        help="show a compiled application's capabilities",
        description=(
            "Import a compiled Agnara application and present its filtered "
            "protocol-neutral introspection snapshot. Importing the target "
            "executes the module that defines it."
        ),
    )
    parser.add_argument(
        "target",
        help="the application to inspect, as 'module:attribute'",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the versioned snapshot as deterministic JSON",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="DIR",
        help="a directory to search for the target module (repeatable)",
    )
    parser.add_argument(
        "--dependencies",
        metavar="ATTRIBUTE",
        help="the DIRegistry in the target module to compile and describe against",
    )
    parser.add_argument(
        "--visibility",
        choices=sorted(_POSTURES),
        default="full",
        help=(
            "which fields to publish: 'full' for local inspection (default), "
            "'agent' for what a caller needs, 'identity' for names only"
        ),
    )
    parser.add_argument(
        "--as-scope",
        action="append",
        default=[],
        metavar="SCOPE",
        help=(
            "inspect as a viewer holding this scope (repeatable). Without any, "
            "every capability is visible regardless of declared scopes."
        ),
    )
    parser.add_argument(
        "--hide",
        action="append",
        default=[],
        metavar="CAPABILITY_ID",
        help="hide this capability from the result (repeatable)",
    )
    parser.set_defaults(handler=run_inspect)


def _rule(scopes: Sequence[str], hidden: Sequence[str]) -> VisibilityRule:
    """Build the viewer rule the flags describe.

    Without ``--as-scope`` the operator is inspecting their own application
    rather than simulating a caller, so every capability is visible. Passing
    any scope switches to the same scope rule every transport applies, which
    is what makes the simulation worth trusting.
    """
    rule: VisibilityRule = ScopeVisible() if scopes else AllCapabilitiesVisible()
    if hidden:
        rule = Hiding(hidden, rule)
    return rule


def _principal(scopes: Sequence[str]) -> Principal:
    if not scopes:
        return AnonymousPrincipal(metadata={"transport": "cli"})
    return Principal("cli-viewer", metadata={"transport": "cli"}, scopes=scopes)


def _snapshot(resolved: ResolvedTarget) -> IntrospectionSnapshot:
    exposures: dict[str, list[ExposureDescriptor]] = {}
    return snapshot(
        [
            describe_app(
                resolved.app,
                resolved.plans,
                exposures=exposures,
                dependencies=resolved.dependencies,
            )
        ]
    )


def run_inspect(arguments: argparse.Namespace) -> str:
    """Resolve, describe, filter and render. Returns the text to print.

    Exposures are absent because no adapter is composed here: the CLI imports
    an application, not a server. A capability therefore shows no transports,
    which is the truth about what this command can see rather than a claim
    that it is unexposed.
    """
    resolved = resolve_target(
        arguments.target,
        search_path=arguments.path,
        dependencies=arguments.dependencies,
    )
    visibility = _POSTURES[arguments.visibility](_rule(arguments.as_scope, arguments.hide))
    filtered = filter_snapshot(
        _snapshot(resolved),
        visibility,
        _principal(arguments.as_scope),
    )
    if arguments.json:
        return json.dumps(filtered.json_data(), indent=2, sort_keys=True)
    return render_snapshot(filtered, visibility)

"""The one way a command gets a filtered snapshot.

`docs/CLI_SPEC.md` requires every introspection command to consume the same
filtered protocol-neutral snapshot. That is enforced here rather than repeated
per command: a command declares that it takes a view, and receives one built
by this module. There is no second path to the same answers, so two commands
cannot disagree under one visibility decision.

The shared arguments live here too, so a command cannot quietly offer a
different set of visibility controls than its neighbours.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass

from agnara.introspection import (
    AllCapabilitiesVisible,
    DiscoveryVisibility,
    Hiding,
    IntrospectionSnapshot,
    ScopeVisible,
    VisibilityRule,
    describe_app,
    filter_snapshot,
    snapshot,
)
from agnara.policy import AnonymousPrincipal, Principal
from agnara_cli._target import ResolvedTarget, resolve_target

__all__ = ["View", "add_view_arguments", "resolve_view"]

#: Named publication postures, so the decision is a word rather than a list of
#: field names an operator has to keep in their head.
POSTURES = {
    "full": DiscoveryVisibility.unrestricted,
    "agent": DiscoveryVisibility.agent_safe,
    "identity": DiscoveryVisibility.identity_only,
}


@dataclass(frozen=True, slots=True)
class View:
    """One filtered snapshot and the decision that produced it.

    Commands need both. The snapshot alone cannot say whether an absent value
    was never declared or was withheld, and a renderer that guessed would
    assert a fact the filter removed.
    """

    snapshot: IntrospectionSnapshot
    visibility: DiscoveryVisibility
    target: ResolvedTarget


def add_view_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the target and visibility arguments every introspection command takes."""
    parser.add_argument(
        "target",
        help="the application to read, as 'module:attribute'",
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
        choices=sorted(POSTURES),
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
            "read as a viewer holding this scope (repeatable). Without any, "
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


def _rule(scopes: Sequence[str], hidden: Sequence[str]) -> VisibilityRule:
    """Build the viewer rule the flags describe.

    Without ``--as-scope`` the operator is reading their own application rather
    than simulating a caller, so every capability is visible. Passing any scope
    switches to the same scope rule every transport applies, which is what
    makes the simulation worth trusting.
    """
    rule: VisibilityRule = ScopeVisible() if scopes else AllCapabilitiesVisible()
    if hidden:
        rule = Hiding(hidden, rule)
    return rule


def _principal(scopes: Sequence[str]) -> Principal:
    if not scopes:
        return AnonymousPrincipal(metadata={"transport": "cli"})
    return Principal("cli-viewer", metadata={"transport": "cli"}, scopes=scopes)


def resolve_view(arguments: argparse.Namespace) -> View:
    """Import the target, describe it once, and filter it once.

    Exposures are absent because the CLI imports an application, not a server:
    no adapter is composed here, so nothing contributes them. A capability
    therefore shows no transports, which is the truth about what these commands
    can see rather than a claim that it is unexposed.
    """
    resolved = resolve_target(
        arguments.target,
        search_path=arguments.path,
        dependencies=arguments.dependencies,
    )
    visibility = POSTURES[arguments.visibility](_rule(arguments.as_scope, arguments.hide))
    described = snapshot(
        [
            describe_app(
                resolved.app,
                resolved.plans,
                dependencies=resolved.dependencies,
            )
        ]
    )
    return View(
        snapshot=filter_snapshot(described, visibility, _principal(arguments.as_scope)),
        visibility=visibility,
        target=resolved,
    )

"""Refuse to start, approve or tag a release unless its preconditions hold.

Four release attempts, ``0.1.0a4`` to ``0.1.0a7``, each burned a version. The
mechanism was the same every time: the annotated tag was the *trigger* of the
release workflow, so it existed before any gate had run, and a gate that
failed afterwards left an immutable tag naming a release that never happened.

ADR 0082 turns that round. A release is a ``workflow_dispatch`` run from
``main``; the tag is created by that run only after every gate has passed and
a human has approved it in the protected ``pypi`` environment. This script is
the part of that contract the workflow cannot express in YAML. It is run at
the start, again before the approval gate, and again after approval, because
each of those moments is a different state of the repository:

* the run was dispatched, not pushed, and from ``refs/heads/main``;
* the checked-out commit is the current HEAD of ``main`` on the remote -- a
  release cut from a ``main`` that moved while the gates ran is a different
  release;
* the requested version is a publishable v0.x version and no tag ``v<version>``
  exists yet, anywhere;
* the environment that holds the human gate really has one: required
  reviewers, and a deployment branch policy that keeps every other branch out.
  Without the reviewers the "approval" is automatic, and automatic approval
  is what the whole design exists to remove.

Usage::

    python scripts/check_release_preconditions.py --version 0.1.0a8 \\
        --require-protected-environment pypi

Standard library only. Diagnostics name commits, refs, versions and rule
types; they never echo the token, a URL or anything read from the API other
than rule types and counts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

#: PEP 440 restricted to what ADR 0021 permits during v0.x.
VERSION_PATTERN = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:(?:a|b|rc)\d+)?$")

RELEASE_EVENT = "workflow_dispatch"
RELEASE_BRANCH_REF = "refs/heads/main"
NETWORK_TIMEOUT = 30

GitRunner = Callable[..., str]
JsonFetcher = Callable[[str], dict[str, Any] | None]


class Refusal(Exception):
    """The preconditions could not even be evaluated."""


@dataclass(frozen=True, slots=True)
class Context:
    """What GitHub Actions tells a job about the run it is part of."""

    event_name: str | None
    ref: str | None
    sha: str | None
    repository: str | None
    api_url: str
    token: str | None

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Context:
        return cls(
            event_name=environ.get("GITHUB_EVENT_NAME"),
            ref=environ.get("GITHUB_REF"),
            sha=environ.get("GITHUB_SHA"),
            repository=environ.get("GITHUB_REPOSITORY"),
            api_url=environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
            token=environ.get("GITHUB_TOKEN"),
        )


# ---------------------------------------------------------------------------
# Git and API access, injectable so the tests need neither GitHub nor a network
# ---------------------------------------------------------------------------


def make_git(workspace: Path) -> GitRunner:
    def git(*arguments: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=True,
            )
        except OSError as exc:
            raise Refusal(f"cannot run git: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            raise Refusal(f"git {arguments[0]} failed with exit code {exc.returncode}") from exc
        return completed.stdout.strip()

    return git


def make_fetcher(context: Context) -> JsonFetcher:
    def fetch(url: str) -> dict[str, Any] | None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agnara-release-preconditions",
        }
        if context.token:
            headers["Authorization"] = f"Bearer {context.token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=NETWORK_TIMEOUT) as response:
                document = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise Refusal(f"the GitHub API answered HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise Refusal(f"cannot reach the GitHub API: {type(exc).__name__}") from exc
        return document if isinstance(document, dict) else None

    return fetch


# ---------------------------------------------------------------------------
# The preconditions
# ---------------------------------------------------------------------------


def check_dispatch(context: Context) -> list[str]:
    """Only a manual dispatch from main is a release; a pushed tag is not."""
    problems: list[str] = []
    if context.event_name != RELEASE_EVENT:
        problems.append(
            f"a release must be started by {RELEASE_EVENT}, this run was started by "
            f"{context.event_name or 'an unknown event'}"
        )
    if context.ref != RELEASE_BRANCH_REF:
        problems.append(
            f"a release must be dispatched from {RELEASE_BRANCH_REF}, this run is on "
            f"{context.ref or 'an unknown ref'}"
        )
    return problems


def check_version(version: str) -> list[str]:
    if VERSION_PATTERN.fullmatch(version) is None:
        return [f"{version!r} is not a publishable v0.x release version"]
    return []


def check_head_is_current_main(context: Context, git: GitRunner) -> list[str]:
    """The commit under release is the one on the remote, right now.

    ``GITHUB_SHA`` is fixed when the run is dispatched. If ``main`` gains a
    commit while the gates run, the tag would name a commit that is no longer
    the head of the reviewed history; the release is refused rather than
    tagging the past.
    """
    problems: list[str] = []
    if not context.sha:
        return ["the commit under release is unknown (GITHUB_SHA is not set)"]
    head = git("rev-parse", "HEAD")
    if head != context.sha:
        problems.append(
            f"the checkout is at {head[:12]}, the run was dispatched for {context.sha[:12]}"
        )
    listing = git("ls-remote", "origin", RELEASE_BRANCH_REF)
    remote = listing.split()[0] if listing else ""
    if not remote:
        problems.append(f"origin has no {RELEASE_BRANCH_REF}")
    elif remote != context.sha:
        problems.append(
            f"{RELEASE_BRANCH_REF} on origin is at {remote[:12]}, the run was dispatched "
            f"for {context.sha[:12]}; main moved, dispatch the release again from its head"
        )
    return problems


def check_tag_absent(version: str, git: GitRunner) -> list[str]:
    """No tag may exist for this version before the approved run creates it."""
    tag = f"v{version}"
    problems: list[str] = []
    if git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"):
        problems.append(
            f"{tag} already exists on origin; a tag is created only by the approved release "
            "run, and a version that was tagged is never reused"
        )
    if git("tag", "--list", tag):
        problems.append(f"{tag} already exists in this checkout")
    return problems


def check_environment_protection(
    context: Context, name: str, fetch: JsonFetcher
) -> tuple[list[str], list[str]]:
    """The human gate must be real: reviewers, and only main may deploy.

    An environment with no required reviewers approves every run instantly,
    which would let this workflow tag and publish with nobody having said yes.
    An environment open to every branch could be entered by a run that is not
    a release at all. Both are repository settings this checkout cannot set;
    it can refuse to proceed until they are.
    """
    problems: list[str] = []
    notes: list[str] = []
    if not context.repository:
        return ["the repository is unknown (GITHUB_REPOSITORY is not set)"], notes
    if not context.token:
        return ["GITHUB_TOKEN is required to read the environment protection rules"], notes

    document = fetch(f"{context.api_url}/repos/{context.repository}/environments/{name}")
    if document is None:
        return [f"environment {name!r} does not exist in {context.repository}"], notes

    rules = [rule for rule in document.get("protection_rules") or [] if isinstance(rule, dict)]
    reviewer_rules = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    reviewers = sum(len(rule.get("reviewers") or []) for rule in reviewer_rules)
    if reviewers == 0:
        problems.append(
            f"environment {name!r} has no required reviewers; approval would be automatic, "
            "so the release refuses to proceed"
        )
    else:
        notes.append(f"environment {name!r} requires approval from {reviewers} reviewer(s)")

    policy = document.get("deployment_branch_policy")
    restricted = isinstance(policy, dict) and (
        policy.get("protected_branches") is True or policy.get("custom_branch_policies") is True
    )
    if not restricted:
        problems.append(
            f"environment {name!r} accepts deployments from every branch; restrict it to "
            "protected branches (or to main) so only a release from main can enter it"
        )
    else:
        notes.append(f"environment {name!r} restricts which branches may deploy")
    return problems, notes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(
    version: str,
    *,
    context: Context,
    git: GitRunner,
    fetch: JsonFetcher,
    protected_environment: str | None,
) -> tuple[int, list[str], list[str]]:
    problems = [*check_dispatch(context), *check_version(version)]
    notes: list[str] = []
    if not check_version(version):
        problems.extend(check_head_is_current_main(context, git))
        problems.extend(check_tag_absent(version, git))
    if protected_environment is not None:
        environment_problems, environment_notes = check_environment_protection(
            context, protected_environment, fetch
        )
        problems.extend(environment_problems)
        notes.extend(environment_notes)
    return (1 if problems else 0), problems, notes


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="the release version being dispatched")
    parser.add_argument(
        "--require-protected-environment",
        metavar="NAME",
        default=None,
        help="also require this GitHub environment to hold required reviewers",
    )
    parser.add_argument("--workspace", type=Path, default=ROOT, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)

    context = Context.from_environment(os.environ if environ is None else environ)
    try:
        code, problems, notes = run(
            arguments.version,
            context=context,
            git=make_git(arguments.workspace.resolve()),
            fetch=make_fetcher(context),
            protected_environment=arguments.require_protected_environment,
        )
    except Refusal as exc:
        print(f"::error::release preconditions could not be evaluated: {exc}")
        return 2

    for note in notes:
        print(note)
    for problem in problems:
        print(f"::error::{problem}")
    verdict = "NOT MET" if code else "MET"
    print(f"RELEASE PRECONDITIONS {verdict} for {arguments.version}")
    return code


if __name__ == "__main__":
    sys.exit(main())

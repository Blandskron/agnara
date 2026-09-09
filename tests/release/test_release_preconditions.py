"""`scripts/check_release_preconditions.py` is what stands between a dispatch and a tag.

Every burned version so far had the same shape: an irreversible tag existed
before the gates ran. These tests hold the refusals that make the new order
real, against actual Git repositories with a real `origin`: a run that is not a
dispatch from `main`, a `main` that moved while the gates ran, a version whose
tag already exists anywhere, and an environment whose "approval" would be
automatic because nobody has to give it.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT

VERSION = "9.9.9a1"
REPOSITORY = "Blandskron/agnara"


def _load() -> Any:
    location = WORKSPACE_ROOT / "scripts" / "check_release_preconditions.py"
    spec = importlib.util.spec_from_file_location("agnara_release_preconditions", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load()


# ---------------------------------------------------------------------------
# A real repository with a real origin
# ---------------------------------------------------------------------------


def _git(cwd: Path, *arguments: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "user.name=Release test",
            "-c",
            "user.email=release-test@example.invalid",
            *arguments,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A clone of `main` whose HEAD is also the head of `main` on origin."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "--bare", "--initial-branch=main")

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "--initial-branch=main")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "commit", "--allow-empty", "-m", "reviewed main")
    _git(work, "push", "-u", "origin", "main")
    return work


def _context(checkout: Path, **overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "event_name": tool.RELEASE_EVENT,
        "ref": tool.RELEASE_BRANCH_REF,
        "sha": _git(checkout, "rev-parse", "HEAD"),
        "repository": REPOSITORY,
        "api_url": "https://api.invalid",
        "token": "ghs_test_token_never_printed",
    }
    fields.update(overrides)
    return tool.Context(**fields)


def _protected(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "name": "pypi",
        "protection_rules": [
            {"type": "required_reviewers", "reviewers": [{"type": "User", "reviewer": {}}]}
        ],
        "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
    }
    document.update(overrides)
    return document


def _run(
    checkout: Path,
    context: Any,
    *,
    environment: dict[str, Any] | None = None,
    absent: bool = False,
) -> tuple[int, list[str], list[str]]:
    """Run with a protected environment unless told otherwise (`absent` means 404)."""
    document = None if absent else (environment if environment is not None else _protected())
    return tool.run(
        VERSION,
        context=context,
        git=tool.make_git(checkout),
        fetch=lambda url: document,
        protected_environment="pypi",
    )


# ---------------------------------------------------------------------------
# The happy path exists, so the refusals below mean something
# ---------------------------------------------------------------------------


def test_a_dispatch_from_the_current_head_of_main_for_an_untagged_version_is_accepted(
    checkout: Path,
) -> None:
    code, problems, notes = _run(checkout, _context(checkout))

    assert (code, problems) == (0, [])
    assert any("1 reviewer" in note for note in notes)
    assert any("restricts which branches" in note for note in notes)


# ---------------------------------------------------------------------------
# How the run was started
# ---------------------------------------------------------------------------


def test_a_pushed_tag_is_not_a_release(checkout: Path) -> None:
    """The trigger that burned four versions is refused outright."""
    context = _context(checkout, event_name="push", ref=f"refs/tags/v{VERSION}")

    code, problems, _ = _run(checkout, context)

    assert code == 1
    assert any("must be started by workflow_dispatch" in problem for problem in problems)
    assert any("must be dispatched from refs/heads/main" in problem for problem in problems)


def test_a_dispatch_from_another_branch_is_refused(checkout: Path) -> None:
    code, problems, _ = _run(checkout, _context(checkout, ref="refs/heads/develop"))

    assert code == 1
    assert any("must be dispatched from refs/heads/main" in problem for problem in problems)


@pytest.mark.parametrize("version", ["9.9.9a1.dev0", "v9.9.9a1", "9.9", "0.0.0a1x", ""])
def test_an_unpublishable_version_is_refused(checkout: Path, version: str) -> None:
    code, problems, _ = tool.run(
        version,
        context=_context(checkout),
        git=tool.make_git(checkout),
        fetch=lambda url: _protected(),
        protected_environment=None,
    )

    assert code == 1
    assert any("not a publishable" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The commit under release
# ---------------------------------------------------------------------------


def test_a_main_that_moved_while_the_gates_ran_is_refused(checkout: Path) -> None:
    """`GITHUB_SHA` is fixed at dispatch; the tag must not name a stale head."""
    context = _context(checkout)
    _git(checkout, "commit", "--allow-empty", "-m", "landed after dispatch")
    _git(checkout, "push", "origin", "main")
    _git(checkout, "reset", "--hard", context.sha)

    code, problems, _ = _run(checkout, context)

    assert code == 1
    assert any("main moved" in problem for problem in problems)


def test_a_checkout_that_is_not_the_dispatched_commit_is_refused(checkout: Path) -> None:
    dispatched = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "commit", "--allow-empty", "-m", "local only")

    code, problems, _ = _run(checkout, _context(checkout, sha=dispatched))

    assert code == 1
    assert any("the checkout is at" in problem for problem in problems)


def test_a_missing_dispatch_commit_is_refused(checkout: Path) -> None:
    code, problems, _ = _run(checkout, _context(checkout, sha=None))

    assert code == 1
    assert any("GITHUB_SHA is not set" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The tag must not exist yet, anywhere
# ---------------------------------------------------------------------------


def test_a_version_already_tagged_on_origin_is_refused(checkout: Path) -> None:
    """A tag that exists is a version that was used, whatever happened after."""
    _git(checkout, "tag", "-a", f"v{VERSION}", "-m", "earlier attempt")
    _git(checkout, "push", "origin", f"v{VERSION}")
    _git(checkout, "tag", "-d", f"v{VERSION}")

    code, problems, _ = _run(checkout, _context(checkout))

    assert code == 1
    assert any("already exists on origin" in problem for problem in problems)


def test_a_version_tagged_only_locally_is_refused(checkout: Path) -> None:
    _git(checkout, "tag", f"v{VERSION}")

    code, problems, _ = _run(checkout, _context(checkout))

    assert code == 1
    assert any("already exists in this checkout" in problem for problem in problems)


# ---------------------------------------------------------------------------
# The human gate must be real
# ---------------------------------------------------------------------------


def test_an_environment_without_required_reviewers_is_refused(checkout: Path) -> None:
    """Automatic approval is exactly what the design exists to remove."""
    code, problems, _ = _run(
        checkout, _context(checkout), environment=_protected(protection_rules=[])
    )

    assert code == 1
    assert any("no required reviewers" in problem for problem in problems)


def test_an_environment_open_to_every_branch_is_refused(checkout: Path) -> None:
    code, problems, _ = _run(
        checkout, _context(checkout), environment=_protected(deployment_branch_policy=None)
    )

    assert code == 1
    assert any("accepts deployments from every branch" in problem for problem in problems)


def test_a_missing_environment_is_refused(checkout: Path) -> None:
    code, problems, _ = _run(checkout, _context(checkout), absent=True)

    assert code == 1
    assert any("does not exist" in problem for problem in problems)


def test_the_environment_cannot_be_checked_without_a_token(checkout: Path) -> None:
    code, problems, _ = _run(checkout, _context(checkout, token=None))

    assert code == 1
    assert any("GITHUB_TOKEN is required" in problem for problem in problems)


def test_the_environment_check_can_be_skipped_only_explicitly(checkout: Path) -> None:
    """Without the flag the environment is not consulted, so a later job can
    re-run the git preconditions alone; with it, an unprotected environment
    fails even when everything else holds."""
    code, problems, _ = tool.run(
        VERSION,
        context=_context(checkout),
        git=tool.make_git(checkout),
        fetch=lambda url: _protected(protection_rules=[]),
        protected_environment=None,
    )

    assert (code, problems) == (0, [])


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def _environ(checkout: Path, **overrides: str) -> dict[str, str]:
    environ = {
        "GITHUB_EVENT_NAME": tool.RELEASE_EVENT,
        "GITHUB_REF": tool.RELEASE_BRANCH_REF,
        "GITHUB_SHA": _git(checkout, "rev-parse", "HEAD"),
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_API_URL": "https://api.invalid",
        "GITHUB_TOKEN": "ghs_test_token_never_printed",
    }
    environ.update(overrides)
    return environ


def test_the_command_reports_a_met_verdict(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tool, "make_fetcher", lambda context: lambda url: _protected())

    code = tool.main(
        [
            "--version",
            VERSION,
            "--require-protected-environment",
            "pypi",
            "--workspace",
            str(checkout),
        ],
        environ=_environ(checkout),
    )
    captured = capsys.readouterr()

    assert code == 0
    assert f"RELEASE PRECONDITIONS MET for {VERSION}" in captured.out
    assert "::error::" not in captured.out


def test_the_command_annotates_each_unmet_precondition(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tool, "make_fetcher", lambda context: lambda url: _protected())
    _git(checkout, "tag", f"v{VERSION}")

    code = tool.main(
        ["--version", VERSION, "--workspace", str(checkout)],
        environ=_environ(checkout, GITHUB_EVENT_NAME="push"),
    )
    captured = capsys.readouterr()

    assert code == 1
    assert captured.out.count("::error::") == 2
    assert f"RELEASE PRECONDITIONS NOT MET for {VERSION}" in captured.out


def test_the_command_never_prints_the_token(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(url: str) -> None:
        raise tool.Refusal("the GitHub API answered HTTP 500")

    monkeypatch.setattr(tool, "make_fetcher", lambda context: refuse)

    code = tool.main(
        [
            "--version",
            VERSION,
            "--require-protected-environment",
            "pypi",
            "--workspace",
            str(checkout),
        ],
        environ=_environ(checkout),
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "ghs_test_token_never_printed" not in captured.out + captured.err
    assert "could not be evaluated" in captured.out


def test_the_api_fetcher_sends_the_token_only_as_a_bearer_header(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"name": "pypi"}'

    def urlopen(request: Any, timeout: float) -> _Response:
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        return _Response()

    monkeypatch.setattr(tool.urllib.request, "urlopen", urlopen)
    fetch = tool.make_fetcher(_context(checkout))

    assert fetch("https://api.invalid/repos/x/y/environments/pypi") == {"name": "pypi"}
    assert seen["headers"]["Authorization"] == "Bearer ghs_test_token_never_printed"
    assert "ghs_test_token_never_printed" not in seen["url"]


# ---------------------------------------------------------------------------
# After publication: the verified release is about to be tagged
# ---------------------------------------------------------------------------


def _run_after_publication(checkout: Path, context: Any) -> tuple[int, list[str], list[str]]:
    return tool.run(
        VERSION,
        context=context,
        git=tool.make_git(checkout),
        fetch=lambda url: None,
        protected_environment=None,
        after_publication=True,
    )


def test_a_verified_release_is_tagged_even_if_main_moved_meanwhile(checkout: Path) -> None:
    """PyPI already holds what the dispatched commit built; that commit gets the tag."""
    context = _context(checkout)
    _git(checkout, "commit", "--allow-empty", "-m", "landed during publication")
    _git(checkout, "push", "origin", "main")
    _git(checkout, "reset", "--hard", context.sha)

    assert _run_after_publication(checkout, context) == (0, [], [])


def test_after_publication_still_refuses_a_checkout_that_is_not_the_dispatched_commit(
    checkout: Path,
) -> None:
    dispatched = _git(checkout, "rev-parse", "HEAD")
    _git(checkout, "commit", "--allow-empty", "-m", "local only")

    code, problems, _ = _run_after_publication(checkout, _context(checkout, sha=dispatched))

    assert code == 1
    assert any("the checkout is at" in problem for problem in problems)


def test_after_publication_still_refuses_an_existing_tag(checkout: Path) -> None:
    _git(checkout, "tag", "-a", f"v{VERSION}", "-m", "earlier attempt")
    _git(checkout, "push", "origin", f"v{VERSION}")

    code, problems, _ = _run_after_publication(checkout, _context(checkout))

    assert code == 1
    assert any("already exists on origin" in problem for problem in problems)


def test_after_publication_still_refuses_a_run_that_is_not_a_dispatch_from_main(
    checkout: Path,
) -> None:
    code, problems, _ = _run_after_publication(checkout, _context(checkout, event_name="push"))

    assert code == 1
    assert any("must be started by workflow_dispatch" in problem for problem in problems)


def test_the_command_accepts_the_after_publication_flag(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    context = _context(checkout)
    _git(checkout, "commit", "--allow-empty", "-m", "landed during publication")
    _git(checkout, "push", "origin", "main")
    _git(checkout, "reset", "--hard", context.sha)

    code = tool.main(
        ["--version", VERSION, "--after-publication", "--workspace", str(checkout)],
        environ=_environ(checkout),
    )

    assert code == 0
    assert f"RELEASE PRECONDITIONS MET for {VERSION}" in capsys.readouterr().out

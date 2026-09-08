"""The synchronized version transition is complete, atomic, and checkable."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT


def _load_tool() -> Any:
    location = WORKSPACE_ROOT / "scripts" / "set_workspace_version.py"
    spec = importlib.util.spec_from_file_location("agnara_workspace_version", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _workspace(tmp_path: Path, *, versions: dict[str, str] | None = None) -> Path:
    selected = versions or dict.fromkeys(DISTRIBUTIONS, "0.1.0a3")
    for name in DISTRIBUTIONS:
        dependencies = "" if name == "agnara" else '\ndependencies = ["agnara"]'
        package = tmp_path / "packages" / name
        package.mkdir(parents=True)
        (package / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\nversion = "{selected[name]}"{dependencies}\n',
            encoding="utf-8",
        )
    status = tmp_path / "docs" / "releases"
    status.mkdir(parents=True)
    (status / "release-status.json").write_text(
        json.dumps({"current_target": "0.1.0a4"}), encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text("old lock\n", encoding="utf-8")
    return tmp_path


def _successful_uv(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["uv", "lock"], 0, "", "")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("development", "0.1.0a4.dev0"), ("release", "0.1.0a4")],
)
def test_plan_sets_every_version_and_exact_core_pin(
    tmp_path: Path, mode: str, expected: str
) -> None:
    workspace = _workspace(tmp_path)

    plan = tool.plan_transition(workspace, mode, "0.1.0a4")

    assert plan.version == expected
    assert len(plan.files) == len(DISTRIBUTIONS)
    for _path, text in plan.files:
        project = tomllib.loads(text)["project"]
        assert project["version"] == expected
        if project["name"] != "agnara":
            assert project["dependencies"] == [f"agnara=={expected}"]


def test_a_partial_workspace_is_refused_before_any_write(tmp_path: Path) -> None:
    versions = dict.fromkeys(DISTRIBUTIONS, "0.1.0a3")
    versions["agnara-http"] = "0.1.0a4.dev0"
    workspace = _workspace(tmp_path, versions=versions)
    before = {path: path.read_bytes() for path in workspace.glob("packages/*/pyproject.toml")}

    with pytest.raises(tool.TransitionError, match="partially versioned"):
        tool.plan_transition(workspace, "development", "0.1.0a4")

    assert {path: path.read_bytes() for path in before} == before


def test_partially_migrated_core_pins_are_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = workspace / "packages" / "agnara-http" / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"agnara"', '"agnara==0.1.0a3"'),
        encoding="utf-8",
    )

    with pytest.raises(tool.TransitionError, match="partially synchronized"):
        tool.plan_transition(workspace, "development", "0.1.0a4")


@pytest.mark.parametrize("target", ["0.0.0", "0.1.0a4.dev0", "0.1.0a4+local", "banana"])
def test_non_public_targets_are_refused(tmp_path: Path, target: str) -> None:
    workspace = _workspace(tmp_path)

    with pytest.raises(tool.TransitionError, match="public PEP 440"):
        tool.plan_transition(workspace, "development", target)


def test_target_must_match_release_governance(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    with pytest.raises(tool.TransitionError, match="does not match"):
        tool.plan_transition(workspace, "development", "0.1.0a5")


def test_check_only_never_writes_and_checks_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    plan = tool.plan_transition(workspace, "development", "0.1.0a4")
    for path, text in plan.files:
        path.write_text(text, encoding="utf-8")
    before = {path: path.read_bytes() for path, _ in plan.files}
    calls: list[tuple[str, ...]] = []

    def uv(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        return _successful_uv()

    monkeypatch.setattr(tool, "_run_uv", uv)

    checked = tool.execute(plan, workspace, check=True)

    assert calls == [("--check",)]
    assert set(checked) == {*before, workspace / "uv.lock"}
    assert {path: path.read_bytes() for path in before} == before


def test_successful_transition_writes_every_package_and_refreshes_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _workspace(tmp_path)
    plan = tool.plan_transition(workspace, "development", "0.1.0a4")
    calls: list[tuple[str, ...]] = []

    def uv(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        (workspace / "uv.lock").write_text("new lock\n", encoding="utf-8")
        return _successful_uv()

    monkeypatch.setattr(tool, "_run_uv", uv)

    changed = tool.execute(plan, workspace, check=False)

    assert calls == [()]
    assert set(changed) == {*(path for path, _ in plan.files), workspace / "uv.lock"}
    assert (workspace / "uv.lock").read_text(encoding="utf-8") == "new lock\n"
    for path, expected in plan.files:
        assert path.read_text(encoding="utf-8") == expected


def test_lock_failure_restores_every_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    plan = tool.plan_transition(workspace, "development", "0.1.0a4")
    paths = [path for path, _ in plan.files]
    before = {path: path.read_bytes() for path in [*paths, workspace / "uv.lock"]}

    def failed_uv(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        (workspace / "uv.lock").write_text("broken lock\n", encoding="utf-8")
        return subprocess.CompletedProcess([], 1, "", "resolution failed")

    monkeypatch.setattr(tool, "_run_uv", failed_uv)

    with pytest.raises(tool.TransitionError, match="resolution failed"):
        tool.execute(plan, workspace, check=False)

    assert {path: path.read_bytes() for path in before} == before


def test_repository_is_in_a_synchronized_state_for_the_current_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workspace must sit in one of the two states the tool can produce.

    Which one is a property of the branch, not of correctness: ``develop`` carries
    the development version and a release branch carries the cut one. Asserting only
    the development state would fail every release branch and every release pull
    request, which is when a desynchronized workspace matters most. The target is
    read from ``release-status.json`` so that this check follows the release the
    repository is actually working towards.
    """
    status = WORKSPACE_ROOT / "docs" / "releases" / "release-status.json"
    target = json.loads(status.read_text(encoding="utf-8"))["current_target"]
    monkeypatch.setattr(tool, "_run_uv", lambda *args, **kwargs: _successful_uv())

    refused: dict[str, str] = {}
    for mode in ("development", "release"):
        plan = tool.plan_transition(WORKSPACE_ROOT, mode, target)
        try:
            tool.execute(plan, WORKSPACE_ROOT, check=True)
        except tool.TransitionError as error:
            refused[mode] = str(error)

    # The two states differ in every version string, so at most one can match.
    assert len(refused) < 2, (
        f"the workspace matches neither synchronized state for {target}:\n"
        + "\n".join(f"  {mode}: {reason}" for mode, reason in refused.items())
    )

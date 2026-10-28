"""Routine action updates follow integration without absorbing publication review."""

import yaml

from tests.architecture.boundaries import WORKSPACE_ROOT


def test_action_updates_target_develop_and_keep_publisher_review_separate() -> None:
    configuration = yaml.safe_load(
        (WORKSPACE_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    )
    assert configuration["version"] == 2
    updates = configuration["updates"]
    assert len(updates) == 1
    actions = updates[0]
    assert actions["package-ecosystem"] == "github-actions"
    assert actions["directory"] == "/"
    assert actions["target-branch"] == "develop"
    assert actions["schedule"]["interval"] == "weekly"
    assert set(actions["labels"]) == {"dependencies", "supply-chain"}
    assert actions["groups"]["actions"]["patterns"] == ["*"]
    assert actions["groups"]["actions"]["exclude-patterns"] == ["pypa/gh-action-pypi-publish"]

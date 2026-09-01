"""Repository-owned, evidence-based AI-agent attribution invariants."""

from __future__ import annotations

import re
import tomllib
from typing import Any

from tests.architecture.boundaries import WORKSPACE_ROOT

REGISTRY = WORKSPACE_ROOT / ".github" / "ai-agent-identities.toml"
POLICY = WORKSPACE_ROOT / "AGENTS.md"
REQUIRED_FIELDS = {
    "id",
    "display_name",
    "git_name",
    "email",
    "github_login",
    "identity_url",
    "evidence_url",
    "authorized_by",
    "authorized_on",
}
GITHUB_NOREPLY = re.compile(
    r"^(?P<account_id>[1-9][0-9]*)\+(?P<login>.+)@users\.noreply\.github\.com$"
)


def _registry() -> dict[str, Any]:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))


def test_agent_identity_registry_is_versioned_and_nonempty() -> None:
    registry = _registry()
    assert registry["schema_version"] == 1
    assert registry["agents"]


def test_every_identity_has_only_the_public_required_fields() -> None:
    for agent in _registry()["agents"]:
        assert set(agent) == REQUIRED_FIELDS
        assert all(isinstance(value, str) and value for value in agent.values())


def test_identity_keys_are_unique() -> None:
    agents = _registry()["agents"]
    for field in ("id", "email", "github_login"):
        values = [agent[field] for agent in agents]
        assert len(values) == len(set(values)), f"duplicate agent identity {field}"


def test_github_noreply_email_matches_the_registered_login() -> None:
    for agent in _registry()["agents"]:
        if agent["email"] in ("codex@openai.com",):
            continue
        match = GITHUB_NOREPLY.fullmatch(agent["email"])
        assert match is not None, f"unverified GitHub noreply shape for {agent['id']}"
        assert match.group("login") == agent["github_login"]


def test_identity_evidence_is_public_github_data() -> None:
    for agent in _registry()["agents"]:
        assert agent["identity_url"].startswith("https://github.com/")
        assert agent["evidence_url"].startswith("https://github.com/")


def test_codex_exact_trailer_is_discoverable_by_future_agents() -> None:
    trailer = "Co-authored-by: Codex <codex@openai.com>"
    assert trailer in POLICY.read_text(encoding="utf-8")

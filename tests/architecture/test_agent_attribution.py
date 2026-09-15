"""Repository-owned, evidence-based AI-agent attribution invariants."""

from __future__ import annotations

import json
import re
import tomllib
from typing import Any

from tests.architecture.boundaries import WORKSPACE_ROOT

REGISTRY = WORKSPACE_ROOT / ".github" / "ai-agent-identities.toml"
POLICY = WORKSPACE_ROOT / "AGENTS.md"
WORKFLOW = WORKSPACE_ROOT / "GIT_WORKFLOW.md"
TEMPLATE = WORKSPACE_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
RULESETS = (
    WORKSPACE_ROOT / ".github" / "rulesets" / "protect-develop.json",
    WORKSPACE_ROOT / ".github" / "rulesets" / "protect-main.json",
)
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
#: Vendor addresses whose shape a GitHub noreply pattern cannot describe.
#: Each is the published trailer address named in AGENTS.md for that agent,
#: not a convenience exemption: an unlisted address must still be a GitHub
#: noreply matching its registered login.
VENDOR_ADDRESSES = frozenset({"codex@openai.com", "noreply@anthropic.com"})
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
        if agent["email"] in VENDOR_ADDRESSES:
            continue
        match = GITHUB_NOREPLY.fullmatch(agent["email"])
        assert match is not None, f"unverified GitHub noreply shape for {agent['id']}"
        assert match.group("login") == agent["github_login"]


def test_identity_evidence_is_public_github_data() -> None:
    for agent in _registry()["agents"]:
        assert agent["identity_url"].startswith("https://github.com/")
        assert agent["evidence_url"].startswith("https://github.com/")


def test_vendor_addresses_are_all_registered() -> None:
    """An exemption is dead weight unless a registered identity uses it."""
    registered = {agent["email"] for agent in _registry()["agents"]}
    assert registered >= VENDOR_ADDRESSES


def test_exact_primary_author_identities_are_discoverable_by_future_agents() -> None:
    policy = POLICY.read_text(encoding="utf-8")
    for identity in (
        "Codex <codex@openai.com>",
        "Claude <noreply@anthropic.com>",
        "gemini-cli <218195315+gemini-cli@users.noreply.github.com>",
    ):
        assert identity in policy
    assert "Blandskron como `Author`" in policy
    assert "Co-authored-by` para trabajo escrito" in policy


def test_active_workflow_requires_human_review_and_no_agent_merge() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "ADR 0092 governs current work" in workflow
    assert "leaves it unmerged." in workflow
    assert "Only Blandskron merges an agent-authored PR" in workflow
    assert "Reviewer requested: Blandskron" in template
    assert "Formal GitHub review completed by Blandskron" in template


def test_versioned_branch_rulesets_require_fresh_human_approval() -> None:
    for path in RULESETS:
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        pull_request = next(rule for rule in ruleset["rules"] if rule["type"] == "pull_request")
        parameters = pull_request["parameters"]
        assert parameters["required_approving_review_count"] == 1
        assert parameters["dismiss_stale_reviews_on_push"] is True
        assert parameters["require_last_push_approval"] is True

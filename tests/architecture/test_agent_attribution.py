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


def test_versioned_branch_rulesets_enforce_everything_that_needs_no_second_person() -> None:
    """Approval is `0` on purpose, and everything a lone maintainer *can* enforce is on.

    This asserted `required_approving_review_count == 1` and was wrong about its
    own repository. GitHub does not let a pull request author approve their own
    pull request, so with one human maintainer that parameter cannot make review
    stricter -- it can only be satisfied by some other account approving the
    maintainer's own work, which manufactures exactly the review trail ADR 0092
    exists to keep honest. `docs/releases/1.0-release-rehearsal.md` section 7
    reached that conclusion; the definitions now follow it.

    So the assertion moved to what the platform can actually guarantee without a
    second person. `dismiss_stale_reviews_on_push` and `require_last_push_approval`
    stay pinned `True` even though they gate nothing at zero approvals: they are
    what makes adding a reviewer a one-line change instead of a redesign.
    """
    for path in RULESETS:
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        assert ruleset["enforcement"] == "active", path.name
        assert ruleset["bypass_actors"] == [], f"{path.name} must let nobody past the rules"

        rules = {rule["type"]: rule.get("parameters") or {} for rule in ruleset["rules"]}
        assert "deletion" in rules and "non_fast_forward" in rules, path.name

        pull_request = rules["pull_request"]
        assert pull_request["required_approving_review_count"] == 0, path.name
        assert pull_request["required_review_thread_resolution"] is True, path.name
        assert pull_request["dismiss_stale_reviews_on_push"] is True, path.name
        assert pull_request["require_last_push_approval"] is True, path.name

        checks = rules["required_status_checks"]
        assert checks["strict_required_status_checks_policy"] is True, (
            f"{path.name}: a branch merged stale can break its base with green CI; "
            "this is the control a lone maintainer can actually enforce"
        )
        assert [context["context"] for context in checks["required_status_checks"]] == ["CI"], (
            path.name
        )


def test_the_governance_documents_do_not_overstate_what_is_enforced() -> None:
    """The ruleset and the documents describing it must not disagree.

    They did. The definitions said one approval was required, `GIT_WORKFLOW.md`
    and `.github/rulesets/README.md` both repeated that claim, and
    `docs/releases/1.0-release-rehearsal.md` section 7 argued the opposite and
    noted the two "must stop disagreeing". A governance document that overstates
    its own enforcement is worse than one that admits the gap, because a reader
    stops checking.

    This pins the direction of the claim rather than its wording: no document
    may say a review count of one is required while the definitions say zero.
    """
    counts = set()
    for path in RULESETS:
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        counts.add(
            next(
                rule["parameters"]["required_approving_review_count"]
                for rule in ruleset["rules"]
                if rule["type"] == "pull_request"
            )
        )
    assert len(counts) == 1, "the two branch definitions disagree with each other"
    (count,) = counts

    readme = (WORKSPACE_ROOT / ".github" / "rulesets" / "README.md").read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for name, text in (("rulesets/README.md", readme), ("GIT_WORKFLOW.md", workflow)):
        states_zero = "`required_approving_review_count` is `0`" in text
        calls_it_a_commitment = "commitment, not an enforced control" in text

        assert states_zero == (count == 0), (
            f"{name} states the review count is 0: {states_zero}, but the definitions set {count}"
        )
        assert calls_it_a_commitment == (count == 0), (
            f"{name} presents review as a commitment rather than an enforced control: "
            f"{calls_it_a_commitment}, but the definitions set {count} required "
            "approvals -- at 1 the platform does enforce it, and the document must "
            "stop calling it unenforced"
        )

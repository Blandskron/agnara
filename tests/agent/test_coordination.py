# Load script as module
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location("agent", "scripts/agent.py")
assert spec is not None
assert spec.loader is not None
agent = importlib.util.module_from_spec(spec)
sys.modules["agent"] = agent
spec.loader.exec_module(agent)


def mock_issue(
    number: int, write_scopes: list[str], comments: list[dict[str, Any]]
) -> dict[str, Any]:
    scopes_json = json.dumps(write_scopes)
    body = (
        f"```json\n# agnara-work\n"
        f'{{"id": "E{number}", "type": "feature", "priority": "P1", '
        f'"scope": {{"write": {scopes_json} }} }}\n```'
    )
    return {
        "number": number,
        "title": f"Test Issue {number}",
        "state": "OPEN",
        "body": body,
        "comments": comments,
    }


def test_parse_metadata():
    issue = mock_issue(42, ["packages/core/**"], [])
    meta = agent.parse_metadata(issue["body"])
    assert meta is not None
    assert meta.scope.write == ["packages/core/**"]


def test_scope_collision():
    active = ["packages/core/registry/**"]
    assert agent.check_scope_collision(["packages/core/**"], active)
    assert not agent.check_scope_collision(["packages/mcp/**"], active)


@patch("agent.get_issues")
def test_next_avoids_collisions(mock_get_issues, capsys):
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    claim_str = f'{agent.CLAIM_PREFIX}{{"worker": "worker-1", "expires": "{expires}"}} -->'

    i1 = mock_issue(1, ["packages/core/**"], [{"body": claim_str, "databaseId": 1}])
    i2 = mock_issue(2, ["packages/core/registry/**"], [])
    i3 = mock_issue(3, ["packages/mcp/**"], [])

    # We must patch subprocess in agent to avoid real gh calls if we didn't patch get_issues,
    # but we patched get_issues directly.
    # Wait, get_issues returns Issue objects, not dicts.
    # Let's recreate Issue objects.
    mock_get_issues.return_value = [
        agent.Issue(
            number=1,
            title="1",
            state="OPEN",
            body="",
            comments=[],
            metadata=agent.parse_metadata(i1["body"]),
            lease=agent.parse_lease(i1["comments"]),
        ),
        agent.Issue(
            number=2,
            title="2",
            state="OPEN",
            body="",
            comments=[],
            metadata=agent.parse_metadata(i2["body"]),
            lease=None,
        ),
        agent.Issue(
            number=3,
            title="3",
            state="OPEN",
            body="",
            comments=[],
            metadata=agent.parse_metadata(i3["body"]),
            lease=None,
        ),
    ]

    args = MagicMock()
    args.json = True
    agent.cmd_next(args)

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    # i2 collides with i1 (which is active). i3 is safe.
    assert result["issue"] == 3


@patch("agent.get_issues")
@patch("agent.subprocess.run")
def test_claim_race_condition(mock_run, mock_get_issues, capsys):
    # Simulate a race condition where we post a comment, but another agent posted right before us.
    args = MagicMock()
    args.issue = 42
    args.worker = "my-worker"

    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    # Another agent claimed it first
    claim_str1 = f'{agent.CLAIM_PREFIX}{{"worker": "other-worker", "expires": "{expires}"}} -->'
    # We claimed it second
    claim_str2 = f'{agent.CLAIM_PREFIX}{{"worker": "my-worker", "expires": "{expires}"}} -->'

    comments = [{"body": claim_str1, "databaseId": 1}, {"body": claim_str2, "databaseId": 2}]

    lease = agent.parse_lease(comments)
    assert lease is not None
    assert lease.worker == "other-worker"


@patch("agent.get_issues")
@patch("agent.subprocess.run")
def test_claim_success(mock_run, mock_get_issues, capsys):
    args = MagicMock()
    args.issue = 42
    args.worker = "my-worker"

    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    claim_str = f'{agent.CLAIM_PREFIX}{{"worker": "my-worker", "expires": "{expires}"}} -->'

    i1 = mock_issue(42, ["packages/core/**"], [{"body": claim_str, "databaseId": 1}])
    mock_get_issues.return_value = [
        agent.Issue(
            number=42,
            title="42",
            state="OPEN",
            body="",
            comments=[],
            metadata=None,
            lease=agent.parse_lease(i1["comments"]),
        )
    ]

    agent.cmd_claim(args)
    captured = capsys.readouterr()
    assert "Successfully claimed #42" in captured.out

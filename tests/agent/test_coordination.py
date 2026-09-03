# Load script as module
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
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


def cp1252_stream() -> io.TextIOWrapper:
    """A stream with the default Windows codec, which rejects most Unicode."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


def written(stream: io.TextIOWrapper) -> str:
    stream.flush()
    raw = stream.buffer
    assert isinstance(raw, io.BytesIO)
    return raw.getvalue().decode("cp1252")


def ready_issue(number: int, title: str) -> Any:
    body = mock_issue(number, ["packages/agnara-http/**"], [])["body"]
    return agent.Issue(
        number=number,
        title=title,
        state="OPEN",
        body="",
        comments=[],
        metadata=agent.parse_metadata(body),
        lease=None,
    )


def test_emit_leaves_encodable_text_unchanged() -> None:
    stream = cp1252_stream()
    agent.emit("Ready work    3", stream=stream)
    assert written(stream) == "Ready work    3\n"


def test_emit_replaces_characters_the_stream_codec_cannot_encode() -> None:
    stream = cp1252_stream()
    agent.emit("frame ── label 你", stream=stream)
    output = written(stream)
    assert output.startswith("frame ")
    assert "─" not in output
    assert "你" not in output


def test_encodable_tolerates_a_missing_or_unknown_codec() -> None:
    assert agent.encodable("─", None) == "─"
    assert agent.encodable("─", "not-a-codec") == "─"


def test_status_framing_is_pure_ascii() -> None:
    assert agent.RULE.isascii()
    assert set(agent.RULE) == {"-"}


@patch("agent.get_issues")
def test_status_writes_every_line_to_a_narrow_codec_stream(mock_get_issues: Any) -> None:
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    claim_str = f'{agent.CLAIM_PREFIX}{{"worker": "w─rker", "expires": "{expires}"}} -->'
    issue = ready_issue(7, "titled")
    issue.lease = agent.parse_lease([{"body": claim_str, "databaseId": 1}])
    mock_get_issues.return_value = [issue]

    stream = cp1252_stream()
    with redirect_stdout(stream):
        agent.cmd_status(MagicMock())

    output = written(stream)
    assert "AGNARA DEVELOPMENT SWARM" in output
    assert agent.RULE in output
    assert "Active        1" in output
    assert "#007" in output


@patch("agent.get_issues")
def test_next_survives_a_remote_title_the_console_cannot_encode(mock_get_issues: Any) -> None:
    mock_get_issues.return_value = [ready_issue(9, "add ─ deterministic 你 output")]
    args = MagicMock()
    args.json = False

    stream = cp1252_stream()
    with redirect_stdout(stream):
        agent.cmd_next(args)

    output = written(stream)
    assert output.startswith("#9 - add ")
    assert "─" not in output


@patch("agent.get_issues")
def test_next_json_output_stays_ascii_and_parseable(mock_get_issues: Any) -> None:
    title = "add ─ deterministic 你 output"
    mock_get_issues.return_value = [ready_issue(9, title)]
    args = MagicMock()
    args.json = True

    stream = cp1252_stream()
    with redirect_stdout(stream):
        agent.cmd_next(args)

    output = written(stream)
    assert output.isascii()
    assert json.loads(output) == {"issue": 9, "title": title}

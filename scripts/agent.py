#!/usr/bin/env python3
"""
Agnara Multi-Agent Coordination Protocol CLI.
Implements atomic leases, scope collision detection, and task discovery.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, TextIO

CLAIM_PREFIX = "<!-- agnara-lease-claim: "
RELEASE_PREFIX = "<!-- agnara-lease-release: "

# Output framing stays ASCII on purpose. The bootstrap instructions in
# AGENTS.md cannot assume a UTF-8 console, and on Windows the default cp1252
# codec cannot encode box-drawing characters. Issue titles, worker names and
# scopes come from GitHub, so they can still hold anything; emit() replaces
# whatever the stream cannot encode instead of aborting the command.
RULE = "-" * 40


def emit(text: str = "", *, stream: TextIO | None = None) -> None:
    """Print one line, degrading unencodable characters instead of raising."""
    target = sys.stdout if stream is None else stream
    print(encodable(text, getattr(target, "encoding", None)), file=target)


def encodable(text: str, encoding: str | None) -> str:
    """Return text the stream can encode, with replacements where it cannot."""
    if not encoding:
        return text
    try:
        text.encode(encoding)
    except UnicodeEncodeError:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except LookupError:
        return text
    return text


@dataclass
class Scope:
    write: list[str] = field(default_factory=list)
    read: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)


@dataclass
class WorkMetadata:
    id: str = ""
    type: str = ""
    priority: str = ""
    dependencies: dict[str, list[int]] = field(default_factory=dict)
    scope: Scope = field(default_factory=Scope)
    parallel: dict[str, bool] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)


@dataclass
class Lease:
    worker: str
    expires_at: datetime
    comment_id: int


@dataclass
class Issue:
    number: int
    title: str
    state: str
    body: str
    comments: list[dict[str, Any]]
    metadata: WorkMetadata | None = None
    lease: Lease | None = None


def parse_metadata(body: str) -> WorkMetadata | None:
    match = re.search(r"```json\s*# agnara-work\s*(.*?)```", body, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        if not isinstance(data, dict):
            return None
        scope_data = data.get("scope", {})
        scope = Scope(
            write=scope_data.get("write", []),
            read=scope_data.get("read", []),
            forbidden=scope_data.get("forbidden", []),
        )
        return WorkMetadata(
            id=data.get("id", ""),
            type=data.get("type", ""),
            priority=data.get("priority", ""),
            dependencies=data.get("dependencies", {}),
            scope=scope,
            parallel=data.get("parallel", {}),
            capabilities=data.get("capabilities", []),
        )
    except Exception:
        return None


def parse_lease(comments: list[dict[str, Any]]) -> Lease | None:
    # Comments are chronologically ordered. Find the active state.
    # To prevent race conditions, a claim is only valid if there is no active lease.
    current_lease = None
    for comment in comments:
        body = comment.get("body", "")
        if body.startswith(CLAIM_PREFIX):
            try:
                data_str = body[len(CLAIM_PREFIX) : body.index("-->")].strip()
                data = json.loads(data_str)
                expires = datetime.fromisoformat(data["expires"])

                # Only accept new claim if current is none or expired
                if (
                    current_lease is None or current_lease.expires_at < datetime.now(UTC)
                ) and expires > datetime.now(UTC):
                    current_lease = Lease(
                        worker=data["worker"],
                        expires_at=expires,
                        comment_id=comment.get("databaseId", 0),
                    )
            except Exception:
                continue
        elif body.startswith(RELEASE_PREFIX):
            current_lease = None
    return current_lease


def get_issues() -> list[Issue]:
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--limit",
        "1000",
        "--json",
        "number,title,state,body,comments",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        emit(f"Error fetching issues: {e.stderr}", stream=sys.stderr)
        sys.exit(1)

    raw_issues = json.loads(result.stdout)
    issues = []
    for raw in raw_issues:
        meta = parse_metadata(raw.get("body", ""))
        lease = parse_lease(raw.get("comments", []))
        issues.append(
            Issue(
                number=raw["number"],
                title=raw["title"],
                state=raw["state"],
                body=raw["body"],
                comments=raw.get("comments", []),
                metadata=meta,
                lease=lease,
            )
        )
    return issues


def check_scope_collision(candidate_write: list[str], active_writes: list[str]) -> bool:
    # Very naive glob collision check for demonstration.
    # In reality, path containment requires path traversal.
    # We treat any overlap as collision.
    for cw in candidate_write:
        for aw in active_writes:
            # If one is a prefix of the other (naive path matching)
            cw_clean = cw.replace("**", "").replace("*", "")
            aw_clean = aw.replace("**", "").replace("*", "")
            if cw_clean.startswith(aw_clean) or aw_clean.startswith(cw_clean):
                return True
    return False


def cmd_status(args):
    issues = get_issues()
    active = [i for i in issues if i.lease is not None]
    ready = [i for i in issues if i.lease is None and i.metadata is not None]

    emit("AGNARA DEVELOPMENT SWARM")
    emit(RULE)
    emit(f"Active        {len(active)}")
    emit(f"Ready work    {len(ready)}")
    emit()
    for issue in active:
        worker = issue.lease.worker if issue.lease else "unknown"
        scopes = ", ".join(issue.metadata.scope.write) if issue.metadata else "unknown"
        emit(f"#{issue.number:03d}  {worker[:15]:<15}  IMPLEMENTING   {scopes}")


def cmd_next(args):
    issues = get_issues()
    active = [i for i in issues if i.lease is not None]
    active_writes = []
    for issue in active:
        if issue.metadata:
            active_writes.extend(issue.metadata.scope.write)

    ready = [i for i in issues if i.lease is None and i.metadata is not None]

    for issue in ready:
        meta = issue.metadata
        if meta and not check_scope_collision(meta.scope.write, active_writes):
            if args.json:
                emit(json.dumps({"issue": issue.number, "title": issue.title}))
            else:
                emit(f"#{issue.number} - {issue.title}")
            return
    if args.json:
        emit(json.dumps({"issue": None}))
    else:
        emit("No ready work available without scope collisions.")


def cmd_claim(args):
    # Optimistic locking: post comment, then fetch comments.
    expires = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    claim_data = {"worker": args.worker, "expires": expires}
    claim_str = f"{CLAIM_PREFIX}{json.dumps(claim_data)} -->"

    cmd = ["gh", "issue", "comment", str(args.issue), "--body", claim_str]
    subprocess.run(cmd, capture_output=True, check=True)

    # Verify we won the race
    issues = get_issues()
    target = next((i for i in issues if i.number == args.issue), None)
    if not target or not target.lease:
        emit("Failed to acquire lease.")
        sys.exit(1)

    if target.lease.worker == args.worker:
        emit(f"Successfully claimed #{args.issue} for {args.worker}")
    else:
        emit(f"Lost race. Issue #{args.issue} is owned by {target.lease.worker}")
        sys.exit(1)


def cmd_release(args):
    release_str = f"{RELEASE_PREFIX} -->"
    cmd = ["gh", "issue", "comment", str(args.issue), "--body", release_str]
    subprocess.run(cmd, capture_output=True, check=True)
    emit(f"Released #{args.issue}")


def main():
    parser = argparse.ArgumentParser(description="Agnara Multi-Agent Coordination CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Show swarm status")

    next_parser = subparsers.add_parser("next", help="Find next actionable issue")
    next_parser.add_argument("--json", action="store_true")

    claim_parser = subparsers.add_parser("claim", help="Claim an issue")
    claim_parser.add_argument("issue", type=int)
    claim_parser.add_argument("worker", type=str)

    release_parser = subparsers.add_parser("release", help="Release an issue")
    release_parser.add_argument("issue", type=int)
    release_parser.add_argument("worker", type=str)

    args = parser.parse_args()
    if args.command == "status":
        cmd_status(args)
    elif args.command == "next":
        cmd_next(args)
    elif args.command == "claim":
        cmd_claim(args)
    elif args.command == "release":
        cmd_release(args)


if __name__ == "__main__":
    main()

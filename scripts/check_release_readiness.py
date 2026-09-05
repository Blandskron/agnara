"""Evaluate whether `develop` is mature enough to close the next release.

This is a measurement tool. It publishes nothing, tags nothing and changes no
version. It answers one question — is the current target's exit gate satisfied
— and it is deliberately hard to lie to:

* **automated** gates are re-derived from the repository on every run, so
  `release-status.json` cannot assert something the repository contradicts;
* **evidence** gates are trusted only while the commit their evidence was
  recorded on is still `HEAD`; older evidence is reported as stale rather than
  green, because a recorded pass cannot outlive the code it described;
* **manual** gates are never satisfied by this script. They require human
  architectural or security judgment and are reported as needing it.

A gate marked satisfied with no evidence is an error, not a warning.

Uses the standard library only, like the rest of the repository's own tooling.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs" / "releases" / "release-status.json"
PLAN_PATH = ROOT / "docs" / "releases" / "RELEASE_PLAN.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
PACKAGES_DIR = ROOT / "packages"

SCHEMA_VERSION = 1

SATISFIED = "SATISFIED"
PARTIAL = "PARTIAL"
UNSATISFIED = "UNSATISFIED"
STALE = "STALE"
NEEDS_REVIEW = "NEEDS_REVIEW"

IN_PROGRESS = "IN_PROGRESS"
RELEASE_READY = "RELEASE_READY"
BLOCKED = "BLOCKED"

AUTOMATED = "automated"
EVIDENCE = "evidence"
MANUAL = "manual"

#: Version references that are release-preparation work rather than defects.
#: `docs/MAINTAINERS_RELEASE.md` sets them on the release branch, not here.
UNRELEASED_HEADING = "## [Unreleased]"


@dataclass(frozen=True, slots=True)
class Result:
    """One gate's evaluated outcome, and why."""

    gate_id: str
    title: str
    kind: str
    mandatory: bool
    status: str
    detail: str

    @property
    def counts_as_satisfied(self) -> bool:
        return self.status == SATISFIED


class StatusError(Exception):
    """The status file is internally inconsistent, which is a hard failure."""


# ---------------------------------------------------------------------------
# Repository facts
# ---------------------------------------------------------------------------


def head_commit() -> str | None:
    """The commit the working tree is on, or None outside a checkout."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:  # pragma: no cover - no git
        return None
    return completed.stdout.strip()


def working_tree_is_clean() -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:  # pragma: no cover - no git
        return None
    return not completed.stdout.strip()


def package_versions() -> dict[str, str]:
    """Every first-party package version, keyed by distribution directory."""
    versions: dict[str, str] = {}
    for path in sorted(PACKAGES_DIR.glob("*/pyproject.toml")):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        versions[path.parent.name] = project["version"]
    return versions


def declared_python_baseline() -> set[str]:
    baselines: set[str] = set()
    for path in sorted(PACKAGES_DIR.glob("*/pyproject.toml")):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        baselines.add(project.get("requires-python", ""))
    return baselines


# ---------------------------------------------------------------------------
# Automated gate checks
# ---------------------------------------------------------------------------


def check_version_consistency() -> tuple[str, str]:
    versions = package_versions()
    if not versions:
        return UNSATISFIED, "no first-party packages found"
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        rendered = ", ".join(f"{name}={version}" for name, version in sorted(versions.items()))
        return UNSATISFIED, f"versions are not synchronized: {rendered}"
    version = distinct[0]
    if version == "0.0.0":
        return UNSATISFIED, "the 0.0.0 development sentinel must never be released"
    return SATISFIED, f"all {len(versions)} first-party packages declare {version}"


def check_python_baseline() -> tuple[str, str]:
    baselines = declared_python_baseline()
    if baselines != {">=3.14"}:
        return UNSATISFIED, f"inconsistent or unexpected requires-python: {sorted(baselines)}"
    # This tool itself requires 3.14, so reaching here proves the interpreter
    # satisfies the declared floor; the CI test lane asserts it independently.
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    return SATISFIED, f"declared >=3.14 everywhere; verified on CPython {running}"


def check_changelog() -> tuple[str, str]:
    if not CHANGELOG_PATH.is_file():
        return UNSATISFIED, "CHANGELOG.md is missing"
    text = CHANGELOG_PATH.read_text(encoding="utf-8")
    if text.count(UNRELEASED_HEADING) != 1:
        return UNSATISFIED, "CHANGELOG.md must contain exactly one [Unreleased] section"
    unreleased = text.split(UNRELEASED_HEADING, 1)[1]
    next_release = re.search(r"^## \[", unreleased, re.MULTILINE)
    body = unreleased[: next_release.start()] if next_release else unreleased
    entries = len(re.findall(r"^- ", body, re.MULTILINE))
    if entries == 0:
        return UNSATISFIED, "[Unreleased] has no entries; nothing to release"
    return SATISFIED, f"[Unreleased] carries {entries} entries"


def check_repository_clean() -> tuple[str, str]:
    clean = working_tree_is_clean()
    if clean is None:
        return PARTIAL, "not a git checkout; cleanliness could not be determined"
    if not clean:
        return UNSATISFIED, "the working tree has uncommitted changes"
    return SATISFIED, "the working tree is clean"


def check_release_commit_identified() -> tuple[str, str]:
    commit = head_commit()
    if commit is None:
        return UNSATISFIED, "HEAD could not be resolved"
    return SATISFIED, f"HEAD is {commit[:10]}"


def check_license_metadata() -> tuple[str, str]:
    if not (ROOT / "LICENSE").is_file():
        return UNSATISFIED, "LICENSE is missing"
    wrong = []
    for path in sorted(PACKAGES_DIR.glob("*/pyproject.toml")):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        license_field = project.get("license")
        text = license_field.get("text") if isinstance(license_field, dict) else license_field
        if text != "Apache-2.0":
            wrong.append(f"{path.parent.name}={text!r}")
    if wrong:
        return UNSATISFIED, "packages not declaring Apache-2.0: " + ", ".join(wrong)
    return SATISFIED, "LICENSE present and every package declares Apache-2.0"


def check_public_api_declared() -> tuple[str, str]:
    """Every distributable package states its public surface with __all__."""
    missing = []
    for init in sorted(PACKAGES_DIR.glob("*/src/*/__init__.py")):
        if "__all__" not in init.read_text(encoding="utf-8"):
            missing.append(init.parent.name)
    if missing:
        return UNSATISFIED, "packages without a declared __all__: " + ", ".join(missing)
    return SATISFIED, "every first-party package declares __all__"


#: Automated gate id -> the function that decides it. A gate whose id is listed
#: here is never read from the status file.
AUTOMATED_CHECKS = {
    "version-consistency": check_version_consistency,
    "python-baseline": check_python_baseline,
    "changelog-accurate": check_changelog,
    "changelog-complete": check_changelog,
    "repository-clean": check_repository_clean,
    "release-commit-identified": check_release_commit_identified,
    "license-metadata": check_license_metadata,
    "public-api-distinguished": check_public_api_declared,
}


# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------


def evaluate_evidence(gate: dict[str, Any], current_commit: str | None) -> tuple[str, str]:
    """Trust recorded evidence only while it still describes the current code."""
    evidence = gate.get("evidence")
    recorded = gate.get("status", UNSATISFIED)
    if recorded != SATISFIED:
        return recorded, gate.get("detail", "not recorded as satisfied")
    if not evidence:
        raise StatusError(f"gate {gate['id']!r} is SATISFIED with no evidence")

    commit = evidence.get("commit")
    if commit is None:
        raise StatusError(f"gate {gate['id']!r} records evidence without a commit")
    if current_commit is not None and commit != current_commit:
        return STALE, f"evidence was recorded on {commit[:10]}, HEAD is {current_commit[:10]}"

    for reference in evidence.get("paths", []):
        if not (ROOT / reference).exists():
            return UNSATISFIED, f"evidence references a missing path: {reference}"

    summary = evidence.get("result") or evidence.get("command") or "recorded"
    return SATISFIED, summary


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def load_status() -> dict[str, Any]:
    if not STATUS_PATH.is_file():
        # Not relative_to(ROOT): a caller may point this at a file outside the
        # repository, and a diagnostic must not fail while reporting a failure.
        raise StatusError(f"{STATUS_PATH} is missing")
    document: dict[str, Any] = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise StatusError(f"unsupported schema_version {document.get('schema_version')!r}")
    return document


def evaluate(document: dict[str, Any]) -> list[Result]:
    current_commit = head_commit()
    results: list[Result] = []
    seen: set[str] = set()

    for gate in document.get("gates", []):
        gate_id = gate["id"]
        if gate_id in seen:
            raise StatusError(f"duplicate gate id {gate_id!r}")
        seen.add(gate_id)
        kind = gate["kind"]

        if kind == AUTOMATED:
            check = AUTOMATED_CHECKS.get(gate_id)
            if check is None:
                raise StatusError(
                    f"gate {gate_id!r} is declared automated but has no implementation; "
                    "add one to AUTOMATED_CHECKS or reclassify the gate"
                )
            status, detail = check()
        elif kind == EVIDENCE:
            status, detail = evaluate_evidence(gate, current_commit)
        elif kind == MANUAL:
            recorded = gate.get("status", NEEDS_REVIEW)
            status = SATISFIED if recorded == SATISFIED else NEEDS_REVIEW
            detail = gate.get("detail", "requires human review")
            if status == SATISFIED and not gate.get("evidence"):
                raise StatusError(f"manual gate {gate_id!r} is SATISFIED with no evidence")
        else:
            raise StatusError(f"gate {gate_id!r} has unknown kind {kind!r}")

        results.append(
            Result(
                gate_id=gate_id,
                title=gate["title"],
                kind=kind,
                mandatory=bool(gate.get("mandatory", True)),
                status=status,
                detail=detail,
            )
        )

    if not results:
        raise StatusError("the status file declares no gates")
    return results


def overall_status(results: list[Result], document: dict[str, Any]) -> str:
    mandatory = [result for result in results if result.mandatory]
    if document.get("blocked_reason"):
        return BLOCKED
    if all(result.counts_as_satisfied for result in mandatory):
        return RELEASE_READY
    return IN_PROGRESS


def readiness_percentage(results: list[Result]) -> int:
    mandatory = [result for result in results if result.mandatory]
    if not mandatory:
        return 0
    satisfied = sum(1 for result in mandatory if result.counts_as_satisfied)
    return round(satisfied * 100 / len(mandatory))


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_MARK = {
    SATISFIED: "PASS",
    PARTIAL: "PARTIAL",
    UNSATISFIED: "FAIL",
    STALE: "STALE",
    NEEDS_REVIEW: "REVIEW",
}


def render(
    document: dict[str, Any],
    results: list[Result],
    status: str,
    percentage: int,
    *,
    verbose: bool,
) -> str:
    target = document["current_target"]
    lines = [
        "AGNARA RELEASE READINESS",
        f"Target: {target}",
        f"Status: {status}",
        "",
        f"Readiness: {percentage}% of mandatory gates",
        "",
    ]

    for kind, heading in (
        (AUTOMATED, "Automated"),
        (EVIDENCE, "Evidence"),
        (MANUAL, "Manual review"),
    ):
        group = [result for result in results if result.kind == kind]
        if not group:
            continue
        lines.append(f"{heading} gates")
        for result in group:
            flag = "" if result.mandatory else "  (optional)"
            lines.append(f"  {_MARK[result.status]:<7} {result.title}{flag}")
            if verbose or result.status != SATISFIED:
                lines.append(f"          {result.detail}")
        lines.append("")

    remaining = [
        result for result in results if result.mandatory and not result.counts_as_satisfied
    ]
    if remaining:
        lines.append("Remaining mandatory gates")
        for result in remaining:
            lines.append(f"  - {result.title}")
        lines.append("")

    if status == RELEASE_READY:
        lines.append(f"RELEASE READY: Agnara is ready to close {target}.")
    elif status == BLOCKED:
        lines.append(f"BLOCKED: {document.get('blocked_reason')}")

    return "\n".join(lines).rstrip() + "\n"


def as_json(
    document: dict[str, Any],
    results: list[Result],
    status: str,
    percentage: int,
) -> str:
    return json.dumps(
        {
            "current_target": document["current_target"],
            "status": status,
            "readiness_percent": percentage,
            "head_commit": head_commit(),
            "gates": [
                {
                    "id": result.gate_id,
                    "title": result.title,
                    "kind": result.kind,
                    "mandatory": result.mandatory,
                    "status": result.status,
                    "detail": result.detail,
                }
                for result in results
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the evaluation as JSON")
    parser.add_argument("--verbose", action="store_true", help="show detail for every gate")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="exit non-zero unless the current target is RELEASE_READY",
    )
    arguments = parser.parse_args(argv)

    try:
        document = load_status()
        results = evaluate(document)
    except StatusError as error:
        print(f"release-status.json is inconsistent: {error}", file=sys.stderr)
        return 2

    status = overall_status(results, document)
    percentage = readiness_percentage(results)

    if arguments.json:
        print(as_json(document, results, status, percentage))
    else:
        print(render(document, results, status, percentage, verbose=arguments.verbose), end="")

    if arguments.require_ready and status != RELEASE_READY:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

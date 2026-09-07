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
import ast
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs" / "releases" / "release-status.json"
PLAN_PATH = ROOT / "docs" / "releases" / "RELEASE_PLAN.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
PACKAGES_DIR = ROOT / "packages"
PUBLIC_API_PATH = ROOT / "docs" / "public-api.json"

#: Distribution name -> top-level import package, per ADR 0017.
#:
#: Spelled out rather than discovered so that a package that stops shipping,
#: or a new one that nobody classified, is a diff in this file rather than a
#: silent change in what the public API gate covers.
DISTRIBUTIONS = {
    "agnara": "agnara",
    "agnara-a2a": "agnara_a2a",
    "agnara-cli": "agnara_cli",
    "agnara-events": "agnara_events",
    "agnara-http": "agnara_http",
    "agnara-mcp": "agnara_mcp",
    "agnara-telemetry": "agnara_telemetry",
}

#: Import package -> the source root the manifest may address.
SOURCE_ROOTS = {
    import_name: PACKAGES_DIR / distribution / "src" / import_name
    for distribution, import_name in DISTRIBUTIONS.items()
}

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


def package_core_requirements(core: str = "agnara") -> dict[str, list[str]]:
    """Core requirements declared by every adapter, keyed by distribution."""
    requirements: dict[str, list[str]] = {}
    normalized_core = core.lower().replace("_", "-")
    for path in sorted(PACKAGES_DIR.glob("*/pyproject.toml")):
        project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
        name = project["name"]
        if name == core:
            continue
        selected = []
        for requirement in project.get("dependencies", []):
            match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(.*)$", requirement)
            if match and match[1].lower().replace("_", "-") == normalized_core:
                selected.append(requirement)
        requirements[name] = selected
    return requirements


def normalized_core_constraints(requirements: list[str]) -> list[tuple[str | None, str]]:
    """Normalize the extras and specifier portion of source core requirements."""
    normalized = []
    for requirement in requirements:
        match = re.match(
            r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]+\])?\s*(.*)$",
            requirement,
        )
        if match:
            normalized.append((match[1], re.sub(r"\s+", "", match[2])))
    return normalized


def unreleased_entry_count() -> int | None:
    """Count active changelog entries, or return None for a malformed section."""
    try:
        text = CHANGELOG_PATH.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        return None
    if text.count(UNRELEASED_HEADING) != 1:
        return None
    unreleased = text.split(UNRELEASED_HEADING, 1)[1]
    next_release = re.search(r"^## \[", unreleased, re.MULTILINE)
    body = unreleased[: next_release.start()] if next_release else unreleased
    return len(re.findall(r"^- ", body, re.MULTILINE))


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
    try:
        target = load_status()["current_target"]
    except StatusError, KeyError:
        return UNSATISFIED, "the current release target could not be determined"
    entries = unreleased_entry_count()
    if entries is None:
        return UNSATISFIED, "the [Unreleased] changelog section could not be interpreted"
    expected = f"{target}.dev0" if entries else target
    phase = "development" if entries else "release"
    if version != expected:
        return (
            UNSATISFIED,
            f"{phase} workspace must declare {expected}, found synchronized {version}",
        )

    problems = []
    for adapter, requirements in sorted(package_core_requirements().items()):
        exact = f"=={version}"
        if normalized_core_constraints(requirements) != [(None, exact)]:
            problems.append(f"{adapter}={requirements!r}")
    if problems:
        return UNSATISFIED, "adapter core requirements are not exact: " + ", ".join(problems)
    return (
        SATISFIED,
        f"all {len(versions)} first-party packages declare {version}; "
        f"all {len(versions) - 1} adapters pin agnara=={version}",
    )


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
        # Release preparation moves the entries into the target's dated
        # section. Historical releases must not satisfy a new target.
        document = load_status()
        target = document["current_target"]
        previous = document["previous_release"]
        versions = package_versions()
        if not versions or set(versions.values()) != {target}:
            return UNSATISFIED, "empty [Unreleased] requires packages at the target version"
        heading = re.search(
            rf"^## \[{re.escape(target)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$",
            text,
            re.MULTILINE,
        )
        if heading is None:
            return UNSATISFIED, "[Unreleased] is empty and the dated target section is missing"
        try:
            date.fromisoformat(heading[1])
        except ValueError:
            return UNSATISFIED, "the target changelog date is invalid"
        release_body = text[heading.end() :]
        following = re.search(r"^## \[", release_body, re.MULTILINE)
        if following:
            release_body = release_body[: following.start()]
        entries = len(re.findall(r"^- ", release_body, re.MULTILINE))
        if not entries:
            return UNSATISFIED, "the target changelog section has no entries"
        compare = "https://github.com/Blandskron/agnara/compare/"
        required_links = (
            f"[Unreleased]: {compare}v{target}...develop",
            f"[{target}]: {compare}v{previous}...v{target}",
        )
        if not all(link in text.splitlines() for link in required_links):
            return UNSATISFIED, "target and Unreleased comparison links must match the release"
        return SATISFIED, f"[{target}] carries {entries} entries with release comparison links"
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


def _literal_all(path: Path) -> list[str] | None:
    """Read a module's literal ``__all__`` without importing the package."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except OSError, SyntaxError, UnicodeError:
        return None
    for node in tree.body:
        if not (
            (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "__all__"
                    for target in node.targets
                )
            )
            or (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "__all__"
            )
        ):
            continue
        value = node.value
        if value is None:
            return None
        try:
            exported = ast.literal_eval(value)
        except ValueError, TypeError:
            return None
        if isinstance(exported, list) and all(isinstance(name, str) for name in exported):
            return exported
        return None
    return None


def _module_path(module: str) -> Path | None:
    """The source file that owns a module's ``__all__``, or None if unusable.

    Only modules inside a workspace distribution are addressable, and the
    distribution is chosen by the module's own import root. A manifest entry
    naming anything else is refused rather than resolved, so the manifest can
    never be pointed at a path outside the packages it claims to describe.
    """
    parts = module.split(".")
    if any(not part.isidentifier() or part.startswith("_") for part in parts):
        return None
    source_root = SOURCE_ROOTS.get(parts[0])
    if source_root is None:
        return None
    if len(parts) == 1:
        return source_root / "__init__.py"
    relative = Path(*parts[1:])
    package = source_root / relative / "__init__.py"
    leaf = (source_root / relative).with_suffix(".py")
    candidates = [path for path in (package, leaf) if path.is_file()]
    return candidates[0] if len(candidates) == 1 else None


def _public_modules(import_name: str) -> set[str]:
    """Every non-private module of a distribution that deliberately exports names.

    The boundary is the source declaration, not a second subjective allowlist:
    a module is public when no part of its path is underscore-prefixed and it
    declares a non-empty literal ``__all__``. A module that exports nothing is
    not forced into the manifest, but it may still be listed there -- that is
    how the reserved `agnara-a2a` and `agnara-events` namespaces are held to an
    empty surface rather than merely left undescribed.
    """
    source_root = SOURCE_ROOTS[import_name]
    public: set[str] = set()
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        directories = relative.parts[:-1]
        if any(part.startswith("_") for part in directories):
            continue
        if path.name.startswith("_") and path.name != "__init__.py":
            continue
        if not _literal_all(path):
            continue
        if path.name == "__init__.py":
            suffix = ".".join(directories)
        else:
            suffix = ".".join((*directories, path.stem))
        public.add(import_name + (f".{suffix}" if suffix else ""))
    return public


def _classified_public_names() -> tuple[dict[str, dict[str, list[str]]] | None, str | None]:
    """Validate the manifest and return each distribution's classified surface.

    The result maps distribution name -> module -> exact ordered export list.
    """
    try:
        document = json.loads(PUBLIC_API_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"public API manifest cannot be read: {exc}"
    if not isinstance(document, dict) or document.get("schema_version") != 3:
        return None, "public API manifest must use schema_version 3"
    distributions = document.get("distributions")
    if not isinstance(distributions, list) or not distributions:
        return None, "public API manifest distributions must be a non-empty list"

    allowed = {"stable", "provisional", "experimental", "internal"}
    classified: dict[str, dict[str, list[str]]] = {}
    for entry in distributions:
        if not isinstance(entry, dict) or set(entry) != {"distribution", "import_name", "modules"}:
            return None, (
                "each manifest distribution must contain only distribution, import_name and modules"
            )
        distribution, import_name = entry["distribution"], entry["import_name"]
        if SOURCE_ROOTS.get(import_name) is None or DISTRIBUTIONS.get(distribution) != import_name:
            return None, f"manifest distribution {distribution!r} is not a workspace distribution"
        if distribution in classified:
            return None, f"public API manifest repeats distribution {distribution!r}"
        modules = entry["modules"]
        if not isinstance(modules, list) or not modules:
            return None, f"{distribution}: manifest modules must be a non-empty list"

        surface: dict[str, list[str]] = {}
        for module_entry in modules:
            if not isinstance(module_entry, dict) or set(module_entry) != {"module", "exports"}:
                return None, f"{distribution}: each manifest module has only module and exports"
            module = module_entry["module"]
            if not isinstance(module, str) or _module_path(module) is None:
                return None, f"manifest module {module!r} is not a module of a workspace package"
            if module.split(".")[0] != import_name:
                return None, f"{distribution}: manifest module {module!r} is another package's"
            if module in surface:
                return None, f"{distribution}: manifest repeats module {module!r}"
            exports = module_entry["exports"]
            if not isinstance(exports, list):
                return None, f"{module}: manifest exports must be a list"

            names: list[str] = []
            for index, item in enumerate(exports):
                if not isinstance(item, dict) or set(item) != {"name", "stability"}:
                    return None, f"{module}: export {index} must contain only name and stability"
                name, stability = item["name"], item["stability"]
                if not isinstance(name, str) or not name:
                    return None, f"{module}: export {index} has an invalid name"
                if stability not in allowed:
                    return None, f"{module}: export {name!r} has unknown stability {stability!r}"
                if stability == "internal":
                    return None, f"{module}: internal name {name!r} must not appear in the manifest"
                names.append(name)
            duplicates = sorted(name for name in set(names) if names.count(name) > 1)
            if duplicates:
                return None, f"{module}: manifest repeats: " + ", ".join(duplicates)
            surface[module] = names

        if import_name not in surface:
            return None, f"{distribution}: manifest must classify the {import_name} entry point"
        classified[distribution] = surface

    missing = sorted(set(DISTRIBUTIONS) - set(classified))
    if missing:
        return None, "distributions absent from the public API manifest: " + ", ".join(missing)
    return classified, None


def check_public_api_declared() -> tuple[str, str]:
    """Every shipped distribution's public surface is classified exactly.

    This is the whole workspace, not the kernel. An application consuming
    Agnara from outside the repository imports `agnara_http` and `agnara_mcp`
    as readily as `agnara`, so a governed core beside an ungoverned adapter is
    not a governed framework (ADR 0076).
    """
    missing = []
    for init in sorted(PACKAGES_DIR.glob("*/src/*/__init__.py")):
        if _literal_all(init) is None:
            missing.append(init.parent.name)
    if missing:
        return UNSATISFIED, "packages without a literal __all__: " + ", ".join(missing)

    classified, error = _classified_public_names()
    if error is not None:
        return UNSATISFIED, error
    assert classified is not None

    problems: list[str] = []
    for distribution, surface in sorted(classified.items()):
        ungoverned = sorted(_public_modules(DISTRIBUTIONS[distribution]).difference(surface))
        if ungoverned:
            problems.append("unclassified public modules: " + ", ".join(ungoverned))
        for module, expected in surface.items():
            source = _module_path(module)
            assert source is not None  # validated while parsing the manifest
            implemented = _literal_all(source)
            if implemented is None:
                problems.append(f"{module}: no literal __all__ to compare against")
                continue
            if implemented == expected:
                continue
            unclassified = [name for name in implemented if name not in expected]
            absent = [name for name in expected if name not in implemented]
            if unclassified:
                problems.append(f"{module}: unclassified: " + ", ".join(unclassified))
            if absent:
                problems.append(f"{module}: not exported: " + ", ".join(absent))
            if not unclassified and not absent:
                problems.append(f"{module}: export order differs from the manifest")
    if problems:
        return UNSATISFIED, "; ".join(problems)

    modules = sum(len(surface) for surface in classified.values())
    total = sum(len(names) for surface in classified.values() for names in surface.values())
    return SATISFIED, (
        f"{total} exports across {modules} modules "
        f"of {len(classified)} distributions are classified exactly"
    )


#: Automated gate id -> the function that decides it. A gate whose id is listed
#: here is never read from the status file.
#:
#: An entry here only makes a check *available*. A check runs when the status
#: file declares a gate with the same id, so an entry no status file
#: references is dead weight that looks like coverage. The test suite asserts
#: that every entry is reached -- see `tests/release/test_release_readiness.py`.
AUTOMATED_CHECKS = {
    "version-consistency": check_version_consistency,
    "python-baseline": check_python_baseline,
    "changelog-accurate": check_changelog,
    "repository-clean": check_repository_clean,
    "release-commit-identified": check_release_commit_identified,
    "license-metadata": check_license_metadata,
    "public-api-distinguished": check_public_api_declared,
}

# ---------------------------------------------------------------------------
# Evidence gates
# ---------------------------------------------------------------------------


def changed_since(commit: str, paths: list[str]) -> list[str] | None:
    """Which of `paths` changed between `commit` and HEAD, or None if unknown.

    This is what keeps the staleness rule useful rather than merely strict.
    Expiring every record on every commit would make the status permanently
    stale and train everyone to ignore it; expiring never would let a green
    record outlive the code. Expiring when the code the evidence actually
    covers has moved is the honest middle.
    """
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", f"{commit}..HEAD", "--", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except OSError, subprocess.CalledProcessError:  # pragma: no cover - unknown commit
        return None
    return [line for line in completed.stdout.splitlines() if line.strip()]


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

    for reference in evidence.get("paths", []):
        if not (ROOT / reference).exists():
            return UNSATISFIED, f"evidence references a missing path: {reference}"

    if current_commit is not None and commit != current_commit:
        covers = evidence.get("covers")
        if not covers:
            # Nothing declares what this evidence depends on, so any movement
            # could invalidate it. Refusing to guess is the safe answer.
            return STALE, (
                f"recorded on {commit[:10]}, HEAD is {current_commit[:10]}, "
                "and the evidence declares no 'covers' paths"
            )
        changed = changed_since(commit, covers)
        if changed is None:
            return STALE, f"recorded on {commit[:10]}; the range to HEAD could not be read"
        if changed:
            shown = ", ".join(changed[:3]) + ("..." if len(changed) > 3 else "")
            return (
                STALE,
                f"recorded on {commit[:10]}; {len(changed)} covered file(s) changed: {shown}",
            )

    summary = evidence.get("result") or evidence.get("command") or "recorded"
    if current_commit is not None and commit != current_commit:
        summary = f"{summary} (recorded on {commit[:10]}; nothing it covers has changed)"
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

"""Everything an application is invited to copy imports the governed API only.

`0.1.0a4` asks whether Agnara can be consumed as a framework from outside this
repository. `scripts/check_public_imports.py` is the mechanical answer: it
decides from `docs/public-api.json` whether an import names a classified module
and pulls a classified name out of it, and it runs on any tree, so the
reference applications built for this release can be audited with exactly the
rule the repository holds its own examples to (ADR 0076).

These rules must fail when:

- an official example, the README or a guide imports an internal symbol;
- a generated project imports something nobody classified;
- the auditor stops recognising a private import, an unclassified name or a
  star import, which would make every rule above vacuous;
- the exemption list quietly grows.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT


def _load_auditor() -> Any:
    """Load the script by path; `scripts/` is tooling, not an importable package."""
    location = WORKSPACE_ROOT / "scripts" / "check_public_imports.py"
    spec = importlib.util.spec_from_file_location("agnara_public_imports", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


auditor = _load_auditor()

MANIFEST = WORKSPACE_ROOT / "docs" / "public-api.json"
GENERATED_FIXTURE = WORKSPACE_ROOT / "tests" / "cli" / "fixtures" / "generated_reference.json"

#: Files an application is invited to copy. A private import in one of these
#: is worse than a private import in a test: the test breaks once, the example
#: keeps producing broken applications.
EXEMPLARY = (
    "examples",
    "README.md",
    "docs/API_DESIGN.md",
    "docs/APPLICATION_MODEL.md",
    "docs/CLI_SPEC.md",
    "docs/HTTP_COMPOSITION.md",
    "docs/INTEROPERABILITY.md",
    "docs/MCP_CONFORMANCE.md",
    "docs/PROJECT_MANIFEST.md",
    "docs/SCAFFOLDING.md",
)

#: Trees the rule deliberately does not cover, and why. Written out so that
#: widening the exemption is an edit here rather than a silent omission.
#:
#: `docs/adr` and `docs/rfc` are decision records: an RFC that sketches an API
#: which was never built is history, not a guide, and rewriting it to satisfy a
#: linter would falsify the record. `tests` and `benchmarks` exist partly to
#: exercise and measure internals, which is what internals are for.
EXEMPT = {
    "docs/adr": "decision records may quote rejected and superseded spellings",
    "docs/rfc": "proposals record the API that was considered, not the one that shipped",
    "tests": "the suite tests internals on purpose",
    "benchmarks": "the benchmarks measure the internal dispatcher directly",
}


def surface() -> Any:
    return auditor.Surface.from_manifest(MANIFEST)


def audit(source: str, tmp_path: Path, suffix: str = ".py") -> list[Any]:
    path = tmp_path / f"sample{suffix}"
    path.write_text(source, encoding="utf-8")
    return auditor.audit_path(path, surface())


# ---------------------------------------------------------------------------
# The auditor itself. Every rule below is worthless if these stop holding.
# ---------------------------------------------------------------------------


def test_the_manifest_the_auditor_reads_is_the_governed_one() -> None:
    assert json.loads(MANIFEST.read_text(encoding="utf-8"))["schema_version"] == 3


def test_a_governed_import_is_accepted(tmp_path: Path) -> None:
    source = (
        "from agnara import Agnara, Risk\n"
        "from agnara.core.di import DIRegistry, provider\n"
        "from agnara.execution import invoke_result\n"
        "from agnara_http import Http, OpenApiInfo\n"
        "from agnara_mcp import build_mcp_server\n"
        "from agnara_telemetry import OpenTelemetryTracingHook\n"
        "import agnara\n"
    )

    assert audit(source, tmp_path) == []


def test_importing_a_submodule_by_name_is_accepted(tmp_path: Path) -> None:
    """`from agnara import execution` names a governed module, not a missing export."""
    assert audit("from agnara import execution\n", tmp_path) == []


def test_a_private_module_import_is_rejected(tmp_path: Path) -> None:
    findings = audit("from agnara_http._dispatch import _HTTPDispatcher\n", tmp_path)

    assert [finding.reason for finding in findings] == ["agnara_http._dispatch is a private module"]


def test_a_public_looking_module_nobody_classified_is_rejected(tmp_path: Path) -> None:
    """`agnara.core.di.resolver` has no ``__all__``, so it is not public."""
    findings = audit("from agnara.core.di.resolver import DIContainer\n", tmp_path)

    assert "not a classified public module" in findings[0].reason


def test_an_unclassified_name_is_rejected(tmp_path: Path) -> None:
    findings = audit("from agnara import Agnara, Context\n", tmp_path)

    assert findings[0].reason == "agnara does not classify: Context"


def test_a_star_import_is_rejected(tmp_path: Path) -> None:
    """A star import cannot be audited, so it cannot be declared supported."""
    findings = audit("from agnara import *\n", tmp_path)

    assert "star import" in findings[0].reason


def test_a_non_agnara_import_is_none_of_the_rule_s_business(tmp_path: Path) -> None:
    assert audit("import os\nfrom pathlib import Path\nimport agnaralike\n", tmp_path) == []


def test_a_markdown_fence_is_audited(tmp_path: Path) -> None:
    source = "Prose.\n\n```python\nfrom agnara_http._asgi import _ASGIBoundary\n```\n"

    findings = audit(source, tmp_path, suffix=".md")

    assert len(findings) == 1
    assert findings[0].lineno == 4


def test_a_markdown_fragment_that_does_not_parse_is_still_audited(tmp_path: Path) -> None:
    """Guides show fragments, and a fragment still teaches an import."""
    source = "```python\nfrom agnara_mcp.dispatch import build_mcp_server\n\n    ...\n```\n"

    findings = audit(source, tmp_path, suffix=".md")

    assert findings == []


def test_a_fence_that_is_not_python_is_left_alone(tmp_path: Path) -> None:
    source = "```text\nfrom agnara_http._asgi import _ASGIBoundary\n```\n"

    assert audit(source, tmp_path, suffix=".md") == []


def test_the_command_line_reports_a_finding(tmp_path: Path) -> None:
    sample = tmp_path / "app.py"
    sample.write_text("from agnara_cli._manifest import load_manifest\n", encoding="utf-8")

    assert auditor.main([str(sample)]) == 1
    assert auditor.main([str(tmp_path / "absent.py")]) == 2


def test_the_command_line_accepts_a_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("from agnara import Agnara\n", encoding="utf-8")

    assert auditor.main([str(tmp_path)]) == 0


# ---------------------------------------------------------------------------
# What the repository ships
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", EXEMPLARY)
def test_nothing_exemplary_imports_outside_the_governed_api(target: str) -> None:
    """An example that needs an internal import is a public API that is missing."""
    root = WORKSPACE_ROOT / target
    assert root.exists(), f"{target} does not exist; the guides are part of the contract"

    findings = auditor.audit_path(root, surface())

    assert not findings, "\n".join(finding.render(WORKSPACE_ROOT) for finding in findings)


def test_generated_projects_import_only_governed_names(tmp_path: Path) -> None:
    """The CLI writes an application's first file. It must not teach an internal.

    Audited from the pinned fixture rather than by running the generator, so
    this rule fails on a template edit even when the generator is not exercised.
    """
    fixture = json.loads(GENERATED_FIXTURE.read_text(encoding="utf-8"))["scenarios"]
    written = 0
    for scenario, record in fixture.items():
        for name, text in record["files"].items():
            if not name.endswith(".py"):
                continue
            path = tmp_path / scenario / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written += 1

    assert written, "the generated-project fixture contains no Python to audit"
    findings = auditor.audit_path(tmp_path, surface())

    assert not findings, "\n".join(finding.render(tmp_path) for finding in findings)


@pytest.mark.parametrize("target", sorted(EXEMPT))
def test_every_exempt_tree_exists_and_is_named_with_a_reason(target: str) -> None:
    """An exemption for a tree that is gone is an exemption nobody reviewed."""
    assert (WORKSPACE_ROOT / target).exists(), target
    assert EXEMPT[target]


def test_no_exemplary_target_is_also_exempt() -> None:
    assert not set(EXEMPLARY) & set(EXEMPT)

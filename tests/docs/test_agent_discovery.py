"""Protect the usable discovery path, not just the presence of filenames."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from jsonschema import Draft202012Validator
from scripts.check_public_imports import Surface, audit_path
from scripts.render_agent_docs import (
    LINK,
    load_index,
    nest_headings,
    official_path,
    render,
    section,
)

from tests.docs.test_documented_examples import blocks_by_heading

ROOT = Path(__file__).resolve().parents[2]
NEW_MARKDOWN = (
    "docs/AGENT_GUIDE.md",
    "docs/AGENT_SELECTION.md",
    "docs/CHOOSING_AGNARA.md",
    "docs/AGENT_DISCOVERY.md",
    "docs/DOCUMENTATION_MCP.md",
    "docs/AGENT_STARTERS.md",
    "docs/AGENT_DISCOVERY_BENCHMARK.md",
    "examples/README.md",
)


def test_version_and_index_metadata_match_published_baseline() -> None:
    index = load_index()
    published = json.loads((ROOT / "docs/releases/release-status.json").read_text())
    assert index["version"] == published["previous_release"] == "1.0.3"
    assert index["release_commit"] == "c25d9eb5b2d432f652c4661a1925cb38baa63c82"
    packages = {
        tomllib.loads(path.read_text())["project"]["name"]: tomllib.loads(path.read_text())[
            "project"
        ]["version"]
        for path in (ROOT / "packages").glob("*/pyproject.toml")
    }
    for entry in index["documents"]:
        assert entry["version"] == packages[entry["package"]]
        assert entry["title"] and entry["topic"] and entry["description"] and entry["audience"]
        assert entry["stability"] in {"stable-api", "current-repository", "guidance", "proposed"}
    for name in ("llms.txt", "llms-full.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert index["version"] in text
        pinned = re.findall(r"agnara(?:-[a-z]+)?==([\d.]+)", text)
        assert all(value == index["version"] for value in pinned)


def test_generated_corpus_matches_sources_and_is_deterministic() -> None:
    expected = render()
    assert (ROOT / "llms-full.txt").read_text(encoding="utf-8") == expected == render()
    assert len(load_index()["corpus"]) == 22
    assert "## 10. A2A" in expected and "no public runtime API" in expected
    assert "## 11. Events" in expected and "## 12. Tasks" in expected
    source = (ROOT / "examples/minimal_capability.py").read_text().strip()
    assert source in expected


def test_source_change_is_detected_by_check_mode(tmp_path: Path) -> None:
    # A copied corpus demonstrates freshness without modifying canonical files.
    for name in ("docs", "examples", "scripts"):
        shutil.copytree(ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "llms-full.txt", tmp_path / "llms-full.txt")
    # Linked root sources are needed to resolve the canonical corpus's links.
    for path in ROOT.glob("*.md"):
        shutil.copy(path, tmp_path / path.name)
    for path in ROOT.glob("*.txt"):
        shutil.copy(path, tmp_path / path.name)
    shutil.copytree(
        ROOT / "packages",
        tmp_path / "packages",
        ignore=shutil.ignore_patterns("__pycache__", "assets"),
    )
    shutil.copytree(
        ROOT / "tests", tmp_path / "tests", ignore=shutil.ignore_patterns("__pycache__")
    )
    guide = tmp_path / "docs/AGENT_GUIDE.md"
    guide.write_text(
        guide.read_text().replace("Agnara is a Python backend", "Agnara is a typed Python backend")
    )
    result = subprocess.run(
        [sys.executable, str(tmp_path / "scripts/render_agent_docs.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1, result.stderr
    assert "stale" in result.stdout


@pytest.mark.parametrize(
    "name",
    [
        *NEW_MARKDOWN,
        "llms.txt",
        "llms-full.txt",
        ".agents/skills/create-agnara-service/SKILL.md",
        ".agents/skills/extend-agnara-capability/SKILL.md",
    ],
)
def test_discovery_links_resolve_inside_repository(name: str) -> None:
    source = ROOT / name
    for match in LINK.finditer(source.read_text(encoding="utf-8")):
        target = urlsplit(match[2])
        if target.scheme or target.netloc or not target.path:
            continue
        destination = (source.parent / unquote(target.path)).resolve()
        assert destination.is_relative_to(ROOT), (name, match[2])
        assert destination.exists(), (name, match[2])


def test_discovery_sources_and_examples_use_only_public_imports() -> None:
    surface = Surface.from_manifest(ROOT / "docs/public-api.json")
    targets = [ROOT / name for name in (*NEW_MARKDOWN, "llms.txt", "llms-full.txt")]
    targets += [ROOT / "examples", ROOT / ".agents/skills"]
    assert not [finding for target in targets for finding in audit_path(target, surface)]


def test_known_future_syntax_is_absent_from_executable_learning_blocks() -> None:
    for name in ("llms.txt", "llms-full.txt", "docs/AGENT_GUIDE.md"):
        for code in blocks_by_heading(ROOT / name).values():
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    assert node.id not in {"HttpApp", "McpApp", "A2AApp", "Inject", "Depends"}
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    function = node.func
                    if isinstance(function.value, ast.Name) and function.value.id == "app":
                        assert function.attr not in {"invoke", "provider", "expose", "get", "post"}


@pytest.mark.parametrize(
    "name",
    [
        "../SECURITY.md",
        "/etc/passwd",
        "docs/../../secret.md",
        "https://example.com/doc.md",
        "C:\\secret.md",
        "docs\\guide.md",
        "packages/agnara/README.md",
    ],
)
def test_generator_refuses_paths_outside_official_sources(name: str) -> None:
    with pytest.raises(ValueError):
        official_path(ROOT, name)


def test_generator_refuses_symlink_escape(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    (corpus / "docs").mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside sentinel")
    try:
        (corpus / "docs/escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    with pytest.raises(ValueError):
        official_path(corpus, "docs/escape.md")


def test_heading_extraction_preserves_code_and_rejects_ambiguity() -> None:
    text = "## First\n```python\n## Second\nprint('value')\n```\n## Second\nend\n"
    extracted = section(text, "First")
    assert "## Second" in extracted and "end" not in extracted
    assert "## Second\nprint" in nest_headings(text)
    with pytest.raises(ValueError):
        section(text + "## First\nduplicate\n", "First")


def test_benchmark_prompts_and_schema_are_valid_without_claimed_results() -> None:
    benchmark = ROOT / "benchmarks/agent_discovery"
    prompts = json.loads((benchmark / "prompts.json").read_text())
    ids = [item["id"] for item in prompts["prompts"]]
    assert len(ids) == len(set(ids)) == 9
    for item in prompts["prompts"]:
        if item["category"] != "implementation":
            assert "agnara" not in item["text"].casefold()
        else:
            assert prompts["target_version"] in item["text"]
    Draft202012Validator.check_schema(json.loads((benchmark / "result.schema.json").read_text()))
    assert not (benchmark / "results.json").exists()

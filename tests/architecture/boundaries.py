"""Shared vocabulary for the architecture tests.

This module knows how to read the workspace layout and how to extract the
imports a source file actually performs. The rules themselves live in the
test modules so that a failure names the document it violates.

Imports are collected statically from the AST rather than by importing the
packages, because a forbidden import hidden inside a rarely executed
function body is still an architecture violation.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = WORKSPACE_ROOT / "packages"

#: Distribution name -> top-level import package, per ADR 0017.
DISTRIBUTIONS: dict[str, str] = {
    "agnara-core": "agnara",
    "agnara-http": "agnara_http",
    "agnara-mcp": "agnara_mcp",
    "agnara-a2a": "agnara_a2a",
    "agnara-events": "agnara_events",
    "agnara-telemetry": "agnara_telemetry",
    "agnara-cli": "agnara_cli",
}

CORE_DISTRIBUTION = "agnara-core"
CORE_IMPORT_NAME = DISTRIBUTIONS[CORE_DISTRIBUTION]

ADAPTER_DISTRIBUTIONS: tuple[str, ...] = tuple(sorted(set(DISTRIBUTIONS) - {CORE_DISTRIBUTION}))

#: Import roots owned by the workspace.
WORKSPACE_IMPORT_NAMES: frozenset[str] = frozenset(DISTRIBUTIONS.values())

#: Third-party packages `agnara-core` must never import.
#:
#: The allowlist test (standard library only) is the general rule; this
#: denylist exists so that a regression fails with a message naming the
#: specific dependency the architecture forbids.
#: See AGENTS.md "NEVER couple core to protocols" and PRINCIPLES.md P2/P13.
FORBIDDEN_IN_CORE: frozenset[str] = frozenset(
    {
        # web / ASGI frameworks and servers
        "fastapi",
        "starlette",
        "litestar",
        "django",
        "flask",
        "quart",
        "uvicorn",
        "granian",
        "hypercorn",
        "daphne",
        # schema / validation libraries
        "pydantic",
        "pydantic_core",
        "msgspec",
        "attrs",
        "attr",
        "marshmallow",
        "cattrs",
        # protocol SDKs
        "mcp",
        "fastmcp",
        "a2a",
        "a2a_sdk",
        # observability SDKs
        "opentelemetry",
        # LLM provider SDKs
        "openai",
        "anthropic",
        "google",
        "cohere",
        "mistralai",
        "ollama",
        "litellm",
        "langchain",
        "llama_index",
        # infrastructure clients
        "sqlalchemy",
        "psycopg",
        "asyncpg",
        "redis",
        "kafka",
        "aiokafka",
        "confluent_kafka",
        "nats",
        "pika",
        "aio_pika",
        "boto3",
        "httpx",
        "aiohttp",
        "requests",
    }
)


@dataclass(frozen=True, slots=True)
class SourceImport:
    """One top-level module name imported by one source file."""

    module: str
    path: Path
    lineno: int

    def where(self) -> str:
        return f"{self.path.relative_to(WORKSPACE_ROOT).as_posix()}:{self.lineno}"


def package_source_root(dist_name: str) -> Path:
    return PACKAGES_DIR / dist_name / "src" / DISTRIBUTIONS[dist_name]


def source_files(dist_name: str) -> Iterator[Path]:
    yield from sorted(package_source_root(dist_name).rglob("*.py"))


def _top_level(module: str) -> str:
    return module.split(".", 1)[0]


def _file_imports(path: Path) -> Iterator[SourceImport]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield SourceImport(_top_level(alias.name), path, node.lineno)
        # `level > 0` is a relative import, which is intra-package by
        # definition and therefore never a boundary violation.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield SourceImport(_top_level(node.module), path, node.lineno)


def imports_of(dist_name: str) -> list[SourceImport]:
    """Every top-level module imported anywhere in a package's sources."""
    return [imp for path in source_files(dist_name) for imp in _file_imports(path)]


def external_imports_of(dist_name: str) -> list[SourceImport]:
    """Imports that leave the package's own import root."""
    own = DISTRIBUTIONS[dist_name]
    return [imp for imp in imports_of(dist_name) if imp.module != own]


def is_standard_library(module: str) -> bool:
    return module in sys.stdlib_module_names


def declared_dependencies(dist_name: str) -> list[str]:
    path = PACKAGES_DIR / dist_name / "pyproject.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def declared_workspace_dependencies(dist_name: str) -> list[str]:
    """Declared dependencies that are themselves workspace distributions."""
    return [
        dep for dep in declared_dependencies(dist_name) if _requirement_name(dep) in DISTRIBUTIONS
    ]


def _requirement_name(requirement: str) -> str:
    """Extract the distribution name from a PEP 508 requirement string."""
    for separator in ("[", "<", ">", "=", "!", "~", ";", " ", "@"):
        requirement = requirement.split(separator, 1)[0]
    return requirement.strip()


def import_graph() -> dict[str, set[str]]:
    """Workspace-internal import edges, keyed by distribution name."""
    by_import_name = {v: k for k, v in DISTRIBUTIONS.items()}
    graph: dict[str, set[str]] = {dist: set() for dist in DISTRIBUTIONS}
    for dist_name in DISTRIBUTIONS:
        for imp in external_imports_of(dist_name):
            if imp.module in WORKSPACE_IMPORT_NAMES:
                graph[dist_name].add(by_import_name[imp.module])
    return graph


def dependency_graph() -> dict[str, set[str]]:
    """Workspace-internal edges declared in packaging metadata."""
    return {
        dist: {_requirement_name(dep) for dep in declared_workspace_dependencies(dist)}
        for dist in DISTRIBUTIONS
    }


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """Return one cycle as a node path, or None when the graph is acyclic."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for neighbour in sorted(graph.get(node, ())):
            if colour.get(neighbour, WHITE) == GREY:
                return [*stack[stack.index(neighbour) :], neighbour]
            if colour.get(neighbour, WHITE) == WHITE:
                cycle = visit(neighbour)
                if cycle is not None:
                    return cycle
        stack.pop()
        colour[node] = BLACK
        return None

    for node in sorted(graph):
        if colour[node] == WHITE:
            cycle = visit(node)
            if cycle is not None:
                return cycle
    return None

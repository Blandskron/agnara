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

import distributions

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_DIR = WORKSPACE_ROOT / "packages"

#: The reviewed publication set, read from `docs/distributions.json`.
#:
#: `tests/release/test_publication_set.py` holds that file to the workspace
#: layout, the workspace root metadata and both workflows, so deriving the
#: architecture vocabulary from it is stronger than restating it here: the
#: seven names now have one definition that everything is checked against.
MANIFEST = distributions.load(WORKSPACE_ROOT)

#: Distribution name -> top-level import package, per ADR 0017.
DISTRIBUTIONS: dict[str, str] = MANIFEST.mapping

CORE_DISTRIBUTION = MANIFEST.core
CORE_IMPORT_NAME = DISTRIBUTIONS[CORE_DISTRIBUTION]

ADAPTER_DISTRIBUTIONS: tuple[str, ...] = tuple(sorted(set(DISTRIBUTIONS) - {CORE_DISTRIBUTION}))

#: Import roots owned by the workspace.
WORKSPACE_IMPORT_NAMES: frozenset[str] = frozenset(DISTRIBUTIONS.values())

#: Third-party packages `agnara` must never import.
#:
#: The allowlist test (standard library only) is the general rule; this
#: denylist exists so that a regression fails with a message naming the
#: specific dependency the architecture forbids.
#:
#: Every technology in the integration matrix of `docs/INTEROPERABILITY.md`
#: belongs here, because that document's whole premise is that the kernel
#: integrates with them from behind a port and never imports one. An entry is
#: not a prediction that someone will try; it is what turns invariant 2 of
#: that document into a test failure that names the library.
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
        "sanic",
        "falcon",
        "robyn",
        "tornado",
        "werkzeug",
        "ninja",
        "rest_framework",
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
        "sqlmodel",
        "alembic",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "aiosqlite",
        "pymysql",
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
        # template engines
        "jinja2",
        "mako",
        "chameleon",
        # task runtimes, schedulers and durable execution
        "celery",
        "taskiq",
        "dramatiq",
        "rq",
        "temporalio",
        "prefect",
        "apscheduler",
        # error reporting and further protocol projections
        "sentry_sdk",
        "strawberry",
        "graphene",
        "ariadne",
        "graphql",
        "grpc",
        "grpc_tools",
    }
)


#: Distributions no first-party Agnara package may declare as a dependency.
#:
#: ADR 0068 gives ecosystem interoperability to `0.1.0b1` and forbids every
#: alpha from shipping a framework, database, broker, task runtime or
#: template engine integration as a supported contract. A denylist
#: over source imports would not catch that, because an integration arrives as
#: a *declared dependency* first.
#:
#: These are PyPI distribution names, not import names, because that is what a
#: `pyproject.toml` carries. Protocol SDKs an adapter legitimately depends on
#: -- `mcp`, `opentelemetry-api` -- are deliberately absent: an adapter for a
#: protocol Agnara projects into is not an ecosystem integration.
#:
#: Removing an entry is a release decision recorded in an ADR, not a test fix.
ECOSYSTEM_INTEGRATIONS: frozenset[str] = frozenset(
    {
        # web frameworks and servers
        "fastapi",
        "starlette",
        "litestar",
        "django",
        "djangorestframework",
        "django-ninja",
        "flask",
        "quart",
        "sanic",
        "falcon",
        "aiohttp",
        "robyn",
        "tornado",
        "werkzeug",
        "uvicorn",
        "granian",
        "hypercorn",
        "daphne",
        # schema and validation libraries
        "pydantic",
        "msgspec",
        "attrs",
        "marshmallow",
        "cattrs",
        # databases, drivers and migrations
        "sqlalchemy",
        "sqlmodel",
        "alembic",
        "psycopg",
        "psycopg2-binary",
        "asyncpg",
        "aiosqlite",
        "pymysql",
        # caches, brokers and messaging
        "redis",
        "kafka-python",
        "aiokafka",
        "confluent-kafka",
        "nats-py",
        "pika",
        "aio-pika",
        # task runtimes, schedulers and durable execution
        "celery",
        "taskiq",
        "dramatiq",
        "rq",
        "temporalio",
        "prefect",
        "apscheduler",
        # templates and presentation
        "jinja2",
        "mako",
        # error reporting and further protocol projections
        "sentry-sdk",
        "strawberry-graphql",
        "graphene",
        "ariadne",
        "grpcio",
    }
)


def _normalized_requirement(requirement: str) -> str:
    """PEP 503 normalized distribution name of a PEP 508 requirement."""
    return _requirement_name(requirement).lower().replace("_", "-").replace(".", "-")


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

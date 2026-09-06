"""The files ``agnara project create`` writes.

Every template is a pure function of the project name, so two runs with the
same name produce byte-identical output. Nothing here reads the clock, the
environment or a random source: a generated project is reviewed in a diff, and
a diff that changes on its own is worse than no generator.

The generated project depends on ``agnara`` and nothing else. Adding a
transport package here would put a protocol dependency in a project's
application layer before the project has decided it wants one, which
`docs/APPLICATION_MODEL.md` and AGENTS.md both forbid.
"""

from __future__ import annotations

__all__ = ["project_files"]


def _pyproject(name: str) -> str:
    return f'''[project]
name = "{name}"
version = "0.1.0"
description = "An Agnara project."
requires-python = ">=3.14"
dependencies = ["agnara"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{name}"]

[tool.ruff]
line-length = 100
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
addopts = ["--strict-markers", "--strict-config", "-ra"]
testpaths = ["tests"]
pythonpath = ["src"]
'''


def _manifest(name: str) -> str:
    return f'''# The project composition manifest. It records what this project contains;
# Python composition in bootstrap.py remains the runtime truth.
# `agnara apps` reads this file. `agnara app create` will update it.

[project]
name = "{name}"
python = ">=3.14"

[defaults]
architecture = "modular-hexagonal"
'''


def _package_init(name: str) -> str:
    return f'''"""The {name} project."""

__all__: list[str] = []
'''


def _settings(name: str) -> str:
    return f'''"""Explicit settings for the {name} project.

Deliberately plain: a frozen value type constructed by ``bootstrap`` rather
than a module that reads the environment when imported. Where configuration
comes from is a decision this project has not made yet, and a generator should
not make it silently. Add a loader here when you choose one, and keep secrets
out of the manifest and out of version control.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Settings"]


@dataclass(frozen=True, slots=True)
class Settings:
    """Values the composition needs to build the application."""

    name: str = "{name}"
    debug: bool = False
'''


def _bootstrap(name: str) -> str:
    return f'''"""Compose the {name} application.

This module is the composition root: it builds the application and the
dependency registry, and nothing else imports a transport. An adapter — HTTP,
MCP, or another — is wired where the process starts, so the same capabilities
stay reachable from every one of them.

``app`` is the attribute Agnara tooling reads::

    agnara inspect {name}.bootstrap:app --path src
    agnara graph {name}.bootstrap:app --path src

Add capabilities with ``agnara app create``, or declare one here with
``@app.capability`` while the project is small.
"""

from __future__ import annotations

from agnara import Agnara
from agnara.core.di import DIRegistry

from {name}.settings import Settings

__all__ = ["app", "dependencies", "settings"]

settings = Settings()

#: The application. Its name becomes the namespace of every capability
#: declared on it, so a capability here is ``{name}.<name>``.
app = Agnara(settings.name)

#: Providers the capabilities in this project depend on. Register them here so
#: one composition owns the graph, and pass it to the tooling with
#: ``--dependencies dependencies``.
dependencies = DIRegistry()
'''


def _apps_init(name: str) -> str:
    return f'''"""Apps of the {name} project.

An app is a bounded context: it owns its capabilities and its layers, and it
is understandable on its own. Create one with::

    agnara app create <name>

See docs/APPLICATION_MODEL.md in the Agnara repository for the model.
"""

__all__: list[str] = []
'''


def _tests_init() -> str:
    return '"""Tests for this project."""\n'


def _test_bootstrap(name: str) -> str:
    return f'''"""The composition root builds an application that Agnara can read.

This is the check that the project is wired correctly. It fails if the
composition stops importing, if the application loses its name, or if the
registry cannot be compiled and frozen for startup.
"""

from __future__ import annotations

from agnara import Agnara

from {name}.bootstrap import app, dependencies


def test_the_composition_builds_an_application() -> None:
    assert isinstance(app, Agnara)
    assert app.name == "{name}"


def test_the_dependency_registry_exists_for_capabilities_to_use() -> None:
    assert dependencies is not None


def test_the_registry_can_be_compiled_and_frozen() -> None:
    """Registration closes at startup; a capability added later is a defect."""
    compiled = app.compile()

    assert compiled is not None
    assert app.is_compiled
'''


def _readme(name: str) -> str:
    return f"""# {name}

An Agnara project.

## Layout

```text
{name}/
├── agnara.toml          # what this project contains
├── pyproject.toml
├── src/{name}/
│   ├── bootstrap.py     # the composition root: `app` lives here
│   ├── settings.py
│   └── apps/            # one directory per bounded context
└── tests/
```

## Install

```bash
uv sync
```

## Inspect

The composition root exposes `app`, which every Agnara tool reads:

```bash
agnara apps
agnara inspect {name}.bootstrap:app --path src
agnara graph {name}.bootstrap:app --path src
agnara context {name}.bootstrap:app --path src
```

Seeing a capability is not permission to invoke it. Inspection applies the
same visibility rules a transport does; use `--visibility agent` to read the
project as a caller would.

## Test

```bash
uv run pytest
```

## Next

Add a bounded context:

```bash
agnara app create billing
```

Capabilities are declared once and exposed over any transport. Nothing in
`src/{name}` should import a protocol package.
"""


def _agents(name: str) -> str:
    return f"""# AGENTS.md — {name}

Instructions for coding agents working in this project.

## Model

This is an Agnara project. A **capability** is the unit of behaviour: it is
declared once, in Python, and exposed over any transport. HTTP, MCP and other
protocols are adapters, never the source of truth.

An **app** under `src/{name}/apps/` is a bounded context. It owns its
capabilities and is understandable on its own.

## Rules

- Do not import a transport package (`agnara_http`, `agnara_mcp`, or any web
  framework) from domain or application code. Adapters are wired where the
  process starts.
- `src/{name}/bootstrap.py` is the composition root. Keep `app` there.
- Registration closes at startup. Declare capabilities at import time; do not
  add them after `compile()`.
- `agnara.toml` records what this project contains. Change it with
  `agnara app create` rather than by hand where a command exists.
- Never put secrets in `agnara.toml` or in `settings.py`.

## Commands

```bash
uv run pytest
uv run ruff check .
agnara apps
agnara inspect {name}.bootstrap:app --path src
```

## Before finishing

Run the tests and the linter. Do not mark work complete without them passing.
"""


def project_files(name: str) -> dict[str, str]:
    """Every file ``agnara project create`` writes, keyed by relative path.

    Paths use ``/`` so one project generates identically on every platform.
    """
    return {
        "pyproject.toml": _pyproject(name),
        "agnara.toml": _manifest(name),
        "README.md": _readme(name),
        "AGENTS.md": _agents(name),
        f"src/{name}/__init__.py": _package_init(name),
        f"src/{name}/bootstrap.py": _bootstrap(name),
        f"src/{name}/settings.py": _settings(name),
        f"src/{name}/apps/__init__.py": _apps_init(name),
        "tests/__init__.py": _tests_init(),
        "tests/test_bootstrap.py": _test_bootstrap(name),
    }

"""The generator scenarios the golden fixture is pinned against.

Kept beside the fixture, and out of the test module, so regenerating it and
asserting against it read from exactly one definition of what is generated.

Regenerate the fixture with:

    uv run python -m tests.cli.reference_projects

The record is JSON rather than a directory of real files on purpose. A fixture
tree of `.py` files would be linted by Ruff and collected by pytest under this
repository's configuration -- a generated `test_capabilities.py` would run as
a repository test and a generated project's imports would be resolved against
the workspace. Storing the text sidesteps all of it, at the cost of reading
diffs as escaped strings.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from agnara_cli import EXIT_OK
from agnara_cli import main as cli

FIXTURE = Path(__file__).parent / "fixtures" / "generated_reference.json"

PROJECT = "commerce"

#: scenario -> the `agnara app create` arguments that produce it. Each runs in
#: its own freshly generated project, so one scenario cannot alter another.
#: Together they cover both architectures, an app with no exposures and an app
#: with two.
SCENARIOS: dict[str, tuple[str, ...]] = {
    "project": (),
    "default-app": ("billing",),
    "minimal-app": ("health", "--architecture", "minimal"),
    "exposed-app": ("payments", "--with", "http,mcp"),
}


def _tree(root: Path) -> dict[str, str]:
    """Every generated file, keyed by POSIX-relative path.

    Read as bytes and decoded, so a stray CRLF survives into the fixture
    instead of being normalised away by universal newlines -- E0A.13 asserts
    against exactly that.
    """
    return {
        path.relative_to(root).as_posix(): path.read_bytes().decode("utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def generate(scenario: str, directory: Path) -> Path:
    """Run one scenario's commands under `directory` and return the project."""
    if scenario not in SCENARIOS:
        raise KeyError(scenario)
    if cli(["project", "create", PROJECT, "--directory", str(directory)]) != EXIT_OK:
        raise RuntimeError(f"{scenario}: project create failed")

    root = directory / PROJECT
    arguments = SCENARIOS[scenario]
    if arguments and cli(["app", "create", *arguments, "--project", str(root)]) != EXIT_OK:
        raise RuntimeError(f"{scenario}: app create failed")
    return root


def record() -> dict[str, Any]:
    """The full generator output for every scenario, ready to serialise."""
    scenarios: dict[str, Any] = {}
    for scenario, arguments in SCENARIOS.items():
        with tempfile.TemporaryDirectory() as temporary:
            root = generate(scenario, Path(temporary))
            scenarios[scenario] = {
                "app_create_arguments": list(arguments),
                "files": _tree(root),
            }
    return {
        "regenerate_with": "uv run python -m tests.cli.reference_projects",
        "project": PROJECT,
        "scenarios": scenarios,
    }


def serialized() -> str:
    return json.dumps(record(), indent=2, sort_keys=True, ensure_ascii=False)


def main() -> int:
    """Regenerate the pinned fixture from the generators, never by hand."""
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(serialized() + "\n", encoding="utf-8", newline="\n")
    sys.stdout.write(f"wrote {FIXTURE}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

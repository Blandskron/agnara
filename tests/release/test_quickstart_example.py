"""The published quick start is a release deliverable, so it is a gate.

`examples/quickstart.py` and the README block it mirrors must keep running
against public API only. They are what a reader of the PyPI page executes
first, so a rename in `agnara` that breaks them breaks the release.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "quickstart.py"
HTTP_EXAMPLE = ROOT / "examples" / "http_service.py"


def _run(script: Path, cwd: Path) -> str:
    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_the_example_runs_and_reports_both_canonical_outcomes(tmp_path: Path) -> None:
    # Run from outside the repository so the example cannot rely on the
    # checkout layout, only on the importable `agnara` package.
    output = _run(EXAMPLE, tmp_path)
    assert "success: refunded 2500 cents for pay_123" in output
    assert "rejected: invalid_input" in output
    assert "protected (runtime-owned): ['ledger']" in output


def test_the_example_imports_only_public_agnara_api() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    imported = re.findall(r"^from ([\w.]+) import|^import ([\w.]+)", source, re.M)
    modules = {first or second for first, second in imported}
    agnara_modules = {name for name in modules if name.split(".")[0] == "agnara"}
    assert agnara_modules == {
        "agnara",
        "agnara.core.di",
        "agnara.execution",
        "agnara.policy",
    }
    assert not [name for name in agnara_modules if "._" in name]


def test_the_readme_quick_start_matches_the_public_api(tmp_path: Path) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme[readme.index("## Quick start") :]
    block = re.search(r"```python\n(.*?)```", quick_start, re.S)
    assert block is not None, "the README must keep a runnable Quick start block"

    script = tmp_path / "readme_quickstart.py"
    script.write_text(block.group(1), encoding="utf-8")
    assert "Success(value='refunded 2500 cents for pay_123')" in _run(script, tmp_path)


def test_the_http_example_runs_outside_the_repository(tmp_path: Path) -> None:
    """The HTTP composition guide's example is a deliverable, so it is a gate.

    Run from outside the checkout, so it cannot depend on the repository
    layout — only on the importable `agnara` and `agnara_http` packages.
    """
    output = _run(HTTP_EXAMPLE, tmp_path)

    assert "compiled: HttpApplication('http:public', 4 routes)" in output
    assert 'read     -> 200 {"found":true' in output
    assert 'write    -> 200 {"stored":"B-2"}' in output
    assert "missing  -> 404 not_found" in output
    assert "'/orders/{order_id}/attachments'" in output
    # The undocumented route is served and stays out of the document.
    assert "health   -> 200 documented=False" in output
    # A cookie, a form field and an upload in one request (ADR 0072), and the
    # per-route limit answering a structured 413 rather than crashing.
    assert '"session":"session-7"' in output
    assert '"note":"Signed copy"' in output
    assert '"bytes":12' in output
    assert "oversize -> 413 content_too_large" in output
    assert "http:public GET /health" in output


def test_the_http_example_imports_only_public_api() -> None:
    """An example that needs a private import is a public API that is missing."""
    source = HTTP_EXAMPLE.read_text(encoding="utf-8")
    imported = re.findall(r"^from ([\w.]+) import|^import ([\w.]+)", source, re.M)
    modules = {first or second for first, second in imported}
    agnara_modules = {name for name in modules if name.split(".")[0].startswith("agnara")}

    assert agnara_modules == {"agnara", "agnara.core.di", "agnara.exposure", "agnara_http"}
    assert not [name for name in agnara_modules if "._" in name]

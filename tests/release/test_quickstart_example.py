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

import pytest

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
        "agnara.di",
        "agnara.execution",
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

    assert agnara_modules == {"agnara", "agnara.di", "agnara.exposure", "agnara_http"}
    assert not [name for name in agnara_modules if "._" in name]


# ---------------------------------------------------------------------------
# The two features that had no runnable documentation
# ---------------------------------------------------------------------------

TELEMETRY_EXAMPLE = ROOT / "examples" / "telemetry.py"
FASTAPI_EXAMPLE = ROOT / "examples" / "fastapi_embedding.py"

#: Features the 1.0 clean-room review requires an application author to be able
#: to wire from public documentation alone, with the example that shows each.
DOCUMENTED_FEATURES = {
    "telemetry": TELEMETRY_EXAMPLE,
    "fastapi embedding": FASTAPI_EXAMPLE,
}


@pytest.mark.parametrize("example", sorted(DOCUMENTED_FEATURES.values()), ids=lambda p: p.name)
def test_the_new_examples_exist_and_import_only_public_api(example: Path) -> None:
    """An example that needs a private import is a public API that is missing."""
    assert example.is_file(), f"{example.name} is missing"
    source = example.read_text(encoding="utf-8")
    imported = re.findall(r"^from ([\w.]+) import|^import ([\w.]+)", source, re.M)
    modules = {first or second for first, second in imported}
    agnara_modules = {name for name in modules if name.split(".")[0].startswith("agnara")}

    assert agnara_modules, f"{example.name} imports no Agnara module"
    for module in agnara_modules:
        assert "._" not in module and not module.split(".")[-1].startswith("_"), (
            f"{example.name} reaches into {module}"
        )


def test_the_telemetry_example_runs_and_proves_redaction(tmp_path: Path) -> None:
    """Telemetry had no runnable example anywhere in the public documentation.

    An author wiring a tracer had to read `tests/integration/telemetry/` to find
    out how, which the 1.0 clean-room rule counts as a documentation defect. The
    example is now the answer, and it asserts the security property rather than
    only demonstrating the wiring.
    """
    output = _run(TELEMETRY_EXAMPLE, tmp_path)

    assert "billing.total: success -> 119" in output
    assert "billing.refuse: internal_failure" in output
    assert "outcome=success" in output
    assert "outcome=failure" in output
    assert "no payload, argument value or exception message reached the exporter" in output
    # The handler embeds the argument in its exception message on purpose. The
    # token is long and non-hexadecimal so it cannot collide with a random span
    # id or a nanosecond timestamp; an earlier 4-digit value did, and failed on
    # Windows CI by chance rather than on a leak.
    assert "zzz-payload-must-never-be-exported-zzz" not in output


def test_the_fastapi_embedding_example_runs_and_fails_closed(tmp_path: Path) -> None:
    """Embedding had no runnable example either, only a test fixture.

    The example is the documented host boundary: the host owns authentication,
    lifecycle and response mapping, the request object never reaches a
    capability, and an unmapped credential is refused rather than executed
    anonymously.
    """
    output = _run(FASTAPI_EXAMPLE, tmp_path)

    assert "authorized, scoped             -> 200" in output
    # Authenticated but unscoped is a policy refusal, not an authentication one.
    assert "authenticated, missing scope   -> 403" in output
    assert "unknown credential             -> 401" in output
    assert "no credential                  -> 401" in output
    # The host's own routes keep working beside the capability.
    assert "plain FastAPI route            -> 200" in output
    # The correlation header is the one raw request value the host forwards to
    # Agnara. The runtime keeps a `tracking_id` opaque and never treats it as a
    # selector, but opaque is not unconstrained: when Agnara owns the transport
    # its HTTP adapter bounds the header, and an embedding host has no adapter
    # doing that for it. An example is copied, so it has to show the check.
    assert re.search(r"^correlation accepted\s+-> 'req-7f3a9c'$", output, re.M), output
    assert re.search(r"^correlation dropped \(long\)\s+-> None$", output, re.M), output
    assert re.search(r"^correlation dropped \(token\)\s+-> None$", output, re.M), output

"""E8.3 and E8.4: ``agnara inspect`` as text and as deterministic JSON.

Every test drives ``main`` with an argument list, so the exit-code contract and
the stdout/stderr split are exercised rather than assumed. The target module is
written to a temporary directory: resolving a target imports real code, and a
test that stubbed the import would not be testing the thing that matters.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main

APPLICATION = '''
from agnara import Agnara, Confirmation, Risk
from agnara.core.di import DIRegistry, Scope, provider


class Ledger:
    pass


registry = DIRegistry()
not_a_registry = "text"


@provider(scope=Scope.SINGLETON)
def ledger() -> Ledger:
    return Ledger()


registry.bind(Ledger, ledger)
app = Agnara("billing")
not_an_app = object()


@app.capability(
    effects={"financial-write"},
    scopes={"billing:write"},
    risk=Risk.HIGH,
    confirmation=Confirmation.NEVER,
    idempotent=False,
)
def refund(payment_id: str, ledger: Ledger, amount_cents: int = 0) -> str:
    """Refund a captured payment."""
    return "refunded"


@app.capability
def health() -> str:
    """Report service health."""
    return "ok"
'''

EXPLODING = "raise RuntimeError('module import failed on purpose')\n"


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    """A directory holding importable target modules, isolated per test."""
    (tmp_path / "billing.py").write_text(APPLICATION, encoding="utf-8")
    (tmp_path / "exploding.py").write_text(EXPLODING, encoding="utf-8")
    yield tmp_path
    for name in ("billing", "exploding"):
        sys.modules.pop(name, None)


def run(
    project: Path,
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
    target: str = "billing:app",
) -> tuple[int, str, str]:
    code = main(["inspect", target, "--path", str(project), *arguments])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_text_output_presents_the_compiled_application(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(project, "--dependencies", "registry", capsys=capsys)

    assert code == EXIT_OK
    assert err == ""
    assert "agnara-introspection 0" in out
    assert "app billing (2 capabilities)" in out
    assert "billing.refund" in out
    assert "Refund a captured payment." in out
    assert "risk high, confirmation never, idempotency no" in out
    assert "payment_id: string (required)" in out
    assert "amount_cents: integer (optional)" in out
    assert "ledger: Ledger" in out
    assert "Ledger: singleton sync_function" in out


def test_text_output_carries_no_ansi_decoration(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, "--dependencies", "registry", capsys=capsys)

    assert "\x1b" not in out


def test_json_output_is_the_versioned_snapshot(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(project, "--dependencies", "registry", "--json", capsys=capsys)
    document = json.loads(out)

    assert code == EXIT_OK
    assert document["format"] == "agnara-introspection"
    assert document["version"] == "0"
    assert document["filtered"] is True
    assert [app["name"] for app in document["apps"]] == ["billing"]
    assert [item["id"] for item in document["apps"][0]["capabilities"]] == [
        "billing.refund",
        "billing.health",
    ]


def test_json_output_is_deterministic_across_runs(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, first, _ = run(project, "--dependencies", "registry", "--json", capsys=capsys)
    _, second, _ = run(project, "--dependencies", "registry", "--json", capsys=capsys)

    assert first == second
    # Sorted keys, so a reader diffing two exports sees only real changes.
    assert first == json.dumps(json.loads(first), indent=2, sort_keys=True) + "\n"


def test_both_modes_describe_the_same_filtered_snapshot(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, text, _ = run(project, "--dependencies", "registry", "--visibility", "agent", capsys=capsys)
    _, encoded, _ = run(
        project, "--dependencies", "registry", "--visibility", "agent", "--json", capsys=capsys
    )
    document = json.loads(encoded)

    identifiers = [item["id"] for app in document["apps"] for item in app["capabilities"]]
    assert identifiers == ["billing.refund", "billing.health"]
    for identifier in identifiers:
        assert identifier in text
    # agent visibility withholds dependencies from both renderings.
    assert document["apps"][0]["capabilities"][0]["dependencies"] == []
    assert "ledger: Ledger" not in text


def test_a_withheld_field_is_named_rather_than_shown_as_a_default(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(
        project, "--dependencies", "registry", "--visibility", "identity", capsys=capsys
    )

    # Risk always has a value in the model, so printing it would assert a fact
    # the visibility decision withheld.
    assert "risk " not in out
    assert "withheld: " in out
    assert "safety" in out.splitlines()[1]


def test_simulating_a_viewer_applies_the_same_scope_rule_as_a_transport(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, unscoped, _ = run(
        project, "--dependencies", "registry", "--as-scope", "other:read", capsys=capsys
    )
    _, scoped, _ = run(
        project, "--dependencies", "registry", "--as-scope", "billing:write", capsys=capsys
    )

    assert "billing.refund" not in unscoped
    assert "billing.health" in unscoped
    assert "app billing (1 capability)" in unscoped
    assert "billing.refund" in scoped


def test_hiding_removes_a_capability_and_can_empty_the_result(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, partial, _ = run(
        project, "--dependencies", "registry", "--hide", "billing.refund", capsys=capsys
    )
    code, empty, err = run(
        project,
        "--dependencies",
        "registry",
        "--hide",
        "billing.refund",
        "--hide",
        "billing.health",
        capsys=capsys,
    )

    assert "billing.refund" not in partial
    assert "billing.health" in partial
    # Nothing visible is an answer, not a failure.
    assert code == EXIT_OK
    assert err == ""
    assert "No capabilities are visible." in empty


def test_an_empty_result_is_still_a_valid_json_document(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(
        project,
        "--dependencies",
        "registry",
        "--hide",
        "billing.refund",
        "--hide",
        "billing.health",
        "--json",
        capsys=capsys,
    )
    document = json.loads(out)

    assert code == EXIT_OK
    assert document["apps"] == []
    assert document["project"] is None
    assert document["filtered"] is True


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("billing", "expected 'module:attribute'"),
        (":app", "expected 'module:attribute'"),
        ("billing:", "expected 'module:attribute'"),
        ("bill ing:app", "is not a module path"),
        ("billing:not an attribute", "is not an attribute name"),
    ],
)
def test_a_malformed_target_is_rejected_before_anything_is_imported(
    project: Path, capsys: pytest.CaptureFixture[str], target: str, expected: str
) -> None:
    code, out, err = run(project, capsys=capsys, target=target)

    assert code == EXIT_FAILED
    assert out == ""
    assert expected in err
    assert "Traceback" not in err
    assert "billing" not in sys.modules


def test_an_unimportable_target_is_a_diagnostic_not_a_traceback(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(project, capsys=capsys, target="absent:app")

    assert code == EXIT_FAILED
    assert out == ""
    assert "cannot import 'absent'" in err
    assert "Traceback" not in err


def test_a_target_module_that_raises_reports_the_reason(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(project, capsys=capsys, target="exploding:app")

    assert code == EXIT_FAILED
    assert "importing 'exploding' failed" in err
    assert "module import failed on purpose" in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    ("target", "arguments", "expected"),
    [
        ("billing:absent", (), "defines no attribute 'absent'"),
        ("billing:not_an_app", (), "is a object, not an Agnara application"),
        ("billing:app", ("--dependencies", "absent"), "defines no attribute 'absent'"),
        ("billing:app", ("--dependencies", "not_a_registry"), "not a DIRegistry"),
    ],
)
def test_a_target_that_is_not_what_it_claims_is_refused(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    arguments: tuple[str, ...],
    expected: str,
) -> None:
    code, out, err = run(project, *arguments, capsys=capsys, target=target)

    assert code == EXIT_FAILED
    assert out == ""
    assert expected in err


def test_a_capability_that_cannot_compile_reports_why(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Without the registry, the dependency parameter is treated as an input
    # and its type has no schema. Saying so beats describing the capability as
    # if it had no dependency.
    code, _, err = run(project, capsys=capsys)

    assert code == EXIT_FAILED
    assert "compiling 'billing' failed" in err


def test_an_unknown_command_line_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as captured:
        main(["inspect"])

    assert captured.value.code == EXIT_USAGE


def test_the_command_reports_its_version() -> None:
    with pytest.raises(SystemExit) as captured:
        main(["--version"])

    assert captured.value.code == EXIT_OK

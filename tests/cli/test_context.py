"""E8.13: ``agnara context`` writes the filtered snapshot for a model to read."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, main

APPLICATION = '''
from agnara import Agnara, Confirmation, Risk
from agnara.core.di import DIRegistry, Scope, provider


class Ledger:
    pass


registry = DIRegistry()


@provider(scope=Scope.SINGLETON)
def ledger() -> Ledger:
    return Ledger()


registry.bind(Ledger, ledger)
app = Agnara("billing")


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


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "billing.py").write_text(APPLICATION, encoding="utf-8")
    yield tmp_path
    sys.modules.pop("billing", None)


def run(
    project: Path,
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    code = main(
        [
            "context",
            "billing:app",
            "--path",
            str(project),
            "--dependencies",
            "registry",
            *arguments,
        ]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_context_describes_each_visible_capability(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(project, "--visibility", "agent", capsys=capsys)

    assert code == EXIT_OK
    assert err == ""
    assert out.startswith("# Available capabilities")
    assert "## Application `billing`" in out
    assert "### `billing.refund`" in out
    assert "Refund a captured payment." in out
    assert "- Safety: risk high, idempotency no" in out
    assert "- Effects: financial-write" in out
    assert "- Requires scopes: billing:write" in out
    assert "  - `payment_id` (string, required)" in out
    assert "  - `amount_cents` (integer, optional)" in out


def test_the_document_says_it_is_not_authorization(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, capsys=capsys)

    assert "not permission to invoke it" in out
    assert "authorized independently at call time" in out


def test_the_document_carries_its_format_and_version(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, capsys=capsys)

    assert "`agnara-introspection` version `0`" in out


def test_a_withheld_field_is_named_rather_than_asserted_as_a_default(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, "--visibility", "identity", capsys=capsys)

    # A model reading "risk low" because the real value was withheld would be
    # misled about exactly the thing that matters.
    assert "- Safety:" not in out
    assert "This view is partial." in out
    assert "safety" in out
    assert "### `billing.refund`" in out


def test_a_capability_with_no_inputs_says_so_only_when_inputs_are_published(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, published, _ = run(project, "--visibility", "agent", capsys=capsys)
    _, withheld, _ = run(project, "--visibility", "identity", capsys=capsys)

    assert "- Inputs: none" in published
    assert "- Inputs" not in withheld


def test_the_context_is_deterministic(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, first, _ = run(project, capsys=capsys)
    _, second, _ = run(project, capsys=capsys)

    assert first == second
    assert "\x1b" not in first


def test_the_context_hides_what_agnara_inspect_hides_for_one_viewer(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, unscoped, _ = run(project, "--as-scope", "other:read", capsys=capsys)
    code = main(
        [
            "inspect",
            "billing:app",
            "--path",
            str(project),
            "--dependencies",
            "registry",
            "--as-scope",
            "other:read",
        ]
    )
    inspected = capsys.readouterr().out

    assert code == EXIT_OK
    assert "billing.refund" not in unscoped
    assert "billing.refund" not in inspected
    assert "billing.health" in unscoped
    assert "billing.health" in inspected


def test_hiding_every_capability_says_so_plainly(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(
        project, "--hide", "billing.refund", "--hide", "billing.health", capsys=capsys
    )

    assert code == EXIT_OK
    assert err == ""
    assert "No capabilities are visible to you." in out
    # The safety statement survives an empty result: a model must not read an
    # empty document as "nothing is restricted".
    assert "not permission to invoke it" in out


def test_output_writes_a_file_and_prints_nothing(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "CAPABILITIES.md"

    code, out, err = run(project, "--output", str(destination), capsys=capsys)

    assert code == EXIT_OK
    assert out == ""
    assert err == ""
    written = destination.read_text(encoding="utf-8")
    assert written.startswith("# Available capabilities")
    assert written.endswith("\n")


def test_an_existing_file_is_not_replaced_without_authorization(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "CAPABILITIES.md"
    destination.write_text("keep me", encoding="utf-8")

    code, _, err = run(project, "--output", str(destination), capsys=capsys)

    assert code == EXIT_FAILED
    assert "pass --overwrite" in err
    assert destination.read_text(encoding="utf-8") == "keep me"


def test_overwrite_replaces_the_file(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "CAPABILITIES.md"
    destination.write_text("replace me", encoding="utf-8")

    code, _, _ = run(project, "--output", str(destination), "--overwrite", capsys=capsys)

    assert code == EXIT_OK
    assert destination.read_text(encoding="utf-8").startswith("# Available capabilities")


def test_the_context_shares_the_cli_failure_contract(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["context", "absent:app", "--path", str(project)])
    captured = capsys.readouterr()

    assert code == EXIT_FAILED
    assert captured.out == ""
    assert "cannot import 'absent'" in captured.err
    assert "Traceback" not in captured.err


def test_every_view_command_offers_the_same_visibility_controls() -> None:
    from agnara_cli._main import _parser

    parser = _parser()
    choices: dict[str, Any] = parser._subparsers._group_actions[0].choices  # type: ignore
    controls = {
        name: {
            option
            for action in choice._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        for name, choice in choices.items()
    }

    shared = {"--path", "--dependencies", "--visibility", "--as-scope", "--hide"}
    for name in ("inspect", "graph", "context"):
        assert shared <= controls[name], name
    assert {"--output", "--overwrite"} <= controls["context"]

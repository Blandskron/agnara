"""E8.5: ``agnara graph`` draws the same snapshot ``agnara inspect`` reads."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from agnara_cli import EXIT_FAILED, EXIT_OK, main

APPLICATION = '''
from agnara import Agnara
from agnara.core.di import DIRegistry, Scope, provider


class Config:
    pass


class Audit:
    pass


class Ledger:
    pass


class Unused:
    pass


registry = DIRegistry()


@provider(scope=Scope.SINGLETON)
def config() -> Config:
    return Config()


@provider(scope=Scope.SINGLETON)
def audit(config: Config) -> Audit:
    return Audit()


@provider(scope=Scope.INVOCATION)
def ledger(audit: Audit, config: Config) -> Ledger:
    return Ledger()


@provider(scope=Scope.SINGLETON)
def unused() -> Unused:
    return Unused()


for kind, factory in ((Config, config), (Audit, audit), (Ledger, ledger), (Unused, unused)):
    registry.bind(kind, factory)

app = Agnara("billing")


@app.capability(scopes={"billing:write"})
def refund(payment_id: str, ledger: Ledger) -> str:
    """Refund a captured payment."""
    return "refunded"


@app.capability
def health() -> str:
    """Report service health."""
    return "ok"
'''


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    (tmp_path / "wiring.py").write_text(APPLICATION, encoding="utf-8")
    yield tmp_path
    sys.modules.pop("wiring", None)


def run(
    project: Path,
    *arguments: str,
    capsys: pytest.CaptureFixture[str],
    command: str = "graph",
) -> tuple[int, str, str]:
    code = main([command, "wiring:app", "--path", str(project), *arguments])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_the_graph_draws_transitive_provider_relationships(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(project, "--dependencies", "registry", capsys=capsys)
    lines = [line.rstrip() for line in out.splitlines()]

    assert code == EXIT_OK
    assert err == ""
    assert "app billing" in lines
    assert "  billing.refund" in lines
    assert "    ledger:" in lines
    assert "      Ledger [invocation sync_function]" in lines
    assert "        Audit [singleton sync_function]" in lines
    assert "          Config [singleton sync_function]" in lines


def test_a_capability_without_dependencies_says_so(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, "--dependencies", "registry", capsys=capsys)

    assert "  billing.health" in out
    assert "    (no dependencies)" in out


def test_an_unreachable_provider_is_reported_transitively(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, "--dependencies", "registry", capsys=capsys)

    # Audit and Config are reached through Ledger, so only Unused is
    # genuinely unreferenced. Naming the transitively used ones would be a
    # false claim about the application.
    assert "providers no visible capability reaches: Unused" in out


def test_hiding_a_capability_changes_which_providers_are_reachable(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(
        project, "--dependencies", "registry", "--hide", "billing.refund", capsys=capsys
    )

    assert "billing.refund" not in out
    assert "providers no visible capability reaches: Audit, Config, Ledger, Unused" in out


def test_withholding_the_relationship_source_is_reported_not_drawn_empty(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, "--dependencies", "registry", "--visibility", "agent", capsys=capsys)

    assert "withheld relationship sources: dependencies, providers" in out
    assert "billing.refund" in out
    # No tree is drawn, and no claim is made that there are no dependencies.
    assert "(no dependencies)" not in out
    assert "Ledger" not in out


def test_a_viewer_who_sees_nothing_gets_an_answer_not_a_failure(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(
        project,
        "--dependencies",
        "registry",
        "--hide",
        "billing.refund",
        "--hide",
        "billing.health",
        capsys=capsys,
    )

    assert code == EXIT_OK
    assert err == ""
    assert "No capabilities are visible." in out


def test_the_graph_and_inspect_agree_under_one_visibility_decision(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ("--dependencies", "registry", "--as-scope", "billing:write")
    _, drawn, _ = run(project, *arguments, capsys=capsys)
    _, encoded, _ = run(project, *arguments, "--json", capsys=capsys, command="inspect")
    document = json.loads(encoded)

    described = {
        capability["id"]: [item["type"]["name"] for item in capability["dependencies"]]
        for app in document["apps"]
        for capability in app["capabilities"]
    }
    assert described == {"billing.refund": ["Ledger"], "billing.health": []}
    for identifier in described:
        assert identifier in drawn
    assert "Ledger [" in drawn


def test_a_viewer_without_the_scope_sees_neither_the_capability_nor_its_wiring(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(
        project, "--dependencies", "registry", "--as-scope", "other:read", capsys=capsys
    )

    assert "billing.refund" not in out
    assert "Ledger [" not in out
    assert "billing.health" in out


def test_the_graph_carries_no_ansi_decoration(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(project, "--dependencies", "registry", capsys=capsys)

    assert "\x1b" not in out


def test_the_graph_shares_the_cli_failure_contract(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["graph", "absent:app", "--path", str(project)])
    captured = capsys.readouterr()

    assert code == EXIT_FAILED
    assert captured.out == ""
    assert "cannot import 'absent'" in captured.err
    assert "Traceback" not in captured.err


def test_both_commands_offer_the_same_visibility_controls() -> None:
    """A command that quietly offered different controls would be a trap."""
    from agnara_cli._main import _parser

    parser = _parser()
    actions = {
        name: {
            option
            for action in choice._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        for name, choice in parser._subparsers._group_actions[0].choices.items()  # type: ignore
    }

    shared = {"--path", "--dependencies", "--visibility", "--as-scope", "--hide"}
    assert shared <= actions["inspect"]
    assert shared <= actions["graph"]
    assert actions["inspect"] - actions["graph"] == {"--json"}

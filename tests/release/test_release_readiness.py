"""The release status file cannot claim more than the repository supports.

`scripts/check_release_readiness.py` is the tool a maintainer trusts to say
whether a release can close. These tests hold the properties that make that
trust reasonable: a satisfied gate carries evidence, evidence names the commit
it came from, an automated gate is really computed rather than asserted, and a
manual gate is never satisfied by the tool itself.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT


def _load_checker() -> Any:
    """Load the script by path.

    ``scripts/`` is repository tooling rather than an importable package, so
    there is no module path to import it by. Loading it from its location keeps
    it out of the packaging layout without adding a shim just for tests.
    """
    location = WORKSPACE_ROOT / "scripts" / "check_release_readiness.py"
    spec = importlib.util.spec_from_file_location("agnara_release_readiness", location)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, which is absent for a module loaded by
    # path alone.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


readiness = _load_checker()

STATUS_PATH = WORKSPACE_ROOT / "docs" / "releases" / "release-status.json"
PLAN_PATH = WORKSPACE_ROOT / "docs" / "releases" / "RELEASE_PLAN.md"
STATUS_MD_PATH = WORKSPACE_ROOT / "docs" / "releases" / "STATUS.md"

KINDS = {readiness.AUTOMATED, readiness.EVIDENCE, readiness.MANUAL}
STATES = {
    readiness.SATISFIED,
    readiness.PARTIAL,
    readiness.UNSATISFIED,
    readiness.NEEDS_REVIEW,
}


def document() -> dict[str, Any]:
    return json.loads(STATUS_PATH.read_text(encoding="utf-8"))


def gates() -> list[dict[str, Any]]:
    return document()["gates"]


# ---------------------------------------------------------------------------
# The status file's own integrity
# ---------------------------------------------------------------------------


def test_the_release_documents_all_exist() -> None:
    for path in (STATUS_PATH, PLAN_PATH, STATUS_MD_PATH):
        assert path.is_file(), path


def test_the_status_file_declares_a_supported_schema() -> None:
    assert document()["schema_version"] == readiness.SCHEMA_VERSION


def test_the_current_target_appears_in_the_release_plan() -> None:
    """A target nobody planned is a typo, not a release."""
    assert document()["current_target"] in PLAN_PATH.read_text(encoding="utf-8")


def test_gate_ids_are_unique() -> None:
    identifiers = [gate["id"] for gate in gates()]

    assert len(identifiers) == len(set(identifiers))


@pytest.mark.parametrize("gate", gates(), ids=lambda gate: gate["id"])
def test_every_gate_declares_a_known_kind_and_state(gate: dict[str, Any]) -> None:
    assert gate["kind"] in KINDS
    assert gate["status"] in STATES
    assert isinstance(gate["title"], str) and gate["title"]


# ---------------------------------------------------------------------------
# What makes a claim trustworthy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gate",
    [gate for gate in gates() if gate["kind"] == readiness.EVIDENCE],
    ids=lambda gate: gate["id"],
)
def test_a_satisfied_evidence_gate_carries_evidence(gate: dict[str, Any]) -> None:
    """The rule the whole program rests on: no claim without evidence."""
    if gate["status"] != readiness.SATISFIED:
        return
    evidence = gate.get("evidence")

    assert evidence, gate["id"]
    assert evidence.get("commit"), "evidence must name the commit it was produced on"
    assert evidence.get("command") or evidence.get("ci"), "evidence must be reproducible"


@pytest.mark.parametrize(
    "gate",
    [gate for gate in gates() if gate["kind"] == readiness.EVIDENCE],
    ids=lambda gate: gate["id"],
)
def test_evidence_paths_exist(gate: dict[str, Any]) -> None:
    for reference in (gate.get("evidence") or {}).get("paths", []):
        assert (WORKSPACE_ROOT / reference).exists(), reference


@pytest.mark.parametrize(
    "gate",
    [gate for gate in gates() if gate["kind"] == readiness.AUTOMATED],
    ids=lambda gate: gate["id"],
)
def test_every_automated_gate_has_a_real_check(gate: dict[str, Any]) -> None:
    """Declaring a gate automated must not be a way to avoid evidence."""
    assert gate["id"] in readiness.AUTOMATED_CHECKS


@pytest.mark.parametrize(
    "gate",
    [gate for gate in gates() if gate["kind"] == readiness.MANUAL],
    ids=lambda gate: gate["id"],
)
def test_a_manual_gate_explains_what_a_human_must_decide(gate: dict[str, Any]) -> None:
    assert gate.get("detail"), gate["id"]


# ---------------------------------------------------------------------------
# The evaluator's own rules
# ---------------------------------------------------------------------------


def test_the_checker_agrees_with_the_committed_status_file() -> None:
    """Running the tool on this checkout must reproduce the recorded state."""
    results = readiness.evaluate(document())

    assert results
    recorded = {gate["id"]: gate["status"] for gate in gates()}
    for result in results:
        if result.kind == readiness.AUTOMATED:
            continue
        if recorded[result.gate_id] == readiness.SATISFIED:
            # Evidence may legitimately be stale on a later commit; anything
            # else would mean the file claims something now false.
            assert result.status in {readiness.SATISFIED, readiness.STALE}, result


def test_readiness_never_reports_ready_while_a_mandatory_gate_is_open() -> None:
    results = readiness.evaluate(document())
    status = readiness.overall_status(results, document())

    open_gates = [
        result for result in results if result.mandatory and not result.counts_as_satisfied
    ]
    if open_gates:
        assert status != readiness.RELEASE_READY
    else:
        assert status == readiness.RELEASE_READY


def test_a_high_percentage_alone_never_makes_a_release_ready() -> None:
    """The failure mode this program exists to prevent."""
    almost = {
        "schema_version": readiness.SCHEMA_VERSION,
        "current_target": "0.0.0test",
        "gates": [
            {
                "id": f"evidence-{index}",
                "title": f"gate {index}",
                "kind": readiness.EVIDENCE,
                "mandatory": True,
                "status": readiness.SATISFIED,
                "evidence": {"commit": readiness.head_commit(), "command": "true"},
            }
            for index in range(19)
        ]
        + [
            {
                "id": "human-judgment",
                "title": "needs a person",
                "kind": readiness.MANUAL,
                "mandatory": True,
                "status": readiness.NEEDS_REVIEW,
                "detail": "someone has to decide",
            }
        ],
    }
    results = readiness.evaluate(almost)

    assert readiness.readiness_percentage(results) == 95
    assert readiness.overall_status(results, almost) == readiness.IN_PROGRESS


def test_stale_evidence_is_not_treated_as_green() -> None:
    """A recorded pass must not outlive the code it described."""
    stale = {
        "id": "old",
        "title": "measured long ago",
        "kind": readiness.EVIDENCE,
        "mandatory": True,
        "status": readiness.SATISFIED,
        "evidence": {"commit": "0" * 40, "command": "uv run pytest"},
    }
    status, detail = readiness.evaluate_evidence(stale, "f" * 40)

    assert status == readiness.STALE
    assert "stale" in detail.lower() or "recorded on" in detail


def test_a_satisfied_gate_without_evidence_is_a_hard_error() -> None:
    naked = {
        "id": "unsupported",
        "title": "claims a pass with nothing behind it",
        "kind": readiness.EVIDENCE,
        "mandatory": True,
        "status": readiness.SATISFIED,
    }

    with pytest.raises(readiness.StatusError, match="no evidence"):
        readiness.evaluate_evidence(naked, readiness.head_commit())


def test_an_automated_gate_without_an_implementation_is_a_hard_error() -> None:
    invented = {
        "schema_version": readiness.SCHEMA_VERSION,
        "current_target": "0.0.0test",
        "gates": [
            {
                "id": "not-implemented",
                "title": "declared automated, computed by nothing",
                "kind": readiness.AUTOMATED,
                "mandatory": True,
                "status": readiness.SATISFIED,
            }
        ],
    }

    with pytest.raises(readiness.StatusError, match="no implementation"):
        readiness.evaluate(invented)


def test_a_manual_gate_cannot_be_satisfied_without_evidence() -> None:
    asserted = {
        "schema_version": readiness.SCHEMA_VERSION,
        "current_target": "0.0.0test",
        "gates": [
            {
                "id": "judged",
                "title": "someone says it is fine",
                "kind": readiness.MANUAL,
                "mandatory": True,
                "status": readiness.SATISFIED,
                "detail": "trust me",
            }
        ],
    }

    with pytest.raises(readiness.StatusError, match="no evidence"):
        readiness.evaluate(asserted)


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def test_the_command_reports_the_target_and_a_status(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert readiness.main([]) == 0

    output = capsys.readouterr().out
    assert "AGNARA RELEASE READINESS" in output
    assert f"Target: {document()['current_target']}" in output
    assert "Status:" in output


def test_the_ready_sentence_appears_only_when_every_mandatory_gate_passes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    readiness.main([])
    output = capsys.readouterr().out

    results = readiness.evaluate(document())
    ready = readiness.overall_status(results, document()) == readiness.RELEASE_READY
    assert ("RELEASE READY:" in output) is ready


def test_require_ready_fails_while_the_target_is_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """So CI or a release script can depend on the answer."""
    code = readiness.main(["--require-ready"])
    capsys.readouterr()

    results = readiness.evaluate(document())
    ready = readiness.overall_status(results, document()) == readiness.RELEASE_READY
    assert code == (0 if ready else 1)


def test_json_output_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    readiness.main(["--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["current_target"] == document()["current_target"]
    assert isinstance(payload["readiness_percent"], int)
    assert len(payload["gates"]) == len(gates())


def test_a_missing_status_file_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(readiness, "STATUS_PATH", tmp_path / "absent.json")

    assert readiness.main([]) == 2
    assert "inconsistent" in capsys.readouterr().err

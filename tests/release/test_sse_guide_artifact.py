"""Negative proofs for installed-guide SSE wire/outcome/lifecycle validation."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.sse_guide import frames, run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "http_sse.py"))


def test_actual_guide_frames_and_lifecycle_pass(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize(
    ("case", "field", "value"),
    [
        ("completed", "status", 500),
        ("completed", "headers", {b"content-type": b"application/json"}),
        (
            "completed",
            "headers",
            {b"content-type": b"text/event-stream; charset=utf-8", b"cache-control": b"public"},
        ),
        ("completed", "units", [{"line": 9}]),
        ("completed", "units", [{"line": False}, {"line": True}]),
        ("completed", "terminal", {"outcome": "completed", "units": 3}),
        ("completed", "problem", {"code": "internal_failure"}),
        ("completed", "lifecycle", ["provider.open", "producer.open"]),
        ("empty", "terminal", None),
        ("empty", "lifecycle", []),
        ("denied", "status", 200),
        ("denied", "lifecycle", ["provider.open", "protected.handler", "provider.close"]),
        ("invalid_input", "lifecycle", ["provider.open"]),
        (
            "first_failure",
            "body",
            b'{"code":"internal_failure","private":"demo-private-diagnostic"}',
        ),
        ("first_failure", "problem", {"code": "forbidden"}),
        ("first_failure", "headers", {b"content-type": b"text/event-stream"}),
        ("late_failure", "body", b"demo-private-diagnostic"),
        ("late_failure", "terminal", {"outcome": "completed", "units": 1}),
        ("disconnect", "terminal", {"outcome": "completed", "units": 1}),
        (
            "disconnect",
            "lifecycle",
            [
                "provider.open",
                "producer.open",
                "produce:0",
                "produce:1",
                "producer.close",
                "provider.close",
            ],
        ),
    ],
)
def test_incorrect_outcomes_or_lifecycle_are_rejected(demonstrated, case, field, value) -> None:
    changed = deepcopy(demonstrated)
    changed[case][field] = value
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "frame",
    [
        b"event: unknown\ndata: {}\n\n",
        b"id: 1\ndata: {}\n\n",
        b"retry: 1\ndata: {}\n\n",
        b"data: {}",  # No final frame boundary.
        b'event: agnara.terminal\ndata: {"outcome":"completed","units":0}\n\ndata: {}\n\n',
        b'event: agnara.terminal\ndata: {"outcome":"completed","units":0}\n\n'
        b'event: agnara.terminal\ndata: {"outcome":"completed","units":0}\n\n',
    ],
)
def test_unknown_unterminated_duplicate_and_post_terminal_frames_are_rejected(frame) -> None:
    with pytest.raises(AssertionError):
        frames(frame)


@pytest.mark.parametrize("case", ["completed", "empty", "denied", "disconnect"])
def test_missing_cases_are_rejected(demonstrated, case) -> None:
    changed = deepcopy(demonstrated)
    del changed[case]
    with pytest.raises(AssertionError):
        validate(changed)


def test_corrupted_wire_and_reordered_cleanup_are_rejected(demonstrated) -> None:
    changed = deepcopy(demonstrated)
    changed["completed"]["body"] = changed["completed"]["body"].replace(b'"line":0', b'"line":9')
    assert changed["completed"]["body"] != demonstrated["completed"]["body"]
    with pytest.raises(AssertionError):
        validate(changed)
    changed = deepcopy(demonstrated)
    changed["late_failure"]["lifecycle"][-2:] = ["provider.close", "producer.close"]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize(
    "case,original,changed_value",
    [
        ("completed", b'"line":0', b'"line":false'),
        ("empty", b'"units":0', b'"units":false'),
        ("late_failure", b'"units":1', b'"units":true'),
    ],
)
def test_wire_booleans_cannot_masquerade_as_integer_values(
    demonstrated, case, original, changed_value
) -> None:
    changed = deepcopy(demonstrated)
    changed[case]["body"] = changed[case]["body"].replace(original, changed_value)
    assert changed[case]["body"] != demonstrated[case]["body"]
    with pytest.raises(AssertionError):
        validate(changed)


@pytest.mark.parametrize("case", ["first_failure", "late_failure"])
def test_json_escaped_diagnostics_are_rejected(demonstrated, case) -> None:
    changed = deepcopy(demonstrated)
    result = changed[case]
    problem = result["problem"] if case == "first_failure" else result["terminal"]["problem"]
    problem["detail"] = "demo-private-diagnostic"
    if case == "first_failure":
        result["body"] = json.dumps(problem).encode()
    else:
        units = result["body"].split(b"event: agnara.terminal\ndata: ", 1)[0]
        result["body"] = (
            units
            + b"event: agnara.terminal\ndata: "
            + json.dumps(result["terminal"]).encode()
            + b"\n\n"
        )
    result["body"] = result["body"].replace(
        b"demo-private-diagnostic", b"demo-private-diagno\\u0073tic"
    )
    assert b"demo-private-diagnostic" not in result["body"]
    with pytest.raises(AssertionError):
        validate(changed)

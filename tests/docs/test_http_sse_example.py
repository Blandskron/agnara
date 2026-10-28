"""The runnable SSE guide preserves wire outcomes and resource ownership."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from examples.http_sse import demonstrate, run_case


def test_http_sse_example_outcomes_and_cleanup() -> None:
    async def run():
        results = await demonstrate()
        assert asyncio.all_tasks() == {asyncio.current_task()}
        return results

    results = asyncio.run(run())
    complete = results["completed"]
    assert complete["status"] == 200
    assert complete["headers"][b"content-type"] == b"text/event-stream; charset=utf-8"
    assert complete["headers"][b"cache-control"] == b"no-store"
    assert complete["units"] == [{"line": 0}, {"line": 1}]
    assert complete["terminal"] == {"outcome": "completed", "units": 2}
    assert complete["body"].count(b"event: agnara.terminal") == 1
    assert b"id:" not in complete["body"] and b"retry:" not in complete["body"]

    for name, status, code in (
        ("denied", 403, "forbidden"),
        ("invalid_input", 400, "invalid_input"),
    ):
        result = results[name]
        assert result["status"] == status
        assert result["problem"]["code"] == code
        assert result["terminal"] is None and result["units"] == []
        assert result["lifecycle"] == []

    first = results["first_failure"]
    assert first["status"] == 500
    assert first["problem"]["code"] == "internal_failure"
    assert first["units"] == [] and first["terminal"] is None

    late = results["late_failure"]
    assert late["status"] == 200
    assert late["units"] == [{"line": 0}]
    assert late["terminal"]["outcome"] == "interrupted"
    assert late["terminal"]["units"] == 1
    assert late["terminal"]["problem"]["code"] == "internal_failure"
    assert late["body"].count(b"event: agnara.terminal") == 1
    for result in (first, late):
        assert b"demo-private-diagnostic" not in result["body"]

    disconnected = results["disconnect"]
    assert disconnected["status"] == 200
    assert disconnected["units"] == [{"line": 0}]
    assert disconnected["terminal"] is None and disconnected["problem"] is None
    assert b"agnara.terminal" not in disconnected["body"]
    assert "produce:1" not in disconnected["lifecycle"]

    for name in ("completed", "first_failure", "late_failure", "disconnect"):
        lifecycle = results[name]["lifecycle"]
        assert lifecycle[0:2] == ["provider.open", "producer.open"]
        assert lifecycle[-2:] == ["producer.close", "provider.close"]
        assert lifecycle.count("provider.open") == lifecycle.count("provider.close") == 1


def test_http_sse_example_empty_stream_has_a_terminal_and_closes_resources() -> None:
    result = asyncio.run(run_case("completed", count="0"))
    assert result["status"] == 200
    assert result["units"] == []
    assert result["terminal"] == {"outcome": "completed", "units": 0}
    assert result["lifecycle"] == [
        "provider.open",
        "producer.open",
        "producer.close",
        "provider.close",
    ]


def test_http_sse_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "http_sse.py"
    completed = subprocess.run(
        [sys.executable, str(example)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "completed: status=200 units=2 outcome=completed closed=1",
        "denied: status=403 units=0 outcome=forbidden closed=0",
        "invalid_input: status=400 units=0 outcome=invalid_input closed=0",
        "first_failure: status=500 units=0 outcome=internal_failure closed=1",
        "late_failure: status=200 units=1 outcome=interrupted closed=1",
        "disconnect: status=200 units=1 outcome=disconnected closed=1",
    ]

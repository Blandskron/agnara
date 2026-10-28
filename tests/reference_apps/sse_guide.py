"""Validate the copied SSE guide from installed wheels under Python -I."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path
from typing import Any


def frames(body: bytes) -> tuple[list[Any], dict[str, Any] | None]:
    """Decode this fixture's complete frames, independently of its own parser."""
    parts = body.split(b"\n\n")
    assert parts.pop() == b"", "SSE frame was not terminated"
    units: list[Any] = []
    terminal = None
    for part in parts:
        assert terminal is None, "frame after terminal"
        if part.startswith(b"event: agnara.terminal\ndata: "):
            terminal = json.loads(part.removeprefix(b"event: agnara.terminal\ndata: "))
            assert isinstance(terminal, dict)
        else:
            assert part.startswith(b"data: "), "unexpected SSE frame"
            units.append(json.loads(part.removeprefix(b"data: ")))
    return units, terminal


def validate(outcomes: dict[str, dict[str, Any]]) -> None:
    expected = {
        "completed": (200, [{"line": 0}, {"line": 1}], "completed"),
        "empty": (200, [], "completed"),
        "denied": (403, [], "forbidden"),
        "invalid_input": (400, [], "invalid_input"),
        "first_failure": (500, [], "internal_failure"),
        "late_failure": (200, [{"line": 0}], "interrupted"),
        "disconnect": (200, [{"line": 0}], None),
    }
    assert outcomes.keys() == expected.keys()
    for name, (status, units, outcome) in expected.items():
        result = outcomes[name]
        assert result["status"] == status, name
        assert result["units"] == units, name
        assert all(type(unit["line"]) is int for unit in result["units"]), name
        assert b"demo-private-diagnostic" not in result["body"], name
        if status == 200:
            assert result["headers"][b"content-type"] == b"text/event-stream; charset=utf-8"
            assert result["headers"][b"cache-control"] == b"no-store"
            assert result["problem"] is None
            decoded_units, terminal = frames(result["body"])
            assert decoded_units == units and terminal == result["terminal"], name
            assert all(type(unit["line"]) is int for unit in decoded_units), name
            if terminal is not None:
                assert type(terminal["units"]) is int, name
                assert "demo-private-diagnostic" not in json.dumps(terminal), name
            if outcome is None:
                assert terminal is None, name
            elif outcome == "completed":
                assert terminal == {"outcome": "completed", "units": len(units)}, name
            else:
                assert terminal is not None
                assert terminal.keys() == {"outcome", "units", "problem"}
                assert terminal["outcome"] == "interrupted" and terminal["units"] == 1
                assert terminal["problem"]["code"] == "internal_failure"
        else:
            assert result["headers"][b"content-type"] == b"application/problem+json"
            assert result["terminal"] is None
            assert json.loads(result["body"]) == result["problem"]
            assert result["problem"]["code"] == outcome
            assert "demo-private-diagnostic" not in json.dumps(result["problem"]), name

        if name in {"denied", "invalid_input"}:
            assert result["lifecycle"] == [], name
        else:
            assert result["lifecycle"] == [
                "provider.open",
                "producer.open",
                *(f"produce:{unit['line']}" for unit in units),
                "producer.close",
                "provider.close",
            ], name


async def run_guide(path: Path) -> dict[str, dict[str, Any]]:
    namespace = runpy.run_path(str(path))
    async with asyncio.timeout(20):
        outcomes = await namespace["demonstrate"]()
        outcomes["empty"] = await namespace["run_case"]("completed", count="0")
    assert asyncio.all_tasks() == {asyncio.current_task()}, "ASGI/lifespan tasks survived"
    return outcomes


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("SSE_GUIDE_ARTIFACT_OK")

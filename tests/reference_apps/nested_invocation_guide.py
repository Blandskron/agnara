"""Check the unchanged nested invocation guide against installed wheels under -I."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from agnara import Principal
from agnara.execution import Failure, FailureCode, Success

CASES = (
    ("authorized", frozenset({"summary:read", "catalog:read"})),
    ("child_denied", frozenset({"summary:read"})),
    ("parent_denied", frozenset({"catalog:read"})),
    ("no_scopes", frozenset()),
)


def validate(demo: Any) -> None:
    expected = {
        "authorized": (Success("Summary: A-1: widget"), ["summary", "product"]),
        "child_denied": (Success("Product unavailable: forbidden"), ["summary"]),
        "parent_denied": (Failure(FailureCode.FORBIDDEN, "required scopes not granted"), []),
        "no_scopes": (Failure(FailureCode.FORBIDDEN, "required scopes not granted"), []),
    }
    assert list(demo) == list(expected)
    identities: set[str] = set()
    effect_lists: set[int] = set()
    for name, (expected_result, expected_calls) in expected.items():
        result, calls = demo[name]
        assert isinstance(result, type(expected_result)), name
        assert result == expected_result, name
        if isinstance(expected_result, Success):
            assert isinstance(result.value, str)
        else:
            assert result.code is expected_result.code
        # Canonical equality excludes execution identity; check it separately.
        assert isinstance(result.execution_id, str) and result.execution_id
        assert result.execution_id not in identities, "independent root identities required"
        identities.add(result.execution_id)
        assert type(calls) is list and calls == expected_calls, name
        assert id(calls) not in effect_lists, "guide cases must not share mutable call lists"
        effect_lists.add(id(calls))


async def run_guide(path: Path) -> Any:
    name = "_agnara_nested_invocation_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    before = asyncio.all_tasks()
    try:
        spec.loader.exec_module(module)
        async with asyncio.timeout(20):
            demo = {}
            for label, scopes in CASES:
                demo[label] = await module.demonstrate(Principal("reader", scopes=scopes))
                assert asyncio.all_tasks() == before, "guide tasks survived"
        return demo
    finally:
        del sys.modules[name]


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("NESTED_INVOCATION_GUIDE_ARTIFACT_OK")

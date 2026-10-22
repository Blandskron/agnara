"""Check the exact direct-idempotency guide against candidate wheels under -I."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, Success


def validate(demo: Any) -> None:
    results, effects = demo
    expected = {
        "first": Success("receipt-1"),
        "duplicate": Success("receipt-1"),
        "changed_input": Failure(
            FailureCode.CONFLICT, "idempotency key conflicts with a different request"
        ),
        "permission_lost": Failure(FailureCode.FORBIDDEN, "required scopes not granted"),
        "other_principal": Success("receipt-2"),
    }
    assert list(results) == list(expected)
    for name, outcome in expected.items():
        result = results[name]
        assert result == outcome, name
        if isinstance(outcome, Failure):
            assert isinstance(result, Failure) and result.code is outcome.code
        assert isinstance(result.execution_id, str) and result.execution_id

    # Canonical outcome equality deliberately excludes execution identity.
    assert results["duplicate"].execution_id == results["first"].execution_id
    assert results["other_principal"].execution_id != results["first"].execution_id
    assert effects == [("A-1", 2500), ("A-1", 2500)]


async def run_guide(path: Path) -> Any:
    name = "_agnara_direct_idempotency_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        async with asyncio.timeout(20):
            demo = await module.demonstrate()
        assert asyncio.all_tasks() == {asyncio.current_task()}, "guide tasks survived"
        return demo
    finally:
        del sys.modules[name]


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("DIRECT_IDEMPOTENCY_GUIDE_ARTIFACT_OK")

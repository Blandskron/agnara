"""Check the exact deadline guide against candidate wheels under Python -I."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, Success


def validate(demo: Any) -> None:
    results, events = demo
    assert list(results) == ["success", "denied", "timeout", "cancelled"]
    assert results["success"] == Success("done")
    assert results["denied"] == Failure(FailureCode.FORBIDDEN, "required scopes not granted")
    assert results["timeout"] == Failure(FailureCode.TIMEOUT, "invocation deadline exceeded")
    assert results["cancelled"] == "CancelledError"
    # The denied call acquires nothing. Even the already-expired deadline
    # enters synchronously, then unwinds handler before its async provider.
    assert events == ["session.open", "handler.enter", "handler.exit", "session.close"] * 3


async def run_guide(path: Path) -> Any:
    name = "_agnara_deadlines_guide_consumer"
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
    print("DEADLINES_GUIDE_ARTIFACT_OK")

"""Check the exact confirmation guide against candidate wheels under Python -I."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, Success


def validate(demo: Any) -> None:
    results, effects = demo
    interaction = Failure(
        FailureCode.INTERACTION_REQUIRED,
        "Confirm this capability invocation before continuing.",
        details={
            "kind": "confirmation",
            "title": "Confirmation required",
            "capability_id": "catalog.archive",
            "hints": (),
        },
    )
    rejected = Failure(FailureCode.FORBIDDEN, "confirmation evidence was rejected")
    expected = {
        "missing": interaction,
        "metadata_flag": interaction,
        "forged": rejected,
        "changed_input": rejected,
        "other_actor": rejected,
        "scope_lost": Failure(FailureCode.FORBIDDEN, "required scopes not granted"),
        "approved": Success("Archived A-1: retired"),
        "replay": rejected,
        "expired": rejected,
    }
    assert list(results) == list(expected)
    for name, outcome in expected.items():
        result = results[name]
        assert result == outcome, name
        if isinstance(outcome, Failure):
            assert isinstance(result, Failure) and result.code is outcome.code
    assert effects == ["resource.open", "archive:A-1", "resource.close"]
    assert "unknown-approval" not in repr(results)


async def run_guide(path: Path) -> Any:
    name = "_agnara_confirmation_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Deferred dataclass annotations must resolve through the unchanged module.
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
    print("CONFIRMATION_GUIDE_ARTIFACT_OK")

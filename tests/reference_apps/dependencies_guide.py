"""Check the exact dependency guide against installed wheels under Python -I."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from agnara.execution import Failure, FailureCode, Success


def validate(demo: Any) -> None:
    assert demo.results.keys() == {"denied", "invalid", "first", "second", "failed"}
    assert demo.results["first"] == Success("first")
    assert demo.results["second"] == Success("second")
    for name, code in (
        ("denied", FailureCode.FORBIDDEN),
        ("invalid", FailureCode.INVALID_INPUT),
        ("failed", FailureCode.INTERNAL_FAILURE),
    ):
        result = demo.results[name]
        assert isinstance(result, Failure) and result.code is code
        assert "private" not in result.message + repr(result.details)
    assert demo.results["invalid"].details["path"] == ("label",)
    failed = demo.results["failed"]
    assert failed.message == "capability invocation failed" and not failed.details
    invocation_events = [
        "session.open",
        "reader.open",
        "handler.enter",
        "reader.close",
        "session.close",
    ]
    assert demo.events == ["pool.open", *invocation_events * 3, "pool.close"]
    assert len(demo.pools) == 1 and demo.pools[0].closed is True
    assert len(demo.sessions) == len(demo.readers) == len(demo.writers) == 3
    for resources in (demo.sessions, demo.readers, demo.writers):
        assert len({id(resource) for resource in resources}) == 3
    for session, reader, writer in zip(demo.sessions, demo.readers, demo.writers, strict=True):
        assert session is reader.session is writer.session
        assert session.pool is demo.pools[0]
        assert session.closed is True and reader.closed is True


async def run_guide(path: Path) -> Any:
    name = "_agnara_dependencies_guide_consumer"
    assert name not in sys.modules
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Resolve deferred provider/dataclass annotations through the exact module.
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
    print("DEPENDENCIES_GUIDE_ARTIFACT_OK")

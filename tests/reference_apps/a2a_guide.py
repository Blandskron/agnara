"""Check the exact copied provisional A2A example against installed wheels."""

from __future__ import annotations

import asyncio
import json
import runpy
import sys
from pathlib import Path
from typing import Any
from uuid import UUID


def validate(outcome: dict[str, Any]) -> None:
    assert outcome["protocol"] == "1.0"
    assert outcome["unauthenticated"] == (401, 'Bearer realm="agent.test"')
    assert outcome["rejected_effects"] == []
    results = outcome["results"]
    assert set(results) == {
        "valid",
        "recovered",
        "invalid_input",
        "forged_dependency",
        "denied",
        "handler_failure",
    }
    identities: set[str] = set()
    for name, value in (("valid", 30), ("recovered", 10)):
        result = results[name]
        assert set(result) == {"message"}
        message = result["message"]
        assert set(message) == {"messageId", "role", "parts"}
        identity = message["messageId"]
        assert str(UUID(identity)) == identity and identity not in identities
        identities.add(identity)
        assert message["role"] == "ROLE_AGENT"
        assert message["parts"] == [{"data": {"result": value}, "mediaType": "application/json"}]
    for name, code, category, reason in (
        ("invalid_input", -32602, "invalid_input", "INVALID_PARAMS"),
        ("forged_dependency", -32602, "invalid_input", "INVALID_PARAMS"),
        ("denied", -32603, "forbidden", "UNKNOWN_ERROR"),
        ("handler_failure", -32603, "internal_failure", "INTERNAL_ERROR"),
    ):
        result = results[name]
        assert set(result) == {"error", "id", "jsonrpc"}
        assert result["id"] == "demo" and result["jsonrpc"] == "2.0"
        error = result["error"]
        assert error["code"] == code
        assert error["data"] == [
            {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "reason": reason,
                "domain": "a2a-protocol.org",
                "metadata": {"agnaraCode": category},
            }
        ]
        assert "demo-private-diagnostic" not in json.dumps(result)
    assert results["handler_failure"]["error"]["message"] == "Internal error"
    assert outcome["events"] == [
        "pool.open",
        "ledger.open",
        "total:3",
        "ledger.close",
        "ledger.open",
        "total:-1",
        "ledger.close",
        "ledger.open",
        "total:1",
        "ledger.close",
        "client.close",
        "http.close",
        "lifespan.close",
        "pool.close",
        "container.close",
    ]


async def run_guide(path: Path) -> dict[str, Any]:
    namespace = runpy.run_path(str(path))
    before = asyncio.all_tasks()
    async with asyncio.timeout(20):
        outcome = await namespace["demonstrate"]()
    assert asyncio.all_tasks() == before, "A2A guide tasks survived teardown"
    return outcome


if __name__ == "__main__":
    validate(asyncio.run(run_guide(Path(sys.argv[1]))))
    print("A2A_GUIDE_ARTIFACT_OK")

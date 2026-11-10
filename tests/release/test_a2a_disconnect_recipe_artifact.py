"""The installed-recipe consumer must reject incorrect wire/lifecycle evidence."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.a2a_disconnect_guide import run_guide, validate


@pytest.fixture(scope="module")
def observed():
    return asyncio.run(
        run_guide(
            WORKSPACE_ROOT / "examples" / "a2a_disconnect.py",
            network_fixture=WORKSPACE_ROOT / "tests" / "a2a" / "test_a2a_network.py",
        )
    )


def test_exact_recipe_and_real_host_evidence_pass_validation(observed) -> None:
    validate(observed)


@pytest.mark.parametrize(
    "corruption",
    [
        "recovery",
        "timeout_reply",
        "early_effects",
        "body_read",
        "body_limit",
        "shutdown_order",
        "resource_leak",
        "bad_value",
    ],
)
def test_corrupted_recipe_evidence_is_rejected(observed, corruption: str) -> None:
    changed = deepcopy(observed)
    if corruption == "recovery":
        changed["disconnects"]["handler"]["recovery"] = 9
    elif corruption == "timeout_reply":
        changed["disconnects"]["handler"]["responses_after_disconnect"] = [{"error": "timeout"}]
    elif corruption == "early_effects":
        changed["limits"]["rejected_effects"] = ["pool.open"]
    elif corruption == "body_read":
        changed["limits"]["body_read_before_refusal"] = True
    elif corruption == "body_limit":
        changed["limits"]["oversized"] = 200
    elif corruption == "shutdown_order":
        changed["shutdown"]["lifecycle"][-2:] = reversed(changed["shutdown"]["lifecycle"][-2:])
    elif corruption == "resource_leak":
        changed["disconnects"]["handler"]["ledgers_closed"][-1] = False
    else:
        changed["in_process"]["results"]["valid"]["message"]["parts"][0]["data"]["result"] = 31
    with pytest.raises(AssertionError):
        validate(changed)

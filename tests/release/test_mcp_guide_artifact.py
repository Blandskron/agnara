"""Negative proofs for the structured installed-wheel MCP guide consumer."""

from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from tests.architecture.boundaries import WORKSPACE_ROOT
from tests.reference_apps.mcp_guide import run_guide, validate


@pytest.fixture(scope="module")
def demonstrated():
    return asyncio.run(run_guide(WORKSPACE_ROOT / "examples" / "mcp_tools.py"))


def test_actual_guide_sdk_results_pass_validation(demonstrated) -> None:
    validate(demonstrated)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("protocol",), "unreviewed"),
        (("listing", "tools"), []),
        (("listing", "tools", 0, "name"), "catalog.private"),
        (("listing", "ttl_ms"), 60_000),
        (("listing", "cache_scope"), "public"),
        (("listing", "next_cursor"), "next-page"),
        (("listing", "tools", 0, "input_schema", "additionalProperties"), True),
        (("listing", "tools", 0, "input_schema", "properties", "ledger"), {"type": "string"}),
        (("listing", "tools", 0, "input_schema", "required"), []),
        (("listing", "tools", 0, "output_schema"), {"type": "integer"}),
        (("unknown_code",), 0),
        (("rejected_effects",), ["private.handler"]),
        (("effects",), ["resource.open", "total:3:10"]),
        (("results", "valid", "structured_content"), {"result": 31}),
        (("results", "valid", "content", 0, "text"), '{"result":31}'),
        (("results", "valid", "content"), []),
        (("results", "valid", "is_error"), True),
        (("results", "recovered", "structured_content"), {"result": 0}),
        (("results", "invalid_input", "is_error"), False),
        (("results", "forged_dependency", "content", 0, "text"), '{"code":"forbidden"}'),
        (("results", "denied", "content", 0, "text"), '{"code":"invalid_input"}'),
        (
            ("results", "handler_failure", "content", 0, "text"),
            '{"code":"internal_failure","message":"demo-private-diagnostic"}',
        ),
    ],
)
def test_incorrect_discovery_outcomes_and_effects_are_rejected(demonstrated, path, value) -> None:
    changed = deepcopy(demonstrated)
    target = changed
    for key in path[:-1]:
        target = target[key] if isinstance(target, (dict, list)) else getattr(target, key)
    if isinstance(target, (dict, list)):
        target[path[-1]] = value
    else:
        setattr(target, path[-1], value)
    with pytest.raises(AssertionError):
        validate(changed)


def test_missing_outcome_and_reordered_cleanup_are_rejected(demonstrated) -> None:
    changed = deepcopy(demonstrated)
    del changed["results"]["recovered"]
    with pytest.raises(AssertionError):
        validate(changed)
    changed = deepcopy(demonstrated)
    changed["effects"][1:3] = reversed(changed["effects"][1:3])
    with pytest.raises(AssertionError):
        validate(changed)

"""The streaming kernel keeps the properties ADR 0084 claims for it.

`tests/unit/execution/test_streaming.py` shows that the contract behaves
correctly today. That is not the same claim as this file makes.

ADR 0084 D4 says the kernel never buffers and D5 says it starts no background
task, and neither property survives a plausible future edit that is *locally*
reasonable: a queue added to smooth a bursty producer, a task spawned to
prefetch one unit ahead, a shield wrapped around teardown to stop a noisy
traceback. Every one of those would keep the unit tests green while quietly
turning demand into something the consumer no longer controls, or making an
unresponsive producer impossible to cancel.

So the absence is what is tested here, statically, by name.
"""

from __future__ import annotations

import ast

import pytest

from tests.architecture.boundaries import CORE_DISTRIBUTION, package_source_root

STREAMING = package_source_root(CORE_DISTRIBUTION) / "execution" / "streaming.py"

#: `asyncio` names that would each break one of ADR 0084's decisions, and the
#: decision each one breaks. The reason travels with the name so a failure
#: explains itself rather than sending a reader to this docstring.
FORBIDDEN_ASYNCIO = {
    "Queue": "D4: a kernel buffer means demand is no longer the consumer's",
    "LifoQueue": "D4: a kernel buffer means demand is no longer the consumer's",
    "PriorityQueue": "D4: a kernel buffer means demand is no longer the consumer's",
    "create_task": "D5: core starts no producer task; consumption is structured",
    "ensure_future": "D5: core starts no producer task; consumption is structured",
    "gather": "D5: core starts no producer task; consumption is structured",
    "TaskGroup": "D5: core starts no producer task; consumption is structured",
    "to_thread": "D1: synchronous producers are out of scope, not thread-bridged",
    "shield": "D5: shielded teardown makes an unresponsive producer uncancellable",
    "wait_for": "D5: the deadline is bounded by timeout_at, not by a second clock",
}


@pytest.fixture(scope="module")
def tree() -> ast.Module:
    return ast.parse(STREAMING.read_text(encoding="utf-8"), filename=str(STREAMING))


def asyncio_attributes(tree: ast.Module) -> set[str]:
    """Every ``asyncio.<name>`` the module reaches for."""
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "asyncio"
    }


def test_the_streaming_boundary_exists_where_the_rules_look_for_it() -> None:
    """Without this, every rule below passes by reading nothing."""
    assert STREAMING.is_file(), STREAMING


def test_the_kernel_neither_buffers_nor_spawns(tree: ast.Module) -> None:
    used = asyncio_attributes(tree)
    assert used, "no asyncio use was parsed; the check would be vacuous"

    violations = sorted(
        f"asyncio.{name} -- {reason}" for name, reason in FORBIDDEN_ASYNCIO.items() if name in used
    )
    assert not violations, violations


def test_the_deadline_is_still_enforced(tree: ast.Module) -> None:
    """The mirror of the rule above: refusing `wait_for` is only honest while
    something else bounds the wait.
    """
    assert "timeout_at" in asyncio_attributes(tree)


def test_cancellation_is_re_raised_wherever_it_is_named(tree: ast.Module) -> None:
    """RFC 0009 constraint 3, checked as structure rather than as prose.

    A `CancelledError` handler that does not end in `raise` has swallowed
    cancellation, whatever it does in between.
    """
    swallowed = [
        handler.lineno
        for handler in ast.walk(tree)
        if isinstance(handler, ast.ExceptHandler)
        and "CancelledError" in ast.unparse(handler.type or ast.Constant(None))
        and not isinstance(handler.body[-1], ast.Raise)
    ]
    assert not swallowed, f"CancelledError is caught without re-raising at lines {swallowed}"

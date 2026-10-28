"""The tutorial's evidence boundary binds and consumes approval explicitly."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from examples.confirmation import DemoAuthority, DemoClock, demonstrate

from agnara import CapabilityId, ConfirmationEvidence, ConfirmationVerdict, Principal
from agnara.execution import Failure, FailureCode, Invocation, Success


def test_confirmation_example_effects_require_verified_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified_actors: list[Principal] = []
    original = DemoAuthority.verify

    async def record(
        self: DemoAuthority,
        evidence: ConfirmationEvidence,
        *,
        capability_id: CapabilityId,
        invocation: Invocation,
        principal: Principal,
    ) -> ConfirmationVerdict:
        verified_actors.append(principal)
        return await original(
            self, evidence, capability_id=capability_id, invocation=invocation, principal=principal
        )

    monkeypatch.setattr(DemoAuthority, "verify", record)
    results, effects = asyncio.run(demonstrate())
    for name in ("missing", "metadata_flag"):
        result = results[name]
        assert isinstance(result, Failure)
        assert result.code is FailureCode.INTERACTION_REQUIRED
        assert result.details["capability_id"] == "catalog.archive"
        assert result.details["kind"] == "confirmation"
    for name in ("forged", "changed_input", "other_actor", "scope_lost", "replay", "expired"):
        result = results[name]
        assert isinstance(result, Failure) and result.code is FailureCode.FORBIDDEN
    approved = results["approved"]
    assert isinstance(approved, Success) and approved.value == "Archived A-1: retired"
    assert effects == ["resource.open", "archive:A-1", "resource.close"]
    assert "unknown-approval" not in repr(results)
    assert len(verified_actors) == 6
    assert all("catalog:write" in actor.scopes for actor in verified_actors)


def test_demo_authority_exact_binding_and_atomic_single_use() -> None:
    async def run() -> None:
        clock = DemoClock()
        authority = DemoAuthority(clock)
        actor = Principal("alice", scopes={"catalog:write"})
        capability = CapabilityId.parse("catalog.archive")
        invocation = Invocation(capability, {"sku": "A-1", "reason": "retired"}, {})
        evidence = authority.approve(invocation, actor)
        assert (
            await authority.verify(
                ConfirmationEvidence(True),
                capability_id=capability,
                invocation=invocation,
                principal=actor,
            )
            is ConfirmationVerdict.INVALID
        )

        async def verify(target: CapabilityId, request: Invocation = invocation):
            return await authority.verify(
                evidence, capability_id=target, invocation=request, principal=actor
            )

        other = CapabilityId.parse("catalog.delete")
        assert await verify(other) is ConfirmationVerdict.INVALID
        assert (
            await verify(other, Invocation(other, invocation.payload, {}))
            is ConfirmationVerdict.INVALID
        )
        assert (
            await verify(capability, Invocation(capability, {"sku": "A-1", "reason": 1}, {}))
            is ConfirmationVerdict.INVALID
        )
        assert (
            await verify(
                capability, Invocation(capability, {**invocation.payload, "extra": True}, {})
            )
            is ConfirmationVerdict.INVALID
        )
        # The caller owns and joins simultaneous verification work. Exactly one
        # contender consumes this reference; neither relies on GIL serialization.
        async with asyncio.TaskGroup() as owned:
            first = owned.create_task(verify(capability))
            second = owned.create_task(verify(capability))
        assert {first.result(), second.result()} == {
            ConfirmationVerdict.VALID,
            ConfirmationVerdict.INVALID,
        }
        assert await verify(capability) is ConfirmationVerdict.INVALID
        assert isinstance(evidence.value, str)
        assert evidence.value not in repr(evidence)
        assert asyncio.all_tasks() == {asyncio.current_task()}

    asyncio.run(run())


def test_confirmation_example_verifier_errors_are_redacted_without_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(*args, **kwargs):
        raise RuntimeError("demo-private-verifier-diagnostic")

    monkeypatch.setattr(DemoAuthority, "verify", broken)
    results, effects = asyncio.run(demonstrate())
    approved = results["approved"]
    assert isinstance(approved, Failure) and approved.code is FailureCode.INTERNAL_FAILURE
    assert "demo-private-verifier-diagnostic" not in repr(results)
    assert effects == []


def test_confirmation_example_runs_outside_checkout(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "examples" / "confirmation.py"
    completed = subprocess.run(
        [sys.executable, str(example)], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "missing: interaction_required",
        "metadata_flag: interaction_required",
        "forged: forbidden",
        "changed_input: forbidden",
        "other_actor: forbidden",
        "scope_lost: forbidden",
        "approved: Archived A-1: retired",
        "replay: forbidden",
        "expired: forbidden",
        "effects: ['resource.open', 'archive:A-1', 'resource.close']",
    ]

"""One public-API capability and its one-shot worker host."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path

from experiments.durable.store import (
    CAPABILITY,
    REVISION,
    LostLease,
    admit,
    allowed,
    audit,
    claim,
    clock,
    credit_input,
    database,
    finish,
    get,
    owned,
    record_credit,
    write,
)

from agnara import Agnara, Principal
from agnara.di import DIContainer, DIRegistry, Scope, provider
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Failure,
    FailureCode,
    Invocation,
    Success,
    invoke_result,
)

ATTEMPT_SECONDS = 10


class Checkpoints:
    """Harness-controlled gates. These are never business input."""

    def __init__(self, control: Path, pause_at: str) -> None:
        self.control = control
        self.pause_at = pause_at

    def mark(self, name: str) -> None:
        (self.control / name).touch()

    def released(self) -> bool:
        return (self.control / "continue").exists()

    def sync(self, name: str) -> None:
        self.mark(name)
        if name == self.pause_at:
            deadline = time.monotonic() + 20
            while not self.released():
                if time.monotonic() >= deadline:
                    raise TimeoutError(name)
                time.sleep(0.01)

    async def pause(self, name: str) -> None:
        self.mark(name)
        if name == self.pause_at:
            async with asyncio.timeout(20):
                while not self.released():
                    await asyncio.sleep(0.01)


class Ledger:
    """Application effect boundary bound to a single attempt."""

    def __init__(
        self, db: sqlite3.Connection, row: sqlite3.Row, gates: Checkpoints, mode: str
    ) -> None:
        self.db, self.row, self.gates, self.mode = db, row, gates, mode

    async def credit(self, cents: int) -> int | Failure:
        await self.gates.pause("before_arm")
        if self.mode == "transient":
            return Failure(FailureCode.UNAVAILABLE, "fixture unavailable")
        job, generation = self.row["id"], self.row["generation"]
        try:
            with write(self.db):
                owned(self.db, job, generation)
                self.db.execute("UPDATE work SET armed = 1 WHERE id = ?", (job,))
            await self.gates.pause("armed")
            record_credit(self.db, job, generation, cents, receipt=self.mode != "no_receipt")
        except LostLease:
            self.gates.mark("effect_fenced")
            return Failure(FailureCode.CONFLICT, "ownership lost")
        await self.gates.pause("effect_committed")
        return cents


def compile_attempt(
    db: sqlite3.Connection, row: sqlite3.Row, gates: Checkpoints, mode: str
) -> tuple[ExecutionPlan, DIContainer]:
    app = Agnara("ledger")

    @app.capability(scopes={"ledger:credit"}, effects={"database-write"}, output=int)
    async def credit(cents: int, ledger: Ledger) -> int | Failure:
        return await ledger.credit(credit_input({"cents": cents}))

    @provider(scope=Scope.INVOCATION)
    def ledger_resource() -> Iterator[Ledger]:
        gates.mark("provider_open")
        try:
            yield Ledger(db, row, gates, mode)
        finally:
            gates.mark("provider_closed")

    dependencies = DIRegistry()
    dependencies.bind(Ledger, ledger_resource)
    plan = ExecutionPlan.compile(app.compile()[CAPABILITY], dependencies)
    return plan, DIContainer(dependencies)


async def invoke(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    gates: Checkpoints,
    plan: ExecutionPlan,
    container: DIContainer,
    mode: str,
) -> None:
    await gates.pause("claimed")
    job, generation = row["id"], row["generation"]
    raw = row["payload"].encode()
    if len(raw) > 64 or hashlib.sha256(raw).hexdigest() != row["fingerprint"]:
        try:
            finish(db, job, generation, result=None, failure="intent_mismatch")
        except LostLease:
            gates.mark("terminal_fenced")
        return
    with write(db):
        try:
            owned(db, job, generation)
        except LostLease:
            gates.mark("attempt_fenced")
            return
        scopes = {"ledger:credit"} if allowed(db, row["tenant"], row["subject"]) else set()
        principal = Principal(row["subject"], scopes=scopes)
        budget = min(ATTEMPT_SECONDS, row["expires"] - clock(db))
        if mode == "deadline":
            budget = min(budget, 0.25)
        # Fault injection exercises core input validation after a host mapping error.
        payload = {"cents": False} if mode == "malformed" else json.loads(raw)
        context = ExecutionContext(
            Invocation(
                plan.definition.id, payload, {}, deadline=asyncio.get_running_loop().time() + budget
            ),
            container,
            principal=principal,
        )
        audit(db, row, "entered", context.execution_id)
    outcome = await invoke_result(plan, context)
    if isinstance(outcome, Success):
        result, failure = outcome.value, None
    else:
        # Store the safe canonical category alone. The state machine decides
        # whether that category can be retried given the effect boundary.
        result, failure = None, outcome.code.value
    try:
        finish(db, job, generation, result=result, failure=failure)
    except LostLease:
        gates.mark("terminal_fenced")
        return
    await gates.pause("result_committed")


async def run_attempt(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    gates: Checkpoints,
    plan: ExecutionPlan,
    container: DIContainer,
    mode: str,
) -> None:
    job = row["id"]
    async with asyncio.TaskGroup() as tasks:
        attempt = tasks.create_task(invoke(db, row, gates, plan, container, mode))
        while not attempt.done():
            shutdown = (gates.control / "stop").exists()
            if shutdown or get(db, job)["cancel"]:
                attempt.cancel()
                break
            await asyncio.sleep(0.01)
    gates.mark("joined")
    # A shutdown before arming leaves the lease recoverable. Once armed,
    # only the evidence path may resolve the interrupted submission.
    if attempt.cancelled() and get(db, job)["armed"]:
        try:
            finish(db, job, row["generation"], result=None, failure=None)
        except LostLease:
            gates.mark("terminal_fenced")


async def worker(path: Path, job: str, gates: Checkpoints, mode: str) -> None:
    container = None
    try:
        with database(path) as db:
            revisions = {"missing": None, "incompatible": "ledger-v2"}
            row = claim(db, job, revisions.get(mode, REVISION))
            if row is not None:
                plan, container = compile_attempt(db, row, gates, mode)
                await run_attempt(db, row, gates, plan, container, mode)
        gates.mark("db_closed")
    finally:
        if container is not None:
            await container.aclose()
            gates.mark("container_closed")


def child(path: Path, control: Path, action: str, argument: str, pause: str, mode: str) -> None:
    gates = Checkpoints(control, pause)
    if action == "submit":
        with database(path) as db:
            admit(db, "north", "writer", argument, b'{"cents":25}', gates.sync)
        gates.mark("db_closed")
    else:
        asyncio.run(worker(path, argument, gates, mode))

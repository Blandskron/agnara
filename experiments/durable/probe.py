"""Run from the repository root with python -m experiments.durable.probe."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

from experiments.durable.store import (
    BACKOFF,
    LEASE,
    SCHEMA,
    TTL,
    Refused,
    admit,
    cancel,
    database,
    get,
    reconcile,
    visible,
)
from experiments.durable.worker import child

TENANT = "north"
SUBJECT = "writer"
INPUT = b'{"cents":25}'


class Worker:
    def __init__(self, process: subprocess.Popen, control: Path) -> None:
        self.process, self.control = process, control

    def wait_at(self, checkpoint: str) -> None:
        deadline = time.monotonic() + 15
        while not self.marked(checkpoint):
            if self.process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError(f"worker did not reach {checkpoint}: {self.process.returncode}")
            time.sleep(0.01)

    def marked(self, checkpoint: str) -> bool:
        return (self.control / checkpoint).exists()

    def signal(self, name: str) -> None:
        (self.control / name).touch()

    def join(self) -> None:
        assert self.process.wait(timeout=15) == 0
        assert self.marked("db_closed")

    def kill(self) -> None:
        assert self.process.poll() is None
        self.process.kill()
        assert self.process.wait(timeout=10) != 0


class Trial:
    def __init__(self, path: Path, db: sqlite3.Connection) -> None:
        self.path, self.db = path, db
        self.serial = 0

    @contextmanager
    def start(
        self, argument: str, pause: str = "-", mode: str = "-", *, action: str = "work"
    ) -> Iterator[Worker]:
        self.serial += 1
        control = self.path.parent / f"process-{self.serial}"
        control.mkdir()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "experiments.durable.probe",
                "--child",
                str(self.path),
                str(control),
                action,
                argument,
                pause,
                mode,
            ]
        )
        try:
            yield Worker(process, control)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

    def submit(self, request: str = "request", raw: bytes = INPUT) -> str:
        return admit(self.db, TENANT, SUBJECT, request, raw)

    def run(self, job: str, mode: str = "-") -> None:
        with self.start(job, mode=mode) as worker:
            worker.join()

    def advance(self, seconds: int) -> None:
        self.db.execute("UPDATE clock SET offset = offset + ?", (seconds,))

    def state(self, job: str) -> str:
        return get(self.db, job)["state"]

    def credits(self, job: str) -> list[int]:
        return [row[0] for row in self.db.execute("SELECT cents FROM credits WHERE id = ?", (job,))]

    def executions(self, job: str) -> list[str]:
        return [
            row[0]
            for row in self.db.execute(
                """SELECT execution FROM audit WHERE id = ? AND event = 'entered'
                   ORDER BY generation""",
                (job,),
            )
        ]

    def allow(self, yes: bool) -> None:
        self.db.execute("UPDATE authority SET allowed = ? WHERE tenant = ?", (yes, TENANT))


@contextmanager
def trial() -> Iterator[Trial]:
    with TemporaryDirectory(prefix="agnara-durable-") as root:
        path = Path(root) / "trial.sqlite"
        with database(path) as db:
            db.execute("PRAGMA journal_mode = DELETE")
            db.executescript(SCHEMA)
            db.executemany(
                "INSERT INTO authority VALUES (?, ?, 1)",
                [(TENANT, SUBJECT), ("south", SUBJECT), (TENANT, "peer")],
            )
            yield Trial(path, db)


def refusal(action, message: str) -> None:
    try:
        action()
    except Refused as error:
        assert str(error) == message
    else:
        raise AssertionError("admission unexpectedly accepted")


def admission() -> dict[str, int]:
    with trial() as t:
        with t.start("request", "before_admission_commit", action="submit") as submitter:
            submitter.wait_at("before_admission_commit")
            submitter.kill()
        assert t.db.execute("SELECT count(*) FROM work").fetchone()[0] == 0
        with t.start("request", "after_admission_commit", action="submit") as submitter:
            submitter.wait_at("after_admission_commit")
            committed = t.db.execute("SELECT id FROM work").fetchone()[0]
            submitter.kill()
        assert t.submit() == committed
        refusal(lambda: t.submit(raw=b'{"cents":26}'), "submission conflict")
        assert t.db.execute("SELECT count(*) FROM work").fetchone()[0] == 1
        assert t.credits(committed) == []
        return {"terminated_submitters": 2, "admissions": 1}


def recover_claim(*, revoke: bool, stale_alive: bool) -> dict[str, object]:
    with trial() as t:
        job = t.submit()
        checkpoint = "before_arm" if stale_alive else "claimed"
        with t.start(job, checkpoint) as first:
            first.wait_at(checkpoint)
            if stale_alive:
                t.run(job)
                assert get(t.db, job)["generation"] == 1 and t.credits(job) == []
            else:
                first.kill()
            if revoke:
                t.allow(False)
            t.advance(LEASE + 1)
            with t.start(job, "claimed") as second:
                second.wait_at("claimed")
                assert first.process.pid != second.process.pid
                assert get(t.db, job)["generation"] == 2
                if stale_alive:
                    first.signal("continue")
                    first.join()
                    assert first.marked("effect_fenced")
                    assert first.marked("terminal_fenced")
                    assert t.state(job) == "running" and t.credits(job) == []
                second.signal("continue")
                second.join()
                assert second.marked("provider_open") is not revoke
                assert second.marked("provider_closed") is not revoke
        expected = "failed" if revoke else "succeeded"
        assert t.state(job) == expected
        assert t.credits(job) == ([] if revoke else [25])
        executions = t.executions(job)
        assert len(set(executions)) == len(executions) == (2 if stale_alive else 1)
        if revoke:
            assert get(t.db, job)["failure"] == "forbidden"
        return {"generation": 2, "state": expected, "credits": len(t.credits(job))}


def crash_after_effect(*, receipt: bool) -> dict[str, object]:
    with trial() as t:
        job = t.submit()
        with t.start(job, "effect_committed", mode="-" if receipt else "no_receipt") as first:
            first.wait_at("effect_committed")
            assert t.credits(job) == [25] and get(t.db, job)["result"] is None
            first.kill()
        t.advance(LEASE + 1)
        t.run(job)
        assert t.state(job) == "uncertain"
        status = visible(t.db, TENANT, SUBJECT, job)
        assert status is not None and status["result"] is None
        assert not reconcile(t.db, "south", SUBJECT, job)
        assert not reconcile(t.db, TENANT, "peer", job)
        assert reconcile(t.db, TENANT, SUBJECT, job) is receipt
        status = visible(t.db, TENANT, SUBJECT, job)
        assert status is not None
        assert status["state"] == ("succeeded" if receipt else "uncertain")
        assert status["result"] == (25 if receipt else None)
        expected_event = "receipt_verified" if receipt else "receipt_missing"
        assert t.db.execute("SELECT event FROM audit WHERE event = ?", (expected_event,)).fetchone()
        assert t.credits(job) == [25] and len(t.executions(job)) == 1
        return {
            "after_recovery": "uncertain",
            "after_reconciliation": status["state"],
            "credits": 1,
        }


def lose_notification() -> dict[str, object]:
    with trial() as t:
        job = t.submit()
        with t.start(job, "result_committed") as first:
            first.wait_at("result_committed")
            first.kill()
        t.advance(LEASE + 1)
        t.run(job)
        status = visible(t.db, TENANT, SUBJECT, job)
        assert status is not None and status["result"] == 25
        assert not cancel(t.db, TENANT, SUBJECT, job)
        assert visible(t.db, "south", SUBJECT, job) is None
        assert visible(t.db, TENANT, "peer", job) is None
        assert visible(t.db, TENANT, SUBJECT, "missing") is None
        t.allow(False)
        assert visible(t.db, TENANT, SUBJECT, job) is None
        assert t.credits(job) == [25] and len(t.executions(job)) == 1
        return {"recorded_result": 25, "executions": 1, "unauthorized_lookups_hidden": True}


def stale_armed_worker() -> dict[str, object]:
    with trial() as t:
        job = t.submit()
        with t.start(job, "armed") as first:
            first.wait_at("armed")
            t.advance(LEASE + 1)
            t.run(job)
            assert t.state(job) == "uncertain"
            first.signal("continue")
            first.join()
            assert first.marked("effect_fenced") and first.marked("terminal_fenced")
        assert not reconcile(t.db, TENANT, SUBJECT, job)
        assert t.credits(job) == [] and get(t.db, job)["generation"] == 1
        return {"state": "uncertain", "stale_effects": 0}


def bounds() -> dict[str, object]:
    with trial() as t:
        for raw, message in (
            (b"x" * 65, "admission bounds exceeded"),
            (b'{"cents":true}', "cents must be an integer in range"),
            (b'{"cents":1000001}', "cents must be an integer in range"),
            (b'{"cents":25,"cents":25}', "noncanonical input"),
        ):
            refusal(lambda raw=raw: t.submit(raw=raw), message)
        t.allow(False)
        refusal(t.submit, "admission denied")
        assert t.db.execute("SELECT count(*) FROM work").fetchone()[0] == 0
        t.allow(True)

        # Probe core validation separately from the admission codec.
        malformed = t.submit("malformed")
        with t.start(malformed, mode="malformed") as worker:
            worker.join()
            assert not worker.marked("provider_open")
        assert t.state(malformed) == "failed" and get(t.db, malformed)["failure"] == "invalid_input"

        tampered = t.submit("tampered")
        t.db.execute("UPDATE work SET payload = ? WHERE id = ?", ('{"cents":26}', tampered))
        t.run(tampered)
        assert get(t.db, tampered)["failure"] == "intent_mismatch" and not t.executions(tampered)

        deadline = t.submit("deadline")
        with t.start(deadline, "before_arm", "deadline") as worker:
            worker.wait_at("before_arm")
            worker.join()
            assert worker.marked("provider_closed")
        assert t.state(deadline) == "failed" and get(t.db, deadline)["failure"] == "timeout"

        for mode in ("missing", "incompatible"):
            job = t.submit(mode)
            t.run(job, mode=mode)
            assert t.state(job) == "quarantined" and not t.executions(job)

        job = t.submit("retry")
        t.run(job, mode="transient")
        assert t.state(job) == "queued"
        t.run(job, mode="transient")
        assert get(t.db, job)["generation"] == 1
        t.advance(BACKOFF + 1)
        t.run(job, mode="transient")
        assert t.state(job) == "exhausted" and len(t.executions(job)) == 2

        expired = t.submit("expiry")
        t.advance(TTL + 1)
        t.run(expired)
        assert t.state(expired) == "expired" and not t.executions(expired)
        assert t.db.execute("SELECT count(*) FROM credits").fetchone()[0] == 0
        return {
            "attempt_limit": 2,
            "quarantined": 2,
            "expired": 1,
            "deadline": "timeout",
            "intent_mismatch": True,
            "credits": 0,
        }


def cancel_and_shutdown() -> dict[str, object]:
    with trial() as t:
        for action in ("cancel", "shutdown"):
            job = t.submit(action)
            with t.start(job, "before_arm") as first:
                first.wait_at("before_arm")
                assert not cancel(t.db, "south", SUBJECT, job)
                if action == "cancel":
                    assert cancel(t.db, TENANT, SUBJECT, job)
                else:
                    first.signal("stop")
                first.join()
                for marker in ("provider_closed", "container_closed", "joined"):
                    assert first.marked(marker)
            assert t.credits(job) == []
            t.advance(LEASE + 1)
            t.run(job)
            if action == "cancel":
                assert t.state(job) == "cancelled" and t.credits(job) == []
            else:
                assert t.state(job) == "succeeded" and t.credits(job) == [25]

        committed = t.submit("armedcancel")
        with t.start(committed, "effect_committed") as first:
            first.wait_at("effect_committed")
            assert cancel(t.db, TENANT, SUBJECT, committed)
            first.join()
        assert t.state(committed) == "uncertain" and t.credits(committed) == [25]
        assert reconcile(t.db, TENANT, SUBJECT, committed)
        return {"cancelled": "cancelled", "after_shutdown_retry": "succeeded", "rollback": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", nargs=6, metavar="ARG", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        path, control, action, argument, pause, mode = args.child
        child(Path(path), Path(control), action, argument, pause, mode)
        return
    if not __debug__:
        raise RuntimeError("run the probe with assertions enabled")
    print(
        json.dumps(
            {
                "environment": {
                    "python": platform.python_version(),
                    "implementation": platform.python_implementation(),
                    "platform": platform.platform(),
                    "machine": platform.machine(),
                    "sqlite": sqlite3.sqlite_version,
                    "agnara": version("agnara"),
                },
                "before_and_after_admission_commit": admission(),
                "killed_after_claim": recover_claim(revoke=False, stale_alive=False),
                "revoked_before_retry": recover_claim(revoke=True, stale_alive=False),
                "old_worker_alive_after_takeover": recover_claim(revoke=False, stale_alive=True),
                "crash_after_effect_with_receipt": crash_after_effect(receipt=True),
                "crash_after_effect_without_receipt": crash_after_effect(receipt=False),
                "lost_result_notification": lose_notification(),
                "old_worker_alive_after_arming": stale_armed_worker(),
                "bounds": bounds(),
                "cancellation_and_shutdown": cancel_and_shutdown(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

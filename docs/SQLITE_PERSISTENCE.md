# Application-owned SQLite persistence

Agnara invokes business capabilities and returns canonical outcomes. The
application owns its database engine, session and commit/rollback decision.
A capability depends on an application-defined port; it receives no ORM
session, connection or transaction object.

The runnable source is [examples/sqlite_persistence.py](../examples/sqlite_persistence.py),
with [storage and cleanup tests](../tests/docs/test_sqlite_persistence_example.py).
This is a small, sequential SQLAlchemy/SQLite fixture over the existing
[embedding boundary](adr/0094-framework-neutral-embedding-contract.md).
It adds no ORM integration or persistence API to Agnara.

## Run the example

Python >=3.14 is required. From the repository root:

```bash
uv sync
uv run python examples/sqlite_persistence.py
uv run pytest tests/docs/test_sqlite_persistence_example.py tests/integration/persistence
```

The workspace pins optional SQLAlchemy 2.0.54 for fixture evidence. SQLAlchemy
is absent from Agnara distribution dependencies. The example uses governed
imports from `agnara`, `agnara.di` and `agnara.execution`; its output below is
verified against the current checkout. An editable distribution version is not
proof of a historical wheel's behavior; use
[release history](https://github.com/Blandskron/agnara/releases/tag/v1.0.3)
for published provenance.

| Scenario | Outcome | Storage decision |
| --- | --- | --- |
| Valid, scoped `record` call | `Success("committed")` | Host commits. |
| Caller lacks `ledger:write` | `forbidden` | No port acquisition or SQL write. |
| Integer supplied for string input | `invalid_input` | No port acquisition or SQL write. |
| Handler writes then raises | Redacted `internal_failure` | Host rolls back the write. |
| Handler writes then caller cancels | `CancelledError` propagates | Host rolls back before re-raising. |

Only `('committed',)` appears when a fresh observer session reads the table.
The in-memory database is disposed at the end; the script leaves no database
file behind.

## Keep the handler behind an application port

`Ledger` is a Python `Protocol` with one `record(value: str) -> str` operation.
The handlers ask for `Ledger` through an explicit DI binding. `SqliteLedger`
implements it using the host's session and a parameterized SQL statement.
SQL strings and SQLAlchemy imports belong to this infrastructure implementation
and the composition root, rather than the handler's operation.

The invocation-scoped provider creates a port wrapper and releases that wrapper
at invocation exit. It does not close or commit the session. Sharing a wrapper's
underlying resource does not transfer the resource's ownership into the DI
container. A larger application can place the port, handlers, implementation
and composition into separate modules along the same boundaries.

Each capability declares `ledger:write`, database-write effect metadata and an
explicit string output contract. The scope policy enforces authority before
dependency acquisition and handler work. Effect metadata describes the
operation; it does not grant access. The writer principal is demonstration
data. A deployed host must authenticate callers at its trusted boundary.

## Decide the transaction from the canonical result

The example freezes one capability snapshot and compiles its plans once for
the owned session. Every call uses a fresh `ExecutionContext` through the same
runtime and container. The host's `transaction()` function awaits the canonical
outcome and explicitly commits `Success` or rolls back every other outcome.

A canonical `Failure` is a returned value, not an exception. A surrounding
transaction context that commits merely because no Python exception escaped
would therefore commit a write followed by a canonical failure. The example
checks the outcome before choosing commit. Its output-contract regression test
also proves that a write followed by invalid handler output is rolled back.

`Success` describes successful capability execution and output validation. It
does not mean the database commit has succeeded. A host commit failure remains
a host exception; this fixture attempts rollback and propagates it. Production
handling of ambiguous commit outcomes, outages or rollback failures belongs to
the application's storage policy. No automatic retry is introduced here.

## Preserve cancellation and cleanup ownership

The cancelled capability inserts a row, signals its start and suspends. A
`TaskGroup` owns the call; the example cancels and awaits it. The transaction
boundary catches escaping exceptions, including `CancelledError`, attempts
rollback and re-raises. The demo records only the child cancellation it
requested; cancellation of the demo itself still propagates.

Cleanup order is explicit:

1. The invocation releases its port wrapper.
2. The host chooses commit or rollback.
3. After all calls drain, the host awaits `runtime.aclose()`.
4. The host's session context closes the session.
5. The outer `finally` disposes the engine.

Creation, invocation and runtime shutdown run on one owning event loop. Tests
cover normal outcomes, a failing host commit and cancellation of the host while
its child is active, checking that no owned tasks remain. SQLAlchemy sessions
are not injected into invocation metadata, context state or DI bindings.

## Limits of this fixture

The example runs small synchronous SQLite operations on the owner thread and
serializes its transactions. It does not demonstrate nonblocking database I/O,
session sharing across concurrent calls or thread/loop reuse. Concurrent
application transactions need independently owned sessions and runtime
composition; sharing this closure would share mutable transaction state.

It provides no migration system, async-session adapter, PostgreSQL evidence,
durable idempotency store, automatic transaction manager or retry strategy.
The [interoperability inventory](INTEROPERABILITY.md) and
[maturity matrix](MATURITY.md) distinguish this bounded fixture from supported
framework features.

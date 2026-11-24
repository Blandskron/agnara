# ADR 0102 — Durable execution ownership

- Status: Accepted
- Date: 2026-11-16
- Tracking: [GitHub Issue #789](https://github.com/Blandskron/agnara/issues/789) (DUR-02)
- Related: ADR 0087, ADR 0089, ADR 0091, ADR 0094, [RFC 0012](../rfc/0012-durable-execution-boundary.md)

## Context

[DUR-01](../../experiments/durable/README.md) exercised recovery of one
complete-result capability through Agnara's existing public API. The host
owned admission, worker processes, SQLite and reconciliation. The queue, credit
and optional receipt shared one local SQLite database. The credit and receipt
committed together, in a different transaction from the invocation result.

DUR-02 repeated the probe on develop `684ca9429f8cc7e61694d0ac4e48827a8aefe711`
with CPython 3.14.4, editable Agnara 1.0.4 and SQLite 3.50.4 on Windows 11
build 26300 AMD64.

```sh
uv sync --locked
uv run --no-sync python scripts/check_public_imports.py experiments/durable
uv run --no-sync python -m experiments.durable.probe
```

Admission survived loss of its acknowledgement. Recovery before the effect
committed one credit on generation 2, or zero when the submitter's authority
had been revoked. A stale worker that was still alive could neither write a
result nor perform a credit after ownership was lost. After a credit committed
without a result, recovery retained one credit in both cases. An authorized
reconciliation with a matching receipt recovered the result. A missing
receipt left the submission uncertain. A committed result survived loss of
notification and remained visible only to its authorized owner.

## Proposed decision

Retain the application-owned worker as the reference experiment. Defer an
external engine trial and any framework-owned durable adapter or storage
port. The observed use case fits the existing compiled invocation path.
The parts that established safe recovery depended on the application's
authority and transaction contracts. The probe provides no second
application or backend with which to establish a common storage contract.

| Option | Ownership and evidence |
| --- | --- |
| Application-owned worker | Uses the existing invocation API. The host maintains admission, deadlines, leases, retry, cancellation, recovery, audit and retention. The fixture demonstrates the transitions needed for its local SQLite effect. |
| External engine integration | An engine could own dispatch and attempt persistence. The application would still supply current authority, deployment compatibility and evidence tying an attempt to its business effect. The fixture identifies no workload or operational requirement that warrants a concrete engine trial yet. |
| Agnara-owned durable adapter | Could share admission or attempt transitions across hosts once there is a second use case. It would need backend conformance, retention and migration rules, an operational lifecycle and a way to express effect uncertainty. |
| Kernel scheduler | Would make the invocation kernel own persistence and worker scheduling. Keep those concerns in the host. |

### Boundary retained from the experiment

- **Identity and authority.** One durable submission identifies versioned
  business input for an authenticated tenant and subject. Admission matches
  tenant, subject, capability and request key, then compares the input
  fingerprint before returning the existing submission ID. Each worker
  attempt has its own ownership generation and a fresh kernel execution ID.
  The host resolves authority again at execution, lookup, cancellation and
  reconciliation. The compiled plan checks policy before acquiring the
  invocation provider. The fixture also checks current authority when it
  writes the credit. No credentials, scope snapshots or confirmation evidence
  are persisted as authority.
- **Fencing and reconciliation.** The generation and lease check runs under
  the same SQLite write lock as the credit or terminal transition. Expiry
  alone cannot stop a worker. Once an attempt arms the effect boundary, a
  replacement suspends automatic execution and records uncertainty. An
  authorized reconciliation transaction checks the receipt against the
  submission fingerprint and records its decision. An effect outside the
  shared transaction requires equivalent application-owned evidence or
  suspension for reconciliation.
- **Clocks and lifecycle.** The fixture schedules persisted expiry, leases
  and retry on one host's wall clock, then derives an attempt deadline on
  the owning event loop's monotonic clock. The probe moves a shared clock
  offset to exercise expiry. Each worker joins owned invocation work before
  closing its database connection and then its container. Cancellation and
  shutdown can leave an armed attempt uncertain. Forced process termination
  does not exercise graceful cleanup.
- **Versions and retention.** The worker quarantines incompatible revisions
  or codecs and checks the persisted intent fingerprint before decoding.
  Attempt counts and transition types bound the fixture's audit writes.
  The harness deletes its temporary database at the end. A long-running
  host would need its own retention, migration and reconciliation operation,
  including the relationship between record expiry and admission
  deduplication.

## Evidence that would reopen the decision

Bring a concrete application with a recovery or operational requirement the
local worker cannot meet, or two applications with independently implemented
transitions that could share a small adapter contract. For an engine trial,
choose one pinned engine and compare it with the application-owned path
under the same interruption cases in RFC 0012. Verify current authority,
attempt identity, effect fencing or suspension, reconciliation, bounded
shutdown and deployment changes through the compiled invocation. Record
the code and operational responsibilities that each option introduces,
including any additional service, state or recovery procedure.

DUR-01 exercised process failure on a single Windows host. Distributed
ownership, clocks across hosts, power loss and external effects require
their own evidence. Any engine SDK stays at its integration boundary.

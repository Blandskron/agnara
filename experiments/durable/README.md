# DUR-01 — Recovery after worker termination

[Issue #784](https://github.com/Blandskron/agnara/issues/784) tests the
application-owned option in [RFC 0012](../../docs/rfc/0012-durable-execution-boundary.md).
A one-shot worker invokes the compiled `ledger.credit` capability through
Agnara's public API. The host owns admission, identity lookup, attempts,
reconciliation and SQLite. The capability returns the credited cents as a
complete result. The credit and its optional receipt commit together in a
separate transaction from the durable invocation result.

## Reproduce

Run from the root of this checkout with CPython 3.14. The fixture needs only
Agnara and the standard library. It uses a private temporary directory,
launches independent Python interpreters and terminates only its own children.
Run without Python optimization so the acceptance assertions execute.

```sh
uv sync --locked
uv run python scripts/check_public_imports.py experiments/durable
uv run python -m experiments.durable.probe
```

[Retained output](observed-windows.json) was produced with CPython 3.14.4 on
Windows 11 build 26300 AMD64, SQLite 3.50.4 (CPython's bundled module),
and editable Agnara 1.0.4 on develop
`261db83965a263a9dd28514e5d429b4dacbaaa8d` plus this fixture. SQLite uses a
local file, rollback journaling (`DELETE`), `synchronous=FULL`, a two-second
busy timeout and `BEGIN IMMEDIATE` for read/modify/write transactions.
The probe uses explicit checkpoints and the harness advances the shared
clock offset to cross expiry boundaries. No external service is needed.

## Crash and ownership evidence

| Interruption | Observation |
| --- | --- |
| Before admission commit | Forced process termination rolled back the insert. A subsequent submit could create the work. |
| Admission committed, response lost | Killing the submitter left one durable admission. The same authenticated caller, selector and fingerprint recovered the existing ID. A changed fingerprint produced a conflict. |
| Claimed, before the effect | Killing the worker and expiring its lease let a different process claim generation 2 and commit one credit. Revoking authority before recovery caused a core policy denial before provider entry and zero credits. |
| Credit committed, result absent | The replacement put the job in `uncertain` without entering the capability again. The current owner could reconcile from a matching receipt and obtain the original result. Without a receipt, reconciliation recorded the missing evidence and the job stayed uncertain. Both variants retained exactly one credit. |
| Result committed, notification lost | Killing the worker after result commit left 25 available to the authorized owner. A later worker performed no additional invocation. Cross-tenant, peer, revoked and unknown lookups had the same absent response. |
| Lease lost with the first worker alive | An active lease blocked a competing worker. Once it expired before the effect boundary was armed, generation 2 took over while generation 1 remained alive. Generation 1 could neither arm the effect nor write its terminal outcome. After arming, recovery suspended the job and fenced the old worker's write at the effect transaction. |

## Fixture rules

- **Admission and authority.** The harness supplies authenticated tenant and
  subject references from a fixed identity set. Admission, lookup and cancel
  resolve permission from a local authority table. Each attempt reconstructs a
  principal with current scopes and runs the compiled capability's policy. The
  effect transaction checks current authority again. The only registered
  operation is a complete-result capability with no confirmation requirement.
  The submission persists references and a fixed capability ID, with no token,
  scope list, executable selector or replayed confirmation.
- **Intent and outcomes.** Codec 1 accepts one canonical UTF-8 JSON object,
  `{"cents":25}` for example, at most 64 bytes. It round-trips a bounded
  integer and requires exact canonical bytes. The worker checks the fingerprint
  before decoding. A deployment or codec mismatch quarantines the job. The
  output is the same bounded integer. Status exposes only ID, state, result
  and a fixed failure code. Attempts use increasing generations and distinct
  kernel execution IDs; reconciliation does not create another execution ID.
- **Recovery and retries.** Before accessing the effect boundary, the handler
  persists an armed marker under the current generation. Effect and result
  transitions each check state, generation and expiration under the same
  SQLite write lock. A matching receipt ties the submission fingerprint to the
  committed credit. Reconciliation is an authorized transaction and records
  receipt verification or absence. A missing receipt needs independently
  verifiable application evidence to proceed. It stays suspended in this
  fixture. Before arming, `rate_limited` and `unavailable` permit at most two
  attempts with three seconds of backoff. `invalid_input`, `unauthenticated`,
  `forbidden`, `not_found`, `conflict`, `interaction_required`, `timeout` and
  `internal_failure` each retain their original code and terminate the job
  before arming. Any failure after arming remains uncertain. Leases are
  fixed at 30 seconds; this fixture has no renewal.
- **Time and shutdown.** A submission expires after 120 seconds. Workers on
  one host use its wall clock for stored timestamps and derive a fresh
  monotonic attempt deadline capped at 10 seconds. The probe forces a short
  deadline and verifies provider teardown. The clock assumption is one
  adequately synchronized host without backward jumps; multi-host clock
  behavior is untested. Cancellation before arming fences the effect and
  cancels the owned task. After arming it can leave an uncertain outcome. If
  the result already committed, it remains available. Host shutdown joins the
  cancelled attempt, closes SQLite and closes the container on its owning
  event loop. A pre-effect shutdown leaves work recoverable on lease expiry.
  SQLite calls and cleanup in this fixture are short and synchronous. The
  controller bounds child waits and terminates a child that outlives the test.
- **Retention.** The harness creates a fixed number of submissions and bounds
  audit entries per submission by the attempt count and finite transition set.
  Expired queued work remains inspectable until the trial ends. The harness
  then deletes the entire temporary database, including its effects. There is
  no live pruning, operational retention policy or migration workflow.

DUR-02 can use this result to evaluate the cost of maintaining the host
state machine. The demonstrated fencing depends on queue and effect sharing a
local SQLite write lock, and successful reconciliation depends on the effect
committing a receipt. Process termination on this host is the tested fault
model. Power loss, network partitions, external side effects and distributed
lease ownership require separate evidence.

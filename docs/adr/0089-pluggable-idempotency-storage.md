# ADR 0089 — Pluggable Idempotency Storage Port and Reference Store

- Status: Accepted
- Date: 2026-09-13
- Tracking: GitHub Issue #392
- Initiative: I3
- Related: ADR 0087, ADR 0020, RFC 0001

## Context

ADR 0087 separated an opaque runtime execution identity from caller tracking
and established that a caller-supplied idempotency key is an untrusted
selector. The runtime still needs a small, transport-neutral boundary that can
arbitrate concurrent use of such a selector without embedding a database,
cache, transaction model, serializer, or retry policy in the kernel.

## Decision

### D1 — A selector is capability-, principal-, key-, and fingerprint-bound

`IdempotencyScope` binds a validated opaque key to a `CapabilityId`, the
authenticated principal identifier, and caller-produced canonical request
fingerprint bytes. The storage index uses capability, principal, and key; the
fingerprint is compared atomically. A different fingerprint for the same
selector returns `IdempotencyConflict` without exposing the existing result,
execution id, key, or fingerprint. Different capabilities or principals are
different namespaces even if they reuse a key.

### D2 — The store owns atomic reservation transitions, not execution

`IdempotencyStore.claim()` atomically returns exactly one of a new
`IdempotencyClaimed` reservation, `IdempotencyInProgress`, a reusable
`IdempotencyCompleted` success, or a fingerprint conflict. A reservation has
an opaque generated execution id and a separate opaque completion token.
`complete()` and `abandon()` only affect the still-current reservation, so a
stale claimant cannot overwrite or release a replacement after expiry.

The port is asynchronous but does not prescribe a database transaction, Redis
command, schema, or driver. A PostgreSQL or Redis adapter can make each
transition one atomic backend operation without changing these semantics.

### D3 — Store only caller-serialized successful bytes, for finite windows

The invocation boundary owns output serialization, sensitive-result policy and
projection. The port stores only bounded opaque `bytes` representing a
successful result; it does not serialize arbitrary Python values and does not
store canonical `Failure` values. Failures and cancellations must call
`abandon()`, releasing the selector for a later explicit attempt. Neither path
retries a capability.

Both in-progress leases and completed successes have explicit positive TTLs.
The reference implementation removes expired entries before every operation,
uses a fixed entry capacity, and fails closed when full. A lease expiry is a
liveness boundary, not evidence that the previous handler stopped; a future
runtime integration must choose lease lengths and any renewal policy relative
to its owned execution deadline.

Expiration is defined as ``expires_at <= clock()``. A record is usable
immediately before its deadline, expired exactly at the deadline, and removed
before the next operation can observe it at or after that boundary. Stores
must apply this rule atomically with claim, lookup, complete and abandon, and
must reject stale completion or abandonment after cleanup. The reusable
contract at ``tests/conformance/idempotency_store.py`` exercises these rules
with an injected clock and a provider factory.

### D4 — The reference implementation is deliberately process-local

`InMemoryIdempotencyStore` uses a lock and a monotonic process clock for
deterministic tests and a single process only. It is neither durable nor
multi-process safe, loses all records on restart, and is not a production
deployment recommendation. No global store is created by the kernel.

## Threat and concurrency analysis

Keys, fingerprints and principal claims originate at application trust
boundaries and remain untrusted. The port bounds key, principal, fingerprint
and result sizes; omits key, fingerprint, reservation token and result bytes
from normal representations; and never returns existing material in a
conflict. It does not authenticate a principal or authorize an operation.

The claim transition is one critical section in the reference store, so
matching concurrent callers cannot both acquire a reservation. Completion and
abandon compare the opaque reservation token under the same lock. Expired
entries are removed deterministically, preventing immortal-key accumulation;
capacity exhaustion raises an explicit storage error rather than evicting a
live record or silently executing twice.

An incompatible stored state, failed completion, or failed abandonment is a
storage failure. The runtime must not convert any of these conditions into a
successful reuse or a second handler execution. Cancellation remains
cancellation; if cleanup cannot be confirmed, the reservation remains owned
until its finite lease expires.

## Consequences

- I3 has a replaceable, testable storage contract for future runtime and
  adapter integration without adding a transport field or storage dependency.
- Callers can reuse only an application-approved serialized success after a
  future boundary supplies a scoped key and fingerprint.
- Idempotency remains separate from authorization, retries, durable execution,
  scheduling, streams, protocol resumption and multitenancy.
- A future durable store must preserve the atomic transition, redaction,
  finite-retention and stale-reservation rules before it is supported.

## Alternatives rejected

**Check then insert.** Rejected because concurrent matching requests can both
run effects. **Global keys.** Rejected because they allow cross-capability and
cross-principal confusion. **Cache every canonical failure.** Rejected because
failure retention and authorization semantics need an explicit later decision.
**Store arbitrary Python results.** Rejected because serialization and
sensitive-data ownership would become hidden kernel behavior. **Use the
in-memory store as a production default.** Rejected because its lock and clock
cannot cross a process boundary or survive a restart.

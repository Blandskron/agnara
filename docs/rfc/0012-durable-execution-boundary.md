# RFC 0012 — Durable execution boundary

- Status: Open research; no implementation decision
- Date: 2026-11-01
- Tracking: [GitHub Issue #719](https://github.com/Blandskron/agnara/issues/719)
- Related: ADR 0087, ADR 0089, ADR 0091, ADR 0093, ADR 0094,
  RFC 0005, RFC 0011

## Purpose and current boundary

Determine whether Agnara needs a durable execution integration and what the
smallest useful boundary would be. The candidate is one persisted,
complete-result invocation recovered after a worker restart. Multi-step
workflows, scheduled jobs and resumable Python execution need separate decisions.

This is a proposal for a feasibility study, not application instructions or
authorization to implement a runtime. No package, backend, dependency, public
syntax or transport is selected. [Maturity](../MATURITY.md) owns current
implementation claims; [BACKLOG](../../BACKLOG.md) owns task state.

Current contracts provide useful components but no recovery guarantee:

- [Direct idempotency](../DIRECT_IDEMPOTENCY.md) can reuse a successful result
  with an explicit principal-bound selector. ADR 0089's store arbitrates
  reservations; it does not own admission, worker recovery or transactions.
  The reference store loses its records on restart.
- [Nested invocation](../NESTED_INVOCATION.md) owns awaited child calls within
  one compiled application. A restart does not resume that stack or reconstruct
  a child's resources, authority or confirmation evidence.
- [Host embedding](../INTEROPERABILITY.md) assigns lifecycle to the host.
  Detaching a task from a request does not persist it.
- [RFC 0011](0011-event-initial-projection.md) studies broker redelivery.
  Redelivery alone cannot establish whether a previous business effect committed.
  MCP/A2A task identifiers likewise do not establish durable execution.

## Options to evaluate

| Option | Useful property | Cost or limit |
| --- | --- | --- |
| Application-owned worker and persistence | Preserves existing explicit compiled invocation; requires no framework extension. | Each application owns admission, recovery and observability. This is the reference option. |
| Integration with an external execution engine | Reuses an engine's persistence and worker ownership. | Requires exact engine/SDK evidence, authority mapping and a lifecycle bridge; engine semantics cannot redefine capabilities. |
| Agnara-owned durable single-invocation adapter | Could standardize a narrow admission/attempt boundary across hosts. | Adds storage transitions, recovery operations, security and operational maintenance. Benefit must exceed an application recipe. |
| Kernel-owned workflow scheduler | Centralizes scheduling and multi-step orchestration. | Expands core responsibility and couples execution to persistence. Outside the proposed first study. |

Evaluate the application-owned option first as the least-locking experiment.
Compare a concrete external engine only if the experiment identifies a need.
Any later core port must serve a demonstrated shared semantic boundary, remain
transport-neutral and justify why an application or adapter contract is insufficient.

## Candidate feasibility profile

The constraints below are questions to prove in an isolated fixture. They are
not an accepted API or a promise of exactly-once effects.

### Admission and immutable intent

One submission selects one registered complete-result capability from a
known compiled application revision. Admission must authenticate and authorize
the submitter before persisting work. It must reject streaming, unsupported
input shapes, oversized records and operations whose authority cannot safely
be reconstructed. No message or record may name an arbitrary Python callable.

Persist a bounded, versioned representation of validated business inputs and
their canonical fingerprint, capability identity, application revision,
trusted tenant/principal reference, admission time, expiration and explicit
attempt policy. The experiment must specify its input codec and round-trip
validation; JSON conversion is not automatically lossless for Python values.
Never persist a container, dependency value, execution context, bearer token,
live principal object or confirmation evidence as a shortcut for reauthentication.
Do not deserialize executable objects or import paths supplied by a submitter.

Admission is acknowledged only after a durable commit. A lost acknowledgement
must have a defined duplicate-submission outcome scoped to verified principal,
tenant, capability and matching input fingerprint. Submission identifiers are
opaque lookup selectors, not authorization. Queue admission does not mean a
handler ran or an effect committed.

### Attempts and authority

Distinguish the durable submission from each worker attempt and the kernel's
execution identity (ADR 0087). Define their mapping explicitly. A repeated
attempt must not manufacture an ADR 0091 completed-success identity or imply
that a restarted Python stack continued.

Every attempt resolves current authority at a trusted host boundary and enters
the compiled plan, preserving policy and confirmation checks before invocation
dependency acquisition and handler effects. Stored scope lists, submitter
metadata and a worker's broad service account cannot impersonate the submitter.
Missing, revoked or ambiguous authority stops execution. Result lookup and
cancellation also require current authorization; knowing an identifier is
insufficient. Cross-tenant existence must not leak through errors.

The first fixture should reject confirmation-requiring capabilities rather
than persist or replay approval evidence. Delegation remains outside this
profile under [RFC 0005](0005-protocol-neutral-delegation.md). A future verified
approval channel or service-principal model requires a separate decision.

### Recovery and stale ownership

The store must atomically claim eligible work and compare an ownership
generation on renewal and every terminal transition. Test two independent
workers against the same record. An expired worker cannot overwrite a newer
attempt's result, release its claim or report its cancellation.

A lease proves storage ownership for a window; expiration does not prove that
the former worker stopped. Storage fencing alone cannot prevent that worker
from making an external business effect. The selected effect boundary must
enforce its own fencing, transaction or idempotency contract, or recovery must
stop for reconciliation. Never infer retry permission from `Idempotency.YES`,
timeout or a lost heartbeat.

The first experiment must classify these crash windows explicitly:

| Interruption point | Required observation and recovery constraint |
| --- | --- |
| Before admission commit | No acknowledged work; re-submission follows the defined admission deduplication rule. |
| Admission committed, acknowledgement lost | Matching re-submission resolves to the existing submission without a second admission. |
| Attempt claimed, before handler effects | Recovery revalidates authority and proves the prior worker can no longer effect work before any automatic re-execution. |
| Effect committed, result not durably recorded | Outcome is uncertain; do not report success or blindly repeat the effect. Reconcile through an application-owned effect identifier or halt for operator action. |
| Result committed, notification lost | Authorized lookup observes the same recorded result; notification retry does not invoke the handler. |
| Lease lost while former worker remains alive | Stale state transitions fail and the external-effect boundary prevents duplicate effects, or recovery stays suspended. |

The fixture must define an observable reconciliation state distinct from
ordinary failure. It must explain how an operator or application can resolve
uncertainty with evidence, authorization and an audit trail. A successful
storage write alone cannot prove a business transaction succeeded.

### Retry, cancellation and deadlines

Retry is an explicit, bounded application policy with an attempt limit,
backoff, total lifetime and reconciliation behavior. Map each canonical
failure category separately, preserving safe diagnostics. Authorization
denial, malformed input and missing confirmation must not enter a retry loop.
An internal failure or timeout is not proof that effects are absent.

Cancellation is a durable request to stop future work plus cooperative
interruption of an owned active attempt. Define the race with successful
completion atomically; a request does not establish that a handler stopped.
No cancellation response promises rollback of completed effects. Worker
shutdown, host disconnection and business cancellation are separate signals.

`Invocation.deadline` is a process-local absolute monotonic timestamp; never
persist it for another worker. Persist a separately defined expiration/budget,
specify the clock-skew and restart policy, then derive a fresh monotonic
deadline at attempt entry. Bound queue wait, attempt duration and cleanup
separately; cleanup remains cooperative under [the deadline contract](../DEADLINES.md).

### Version, data and lifecycle ownership

Bind stored intent to a deployment revision and input/output codec versions.
If a compatible compiled capability is unavailable after deployment, quarantine
the work rather than invoking a different signature or silently migrating
payloads. A migration needs explicit application ownership and validation.

Bound stored inputs, results, failures, audit data and retention. Filter result
and status serialization for the requesting principal. Logs and notifications
must not expose input secrets, exception text, lease tokens or policy internals.
Define deletion and expired-record behavior; losing a record does not authorize
another business effect. A stored success is never authority for result reuse.

The host owns workers, persistence clients and their event loop. Use bounded
structured concurrency: stop claims, finish or cancel owned attempts under a
shutdown budget, join them, close clients and finally close the container.
Persist unfinished/uncertain state as required; never acknowledge completion
because the process is exiting. Core acquires no scheduler, database, broker,
background task or protocol dependency.

## Evidence gates and possible follow-up Issues

Each slice requires a separately scoped Issue and review. This RFC does not
activate implementation, change supported protocols or select a distribution.

| Slice | Evidence required before closure |
| --- | --- |
| DUR-01: application-owned feasibility | One complete-result capability, one real persistence backend and a simulated independently recorded business effect; exact Python/dependency/platform versions, commands and retained results. Use two worker processes and forced process termination, not only mocks or coroutine cancellation. Cover every crash-window row, authority revocation, version mismatch, bounds and shutdown. Report unresolved effect uncertainty explicitly. |
| DUR-02: boundary comparison and decision | Compare the application recipe against one engine integration if warranted. Record measured complexity, lifecycle and recovery differences, operational ownership and limits. An ADR selects retain/defer/reject or a narrow adapter contract, with explicit identity, authority, fencing, clocks and reconciliation semantics. |
| DUR-03: implementation proposal | Only after DUR-02: scoped runtime/API proposal, storage conformance tests, threat analysis, package-boundary review and migration/retention policy. An external SDK belongs only at its integration boundary. |
| DUR-04: governed consumer evidence | Only after an implementation decision: public manifest and import audit, installed-wheel consumer, restart/concurrency evidence in CI, runnable guide and precise maturity update. Transport-specific admission/status/cancel projections require their own decisions. |

Acceptance is evidence of honest outcomes under failure, not a throughput
target. A no-go result is valid if correct recovery requires a larger contract
than the demonstrated use case justifies. No isolated successful restart
establishes production readiness or a general workflow guarantee.

## Decisions still open

1. Does an application recipe solve the demonstrated need without a new
   framework-owned runtime or storage port?
2. What effect boundary can reconcile a crash after effect commit and before
   result commit, and what must stay suspended when that evidence is missing?
3. Which principal can each delayed attempt legitimately act as, and how is
   revocation observed without persisting credentials or delegating authority?
4. Which backend, clock model and ownership mechanism can prove the proposed
   admission and recovery transitions under a real process failure?
5. What is the minimum deployment-version and retention policy that prevents
   silently reinterpreting old work or repeating forgotten effects?

Answers belong in a later ADR and executable Issues. The existing direct
runtime, idempotency store and nested invocation contracts remain the current
application instructions.

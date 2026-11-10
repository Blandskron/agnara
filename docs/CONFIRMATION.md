# Verifying confirmation before execution

A capability with `confirmation="required"` needs evidence verified by the
application before it can run. Confirmation does not grant scopes or replace
authentication. A caller-controlled `confirmed` flag is never proof.

## Run the example

From the repository root with Python 3.14:

```bash
uv sync
uv run python examples/confirmation.py
```

The complete [example](../examples/confirmation.py) uses governed public APIs
without a server or external service. It simulates approval and one catalog
effect; no real user decision is collected and no catalog data is changed.

```text
missing: interaction_required
metadata_flag: interaction_required
forged: forbidden
changed_input: forbidden
other_actor: forbidden
scope_lost: forbidden
approved: Archived A-1: retired
replay: forbidden
expired: forbidden
effects: ['resource.open', 'archive:A-1', 'resource.close']
```

Only the approved invocation opens the dependency and records the simulated
effect. The invocation-scoped generator provider then closes its resource.

## Compose the verifier explicitly

The example declares `catalog.archive` with a scope, required confirmation
and `output=str`. Its application-owned `DemoAuthority` implements the public
`ConfirmationVerifier` protocol. The plan receives that verifier at startup:

```python
from agnara.execution import ExecutionContext, ExecutionPlan, invoke_result

plan = ExecutionPlan.compile(
    capabilities["catalog.archive"], dependencies, confirmation_verifier=authority
)
result = await invoke_result(
    plan,
    ExecutionContext(
        invocation, container, principal=actor, confirmation_evidence=evidence
    ),
)
```

This excerpt uses the objects explicitly constructed in the example. A required
confirmation declaration without a verifier fails at compilation. The host
authenticates the actor before constructing `Principal`; the demonstration's
Alice and Bob are fixed fixtures, not an authentication implementation.

The plan evaluates declared scopes first, then application policies and the
confirmation requirement, before input validation, dependency resolution and
handler work. Even genuine confirmation evidence cannot authorize an actor
whose scope has been removed. The verifier sees the unvalidated invocation,
so it independently checks the exact input shape it approves.

## Bind evidence to an exact decision

The demonstration authority creates a random opaque reference and keeps an
immutable local record of capability, actor identity, both input strings and
expiry. Its trusted `approve` method is called only by the composition root
to simulate an already approved decision. It is not a caller-facing API.

`ConfirmationEvidence(reference)` only wraps a value. The wrapper does not
prove approval. The verifier checks its local record, rejects a different
capability, actor, argument shape or value, and enforces inclusive expiry.
Changing `sku` or `reason` requires a new approval. Invocation metadata has no
role in this decision.

An `asyncio.Lock` makes lookup, validation and single-use consumption one
atomic operation among tasks on the authority's event loop. Tests submit
simultaneous attempts using a task group and verify exactly one succeeds.
This lock offers no cross-thread or multi-process coordination.

The reference is consumed when confirmation passes, before input validation
or the effect. A later validation, resource, handler or cancellation failure
does not restore it. This example deliberately requires fresh approval for
another attempt. Approval consumption is not a transaction with the business
effect and does not provide exactly-once execution or idempotency; see the
[direct idempotency guide](DIRECT_IDEMPOTENCY.md) for the separate contract.

## Request interaction or deny evidence

Missing evidence produces `FailureCode.INTERACTION_REQUIRED` with a caller-safe
confirmation request. The `metadata_flag` case produces the same result, even
though it carries `{"confirmed": true}`. No verifier or handler runs there.

Supplied but forged, mismatched, expired or already consumed evidence produces
`FORBIDDEN`, rather than another interaction request. Unexpected verifier errors
fail closed with a redacted internal failure. Outcomes do not expose the
reference, approval record or verifier diagnostics; the example prints only
failure codes and the successful application value.

Interaction required ends this invocation. A host may collect and verify a
decision separately, then start a new invocation with evidence. It does not
resume a suspended handler. `ExecutionContext` fixes its confirmation evidence
at construction; there is no in-handler approval API or durable pending task.

## Demonstration limits

The authority stores records in one process and belongs to one event loop.
Its injected clock allows expiry tests without sleeping. Records vanish on
restart, and it has no durable audit, external approval channel, revocation
service or deployment-wide replay protection. The small fixed scenario is not
a general approval server.

A production authority must independently authenticate approvers, establish
their authority to approve the operation, persist and atomically consume the
decision where needed, and define canonicalization, expiry, revocation,
delegation and retry rules. An API client must never gain access to the trusted
issuance method merely by submitting inputs. Core owns none of that service;
it supplies the verifier boundary and enforces its verdict before effects.

See ADR 0024, the [API design contract](API_DESIGN.md) and
[security guidance](../SECURITY.md) for the governing boundaries.

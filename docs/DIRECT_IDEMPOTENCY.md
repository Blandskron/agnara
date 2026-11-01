# Direct idempotency

Agnara can reuse a successful direct invocation when the application supplies
an explicit idempotency option. The [runnable example](../examples/direct_idempotency.py)
shows this with a simulated order capture. It makes no payment or network call.

## Run it

From the repository root with Python 3.14:

```bash
uv sync
uv run python examples/direct_idempotency.py
```

The result is:

```text
first: receipt-1
duplicate: receipt-1
changed_input: conflict
permission_lost: forbidden
other_principal: receipt-2
effects: [('A-1', 2500), ('A-1', 2500)]
concurrent_first: receipt-1
concurrent_contender: conflict
concurrent_permission_lost: forbidden
concurrent_duplicate: receipt-1
concurrent_effects: [('A-1', 2500)]
```

The duplicate returns the first receipt and retains its logical execution
identity; the handler runs once for Alice. Reusing the key with a different
amount conflicts. Losing `orders:write` blocks reuse because policy runs again
before the store is consulted. Bob can use the same key because his verified
principal identity defines a separate namespace.

## Observe a concurrent contender

The second demonstration, `demonstrate(concurrent=True)`, uses a fresh runtime
and process-local store on the same event loop. A task group owns the first
invocation. Its handler signals entry, then waits on an event before recording
the simulated effect. While that invocation holds the reservation, the caller
awaits a second invocation with the same principal, key and fingerprint.

The contender returns `FailureCode.CONFLICT` with the safe message
`idempotency request is already in progress`. It does not wait for the receipt
or enter the handler. This differs from the sequential changed-input conflict,
whose message identifies a different request. An unscoped matching caller is
still forbidden while the reservation is held: policy precedes store lookup.

The caller then releases the first handler and awaits its success. A later
duplicate reuses that receipt and logical execution identity. The refusal has
its own execution identity; it does not disclose the holder's identity. Exactly
one simulated effect is recorded in this second demonstration.

Events establish the overlap without sleeps or a race over scheduling. A
five-second watchdog fails the demonstration if it cannot progress. Task-group
exit joins or cancels owned work before the runtime closes in `finally`.
The watchdog is separate from the example's lease TTL; this does not test
lease expiry or prove a bound on arbitrary handler or cleanup code.

## What the application owns

The example compiles `orders.capture` once, then constructs each
`ExecutionContext` with a fresh `Invocation` and explicit
`IdempotencyInvocation`. Its `IdempotencyScope` binds four inputs:

- the compiled capability identity;
- the authenticated principal identity;
- an approved selector key for this logical attempt;
- a SHA-256 fingerprint of a canonical form containing every caller-controlled
  business input.

The caller's metadata and correlation IDs are never treated as selectors or
authentication. In an actual host, authenticate the caller before creating
`Principal`, authorize the operation, and decide which caller key to accept.
Keep the fingerprint serialization stable across processes and deployments.

The application also owns the result codec. `ReceiptCodec` encodes only this
capability's successful receipt string. A stored success is never permission
to skip current policy or confirmation checks. Failures and cancellations are
not cached; storage or codec failures fail closed rather than repeating an
effect automatically.

`InMemoryIdempotencyStore` is a process-local demonstration store: it loses
records on restart and cannot coordinate multiple workers. The TTL values are
example values, not deployment guidance. A durable store must preserve the
atomic claim, completion, expiry and stale-reservation rules from
[ADR 0089](adr/0089-pluggable-idempotency-storage.md).

## Scope

This is the implemented **direct, complete-result** path from
[ADR 0091](adr/0091-operational-idempotency-runtime.md). Agnara's HTTP
and MCP adapters do not accept an idempotency selector. It does not add a
retry policy, durable execution or transaction ownership.

## Validation evidence

The installed candidate-wheel lane in
`tests/release/test_integrated_dogfooding.py` copies this exact example outside
the checkout and loads it under Python `-I`. Its consumer checks canonical
successes and refusals, nonempty execution identities, duplicate identity reuse,
principal isolation and the exact two sequential effects. It also runs the
concurrent scenario, checking the complete in-progress refusal, denial, later
receipt/identity reuse and exactly one effect. Negative proofs in
`tests/release/test_direct_idempotency_guide_artifact.py` reject missing or extra
outcomes, changed receipts, incorrect identities/refusals, leaked holder identity
or diagnostics, and missing or extra effects. The focused guide tests separately
verify runtime closure and joined tasks after success, owner error and cancellation.

Run the focused checks with:

```bash
uv run pytest tests/docs/test_direct_idempotency_example.py tests/release/test_direct_idempotency_guide_artifact.py tests/release/test_integrated_dogfooding.py
```

This is sequential and event-gated concurrent evidence in one process and one
event loop. It does not validate threads, multiple workers, durable storage,
lease expiry, restart recovery or HTTP/MCP selectors. No surviving tasks are
permitted; independent runtime/resource-close checks remain checkout-test
evidence. See the [coverage matrix](INTEROPERABILITY.md#installed-candidate-wheel-guide-coverage)
for the shared provenance and public-import gates.

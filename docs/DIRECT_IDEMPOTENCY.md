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
```

The duplicate returns the first receipt and retains its logical execution
identity; the handler runs once for Alice. Reusing the key with a different
amount conflicts. Losing `orders:write` blocks reuse because policy runs again
before the store is consulted. Bob can use the same key because his verified
principal identity defines a separate namespace.

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

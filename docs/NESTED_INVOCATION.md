# Calling another capability

Use `CapabilityInvoker` when a handler needs to invoke a capability from the
same compiled application. The child executes its compiled plan, including
authorization, input validation and dependency cleanup.

## Run the example

From the repository root with Python 3.14:

```bash
uv sync
uv run python examples/nested_invocation.py
```

The complete [example](../examples/nested_invocation.py) imports only governed
public APIs and needs no server or external service. Its output is:

```text
authorized: Summary: A-1: widget; handlers=['summary', 'product']
child denied: Product unavailable: forbidden; handlers=['summary']
parent denied: forbidden; handlers=[]
```

## Compose at startup

1. Register `catalog.summary` and `catalog.product` on one `Agnara` application.
2. Freeze the registry with `app.compile()`.
3. Compile each definition into an `ExecutionPlan` with the same `DIRegistry`.
4. Construct `CapabilityRuntime` with that snapshot, its plans and the
   application-owned `DIContainer`.
5. Invoke the parent through `runtime.invoke_result(context)` and close the
   runtime in `finally` with `await runtime.aclose()`.

The summary handler explicitly requests `CapabilityInvoker`. It awaits
`invoker.invoke(CapabilityId.parse("catalog.product"), {"sku": sku})` to enter
the child's plan. Calling the Python `product` function directly would bypass
the child's capability policies and lifecycle.

## Read the outcomes

The summary requires `summary:read`; the product requires `catalog:read`.
Having the first scope allows the parent handler to run but does not authorize
the child. The example records handler calls so the denied paths demonstrate
that the protected code did not execute.

The child returns a canonical `Success` or `Failure` to its parent. This
example deliberately maps a child failure into a fallback summary string.
Consequently the outer invocation succeeds with `Product unavailable:
forbidden`; this does not mean the child succeeded. Applications must choose
their own business behavior for an unavailable child.

The principals are local fixtures. A real application must authenticate callers
at its host boundary and construct their authority from verified identity.

## Ownership and limits

Each child receives a fresh execution context, identity and invocation DI
scope, and evaluates its own policy. Parent confirmation evidence and
idempotency configuration do not propagate. A child deadline can only shorten
the parent's deadline; cancellation propagates through awaited child work.

This contract supports complete results in the same compiled application.
Streaming children, cross-application calls and delegation are unsupported.
It provides no durable workflow, transaction or automatic retry mechanism.
See [ADR 0093](adr/0093-nested-capability-invocation-contract.md) and
[current maturity](MATURITY.md) for the full boundary.

## Verify

```bash
uv run pytest tests/docs/test_nested_invocation_example.py
uv run python scripts/check_public_imports.py examples/nested_invocation.py
```

The installed candidate-wheel lane in
[`tests/release/test_integrated_dogfooding.py`](../tests/release/test_integrated_dogfooding.py)
also copies this exact example unchanged into an external consumer directory.
It runs under Python `-I` after all seven local wheels are installed together,
with installed-package provenance and governed imports checked separately.

The structured consumer calls `demonstrate` for the three principal cases
above and an additional caller with no scopes. It validates exact canonical
outcomes, including successful parent fallback when the child is denied,
nonempty distinct root execution identities and independent ordered handler
traces. Parent denial runs neither handler; child denial runs only the parent.
Execution is bounded and each case must leave no additional tasks running.
Negative validation proofs reject changed results, leaked refusal diagnostics,
shared/missing identities, changed effects and shared mutable trace lists:

```bash
uv run pytest tests/release/test_nested_invocation_guide_artifact.py
uv run pytest tests/release/test_integrated_dogfooding.py
```

This is evidence against wheels built from the reviewed candidate source,
not against previously published PyPI artifacts. The guide consumer observes
root identities and handler effects; it does not independently verify child
context/identity, DI resource closure, cancellation or deadlines. Those remain
core execution-test evidence. It adds no transport, host or delegation support.

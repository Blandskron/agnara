# RFC 0001 — Capability Runtime

- Status: Draft
- Target: v0.1 architecture
- Decision owner: Project maintainer

## Summary

Agnara models application behavior as protocol-neutral capabilities and compiles them into transport-independent execution plans.

## Motivation

HTTP routes are delivery mechanisms, not domain capabilities.

An operation such as `create_customer` may be called from HTTP, MCP, A2A, a task worker or another capability. Validation, dependency resolution, security, telemetry and business behavior should not be reimplemented for every surface.

## Proposed API

First-pass design target:

```python
from agnara import Agnara, Context

app = Agnara("example")


@app.capability(
    description="Create a customer",
    scopes={"customers:create"},
    effects={"database-write"},
    idempotent=False,
)
async def create_customer(
    command: CustomerCreate,
    ctx: Context,
) -> Customer:
    ...
```

Transport exposure is separate:

```python
http = app.use(Http())
mcp = app.use(Mcp())

http.post("/customers", create_customer)
mcp.tool(create_customer)
```

An alternative fluent API may be explored:

```python
app.expose(create_customer).http.post("/customers")
app.expose(create_customer).mcp.tool()
```

No syntax becomes stable until the golden API examples have been reviewed.

## Capability identity

A capability requires a stable logical identifier independent of transport.

Default:

```text
<application-namespace>.<python-qualified-name>
```

Explicit IDs must be supported for refactors.

Transport names may differ from capability IDs.

## Inputs

The first release should prefer a simple rule:

- ordinary typed parameters are capability inputs;
- dependency injection requires explicit markers;
- framework context requires an explicit `Context` type or injection marker.

Avoid inference rules that are clever but ambiguous.

## Outputs

The output annotation defines the canonical output contract when present.

The framework must distinguish:

- no output annotation;
- `None`;
- streaming output;
- task handle;
- structured value.

## Effects

Capabilities may declare effects.

Initial vocabulary should remain open but standardized core values may include:

```text
none
read
cache-write
database-write
external-write
financial-write
destructive
```

Do not pretend a string label alone is a security guarantee.

## Risk

Suggested initial levels:

```text
low
medium
high
critical
```

Risk is metadata consumed by policy engines and agent discovery. It does not replace authorization.

## Confirmation

Suggested values:

```text
never
policy
required
```

The runtime must support a protocol-neutral "interaction required" state before protocol adapters can map it to MCP/A2A/HTTP-specific behavior.

## Idempotency

Values:

```text
true
false
unknown
```

Using `unknown` is preferable to falsely claiming idempotency.

## Long-running capabilities

Do not overload ordinary return types.

Task execution should be a distinct capability/exposure mode and introduced after the synchronous/direct execution model stabilizes.

## Dependency model

Dependency injection is an execution concern, not an HTTP concern.

Conceptual declaration:

```python
async def create_customer(
    command: CustomerCreate,
    db: Inject[Database],
) -> Customer:
    ...
```

Final syntax is undecided.

## Execution plan

A capability is compiled before runtime into an immutable plan.

A plan owns:

- argument binders;
- validators;
- dependency providers;
- policy evaluators;
- handler;
- output adapter;
- telemetry metadata.

## Invocation

Direct invocation must be first-class:

```python
result = await app.invoke(
    create_customer,
    command=customer,
    context=test_context,
)
```

This makes transport-independent tests the default.

## Error model

Core exceptions must not be HTTP exceptions.

Candidate categories:

```text
InvalidInput
Unauthenticated
Forbidden
NotFound
Conflict
RateLimited
InteractionRequired
Unavailable
Timeout
InternalFailure
```

Mappings belong to adapters.

## Rejected design: route as core primitive

Rejected because it permanently centers HTTP and forces other protocols to adapt to HTTP semantics.

## Rejected design: MCP tool as core primitive

Rejected for the same reason.

## Rejected design: LLM agent as core primitive

Agnara executes capabilities. Agent reasoning engines are consumers/composers, not part of the execution kernel.

## Open questions

1. Exact input/dependency annotation syntax.
2. Whether schema validation occurs before or after dependency construction.
3. How partial streaming failures are represented.
4. Canonical authorization principal model.
5. Public delegation runtime types and verifier API; the security model is
   defined by RFC 0004.
6. Unified interaction-required state.
7. Capability versioning.
8. Sync handler execution strategy.

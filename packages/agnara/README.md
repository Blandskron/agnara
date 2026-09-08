# agnara

> **Capability-native Python for the agentic era.**

Agnara is a Python 3.14-native capability framework for services meant to be
consumed by humans, applications and AI agents without making HTTP the centre
of the architecture. A capability is declared once, with its effects, risk and
confirmation requirements, and later exposed through whichever protocol the
caller needs.

This distribution is `agnara`, the capability-first, transport-neutral
execution kernel: the capability model, registry, execution context,
dependency graph, policies, execution planning and canonical errors. It
depends on nothing but the standard library.

## Status: alpha

This is the `0.1.0a4` application alpha, which adds public application and
exposure boundaries and builds the synchronized adapter set alongside the
kernel. It is **not production-ready**, the public API may change without a
deprecation cycle, and it makes no claim of protocol conformance, benchmark
leadership or security guarantees.

Which versions are on PyPI is answered by the project page rather than by this
file. `CHANGELOG.md` records what each version contains.

## Install

```bash
pip install agnara
```

Every published version so far is a pre-release, so this resolves to the newest
alpha without a version pin or `--pre`. Pin explicitly when a build must not
move:

```bash
pip install "agnara==0.1.0a4"
```

Requires CPython 3.14 or newer.

## Quick start

```python
import asyncio

from agnara import Agnara, Risk, StandardEffect
from agnara.core.di import DIContainer, DIRegistry
from agnara.policy import Principal
from agnara.execution import (
    ExecutionContext,
    ExecutionPlan,
    Invocation,
    invoke_result,
)

app = Agnara("billing")


@app.capability(
    description="Refund a captured payment.",
    scopes=("billing:write",),
    effects=(StandardEffect.FINANCIAL_WRITE,),
    risk=Risk.HIGH,
)
def refund(payment_id: str, amount_cents: int) -> str:
    return f"refunded {amount_cents} cents for {payment_id}"


async def main() -> None:
    capabilities = app.compile()
    dependencies = DIRegistry()
    plan = ExecutionPlan.compile(capabilities["billing.refund"], dependencies)

    outcome = await invoke_result(
        plan,
        ExecutionContext(
            Invocation(
                capability_id=plan.definition.id,
                payload={"payment_id": "pay_123", "amount_cents": 2500},
                metadata={},
            ),
            DIContainer(dependencies),
            principal=Principal("quickstart", scopes={"billing:write"}),
        ),
    )
    print(outcome)


asyncio.run(main())
```

The declared function is returned unchanged, so it stays directly callable and
directly testable. Registration is a side effect on the application, not a
transformation of the function.

## What this release includes

- capability declaration and a deterministic, freezable registry;
- stable capability identity, plus effect, risk, idempotency and confirmation
  metadata;
- a schema port with a standard-library adapter and compiled per-parameter
  input validation;
- dependency injection with compile-time graph validation and scoped
  resolution;
- execution plans, direct invocation and optional monotonic deadlines;
- protocol-neutral policies, principals and scope evaluation;
- canonical `Success` / `Failure` outcomes with stable failure codes;
- protocol-neutral introspection snapshots and explicit discovery visibility;
- structured execution telemetry hooks with per-invocation identity.

## What it does not include

The HTTP/ASGI, OpenAPI, MCP, CLI and OpenTelemetry functionality lives in
separate distributions -- `agnara-http`, `agnara-mcp`, `agnara-cli` and
`agnara-telemetry` -- and is not bundled into this standard-library-only
kernel. Each is versioned in step with this one; check its PyPI project page
for the versions available to install. Events and A2A remain zero-API reserved
namespaces.

## Frozen value semantics

Core value types such as `CapabilityId` and `CapabilityDefinition` are
immutable and slotted. Assigning or deleting either a declared field or an
unknown attribute raises `dataclasses.FrozenInstanceError`; a typo never
attaches new state and does not leak CPython's internal slots error.

## Confirmation boundary

Capabilities declared with `confirmation="required"` need an
application-provided `ConfirmationVerifier` when their `ExecutionPlan` is
compiled. Each invocation may carry an explicit opaque `ConfirmationEvidence`
on `ExecutionContext`; values in generic invocation metadata are not approval.

The verifier receives the exact capability id, invocation, and principal and
owns authenticity, input canonicalization, expiry, and replay protection.
Missing evidence terminates execution with an interaction request. Rejected
evidence terminates it as forbidden. Both outcomes occur before dependency
construction or handler effects, and `invoke_result()` maps them to stable
protocol-neutral failure codes.

## Telemetry hooks

The core port is `agnara.execution.TelemetryHook`, with synchronous
`on_invocation_start(InvocationStartEvent)` and
`on_invocation_terminal(InvocationTerminalEvent)` callbacks. Register observers
with `ExecutionPlan.compile(definition, registry, hooks=[observer])`; inheriting
from the protocol is optional. Events expose capability, invocation and tracking identity;
terminal events also contain monotonic duration and execution outcome, without
handler inputs, returned payloads or exception objects.

Both plan construction paths copy the hook collection to a tuple. Missing or
non-callable callbacks, coroutine functions and generator functions fail at
startup with `DefinitionError`. Valid callbacks accept one event, return `None` synchronously
and must not block. Their ordinary exceptions are ignored during execution.

Observers own synchronization of their mutable state and must keep their
callbacks stable after compilation. Tracking IDs are caller-provided and may
repeat; they are not unique span identifiers and should contain no secrets.
Exporter startup, flushing and shutdown belong to adapters, not the core
runtime. The separate `agnara-telemetry` package provides metrics and tracing
hooks over an application-supplied meter and tracer.

**Migration:** `docs/MIGRATION_a3_to_a4.md` covers every user-visible change
from `0.1.0a3`. For the hook types specifically, code constructing
`InvocationStartEvent` or `InvocationTerminalEvent` has had to supply
`invocation_id` since `0.1.0a3`. Use the same identity for matching
start/terminal events; `tracking_id` is not unique. Hooks that only read events
are unaffected, and plans without hooks skip event construction entirely.

## Links

- Source, architecture and decision records:
  <https://github.com/Blandskron/agnara>
- Changelog:
  <https://github.com/Blandskron/agnara/blob/main/CHANGELOG.md>
- Architecture:
  <https://github.com/Blandskron/agnara/blob/main/ARCHITECTURE.md>
- Longer example:
  <https://github.com/Blandskron/agnara/blob/main/examples/quickstart.py>

## License

Apache License 2.0.

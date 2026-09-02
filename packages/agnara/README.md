# agnara-core

Capability-first, transport-neutral execution kernel. Owns the capability model, registry, execution context, dependency graph, policies, execution planning and canonical errors.

- Import package: `agnara`
- Depends on: nothing (standard library only)
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

## Frozen value semantics

Core value types such as `CapabilityId` and `CapabilityDefinition` are
immutable and slotted. Assigning or deleting either a declared field or an
unknown attribute raises `dataclasses.FrozenInstanceError`; a typo never
attaches new state and does not leak CPython's internal slots error.

The internal construction rule and memory evidence are recorded in
`docs/adr/0020-reliable-frozen-slotted-value-types.md`.

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

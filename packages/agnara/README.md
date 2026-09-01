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

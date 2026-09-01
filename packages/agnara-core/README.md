# agnara-core

Capability-first, transport-neutral execution kernel. Owns the capability model, registry, execution context, dependency graph, policies, execution planning and canonical errors.

- Import package: `agnara`
- Depends on: nothing (standard library only)
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

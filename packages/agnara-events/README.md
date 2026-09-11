# agnara-events

Reserved namespace for future event exposure abstractions and AsyncAPI projection.

This baseline package deliberately has no public API or event runtime. It is
built and versioned with the synchronized workspace set to reserve the official
package boundary, not to claim broker or AsyncAPI support.

- Import package: `agnara_events`
- Depends on: the exact synchronized `agnara` version
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

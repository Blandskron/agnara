# ADR 0048 — One Discovery Path for Every CLI Introspection Command

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #194 (E8.5)

## Context

E8.5 asks for `agnara graph` "over the same snapshot without a second
discovery path". The obvious implementation is the wrong one: the relationship
data lives in a `DIRegistry`, and walking it directly would be shorter than
reading a filtered snapshot. It would also answer differently from
`agnara inspect` under the same visibility decision — showing providers a
viewer was not shown, or wiring for a capability that viewer cannot see — and
nothing would reveal the difference until it mattered.

The same trap waits for every command EPIC 8 still has to add: `agnara apps`,
`agnara capabilities`, `agnara doctor`. Deciding it once per command is how
surfaces drift.

## Decision

`agnara_cli._view` is the only way a command obtains introspection data. It
owns the shared arguments (`target`, `--path`, `--dependencies`,
`--visibility`, `--as-scope`, `--hide`), resolves the target, describes the
application once and filters once, and returns a `View`: the filtered
snapshot, the `DiscoveryVisibility` that produced it, and the resolved target.

A command adds its arguments with `add_view_arguments` and calls
`resolve_view`. It never calls `describe_app`, `filter_snapshot` or the DI
registry itself. `agnara graph` therefore cannot see a provider `agnara
inspect` withheld, because it is reading the same object.

The `View` carries the visibility decision, not only the snapshot, because a
snapshot alone cannot distinguish a value that was never declared from one
that was withheld. `agnara graph` uses that to report a withheld relationship
source instead of drawing an empty tree that would read as "this application
has no dependencies".

Two rendering decisions follow from the same honesty rule. An unreferenced
provider is computed transitively, because a provider that exists only to
satisfy another provider is used, and listing it as unreferenced would be a
false claim. A dependency whose type has no published provider is drawn as
"no provider published" rather than as a leaf, so a withheld or missing
provider is visible rather than indistinguishable from a root.

An architecture-style test asserts that `inspect` and `graph` expose the same
visibility controls, differing only by `--json`. A command that quietly
offered a different set would be a trap for an operator who learned the flags
on one of them.

## Alternatives

- Walk the `DIRegistry` in `graph`: rejected. It is the second discovery path
  E8.5 explicitly forbids, and it would silently ignore the visibility
  decision.
- Give each command its own arguments: rejected because the drift is invisible
  until an operator's flag is silently absent on one command.
- Pass only the snapshot to renderers: rejected because withheld and undeclared
  become indistinguishable, and the renderer would assert facts the filter
  removed.
- Emit DOT or Mermaid: deferred. A machine-readable graph should come from
  `agnara inspect --json`, which already carries the provider edges; adding a
  second serialization now would create the divergence this ADR exists to
  prevent.

## Evidence and limits

`tests/cli/test_graph.py` covers transitive provider trees, a capability with
no dependencies, transitive reachability of providers, hiding changing what is
reachable, a withheld relationship source being reported rather than drawn,
the empty result, agreement with `agnara inspect --json` under one visibility
decision, a scoped viewer seeing neither a capability nor its wiring, the
absence of ANSI decoration, the shared failure contract, and the shared
argument set.

Limits: one application per invocation, no project-level graph, no export
format, and no `agnara apps`, `capabilities` or `doctor`. Cycle protection in
the renderer is defensive — `compile_dag` rejects a cycle before a plan
exists — and is not evidence that a cyclic snapshot is supported.

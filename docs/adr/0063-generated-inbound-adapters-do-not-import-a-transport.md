# ADR 0063 — A Generated Inbound Adapter Does Not Import a Transport

- Status: Proposed
- Date: 2026-09-06
- Tracking: GitHub Issue #246 (E0A.6)

## Context

`docs/SCAFFOLDING.md` specifies `--with`:

> `adapters/inbound/` is created as a documented, empty package. Only requested
> inbound adapters are added, and `--with` is E0A.6.

and states the invariant "No MCP import appears outside the MCP adapter
file/package".

The obvious reading is that `agnara app create payments --with http` generates
an adapter that imports `agnara_http` and registers routes. Three facts,
verified on `develop` before this change, rule that out.

| exposure | distribution | public surface |
| --- | --- | --- |
| `mcp` | `agnara-mcp` | 20 names |
| `http` | `agnara-http` | `__all__ = []` |
| `a2a` | `agnara-a2a` | `__all__ = []` |
| `events` | `agnara-events` | `__all__ = []` |
| `tasks` | — | no distribution exists |

1. **No adapter distribution is published.** Only `agnara` is on PyPI; every
   adapter returns 404. A generated project declares
   `dependencies = ["agnara"]`, so an adapter import produces a project that
   cannot be installed.
2. **`agnara-http` has no public API on purpose.** ARCHITECTURE.md section 3
   records why: its composition API is still the golden-design sketch in
   `docs/API_DESIGN.md` section 4. Generating `from agnara_http._dispatch
   import _HTTPExposure` would put private names into user code and freeze a
   surface we have deliberately not committed to.
3. **`a2a` and `events` are reserved namespaces with no implementation, and
   `tasks` has no package at all.** There is nothing to import.

Generating a working adapter for `mcp` and something else for the other four
would make `--with http` — the most-cited example in `docs/CLI_SPEC.md` — the
worst-served case.

## Decision

A generated inbound adapter imports **only this app's application layer**. It
names the capabilities it projects, records what the protocol projects them
*as*, and documents the wiring the developer performs when they add the
adapter dependency.

```python
from depot.apps.payments.application.capabilities import get_record, list_records

__all__ = ["EXPOSED"]

EXPOSED: tuple[Callable[..., Any], ...] = (get_record, list_records)
```

`EXPOSED` is a real seam, not a placeholder: it is the list an adapter
iterates, and it keeps "which capabilities does this protocol serve?"
answerable in one place, in the layer that owns the protocol.

### Consequences of the decision

- `docs/SCAFFOLDING.md`'s invariant holds **by construction** rather than by
  convention. No transport import appears anywhere in a generated project, so
  it cannot appear outside its own adapter file.
- A generated project installs with `agnara` alone, whatever `--with` was
  passed.
- The five exposures have one uniform shape, so `--with http` is as well
  served as `--with mcp`.
- We commit to no adapter API before those APIs are public. When
  `agnara-http` graduates a public surface, this template gains real wiring
  without any generated project having depended on a private name in the
  meantime.

The cost is that the generated adapter does not serve traffic. That is honest:
neither does the adapter distribution it would have imported, from a user's
point of view, because they cannot install it.

## The manifest records what was scaffolded

`exposures` was written as `[]` regardless of what `--with` asked for — the
same declared-versus-actual defect ADR 0062 closed for `architecture`.
`agnara apps` reports this field without importing anything, so it has to
describe the app. The resolved exposures are now written to it.

Order is the order given, with repeats dropped. A manifest preserves what its
author wrote, and `--with http,mcp` should read back as it was typed.

## `minimal` refuses an exposure

The minimal architecture has no `adapters/` package; `docs/SCAFFOLDING.md`
fixes its layout at four files. Giving it an inbound adapter would make it the
modular-hexagonal template under another name.

`--with` on a minimal app is therefore refused, naming the flag that resolves
it. Creating the adapters package silently, or ignoring `--with`, would both
leave the manifest describing something the directory contradicts — which is
the failure ADR 0062 exists to prevent.

## Alternatives considered

**Import the adapter distributions and add them to the generated project's
dependencies.** Rejected: the project would not install, since no adapter is
on PyPI.

**Generate a working adapter for `mcp` only, refuse the rest.** Rejected:
`--with http` is the primary example in `docs/CLI_SPEC.md`, and one working
adapter beside four refusals is a worse scaffolder than five consistent ones.

**Import private names from `agnara-http`.** Rejected. It would commit user
code to a surface ARCHITECTURE.md section 3 explicitly records as not ready,
and generated code is the worst place to leak one.

**Record exposures without generating files.** Rejected: `docs/SCAFFOLDING.md`
states that requested inbound adapters are added, and an app whose manifest
claims an exposure with nothing in `adapters/inbound/` reintroduces exactly
the mismatch this and ADR 0062 remove.

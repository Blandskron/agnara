# ADR 0047 — `agnara inspect` and the CLI Entry Point

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #192 (E8.3, E8.4)

## Context

E8.1 and E8.2 delivered the introspection snapshot and the visibility layer,
and nothing read them. `agnara-cli` was an empty package with a docstring, so
the first command also has to establish the entry point, the exit-code
contract and the way a command finds an application.

Finding an application is the hard part. `agnara.toml` and the project runtime
(E0A.2, EPIC 1A) do not exist, so there is nothing to discover a project from.

`docs/CLI_SPEC.md` constrains the rest: text and `--json` must consume the same
filtered protocol-neutral snapshot, inspection must not infer its model from
OpenAPI, machine output needs an explicit format version, deterministic
ordering, defined exit codes and no ANSI decoration, and offline inspection is
not permission to dump what a publication policy withholds.

## Decision

`agnara` is a console script and `python -m agnara_cli` runs the same code.
Arguments are parsed with `argparse` from the standard library.

Exit codes are decided once, in `_main`: `0` when the command produced its
answer — including the answer "nothing is visible" — `1` when the operator's
input or application could not be used, and `2` when argparse rejects the
command line. A `TargetError` becomes one diagnostic line on stderr. Anything
else propagates, because a defect in this CLI that prints as a tidy message is
a defect nobody reports.

An application is named explicitly as `module:attribute`, the convention
`uvicorn` and `gunicorn` established. A malformed target is rejected before
anything is imported, because importing a target executes the user's module;
that is inherent — a compiled application exists only after its declarations
run — and it is documented rather than hidden. `--path` adds directories to
the import search, `--dependencies` names a `DIRegistry` in the same module.
Without it the application compiles against an empty registry, so a capability
that declares a dependency fails with the reason instead of being described as
if it had none.

The visibility decision is a command-line argument, not an assumption.
`--visibility` selects `full` (the default), `agent` or `identity`;
`--as-scope` simulates a viewer holding those scopes, switching from
"show me everything I declared" to the same `ScopeVisible` rule every transport
applies; `--hide` removes named capabilities. `full` is the default because
`agnara inspect` is a local development tool run against source the operator
can already read, and because `docs/CLI_SPEC.md` describes the command as
showing policies and dependencies. `--json` output is a document an operator
may go on to publish, which is why the same fields can be withheld here.

Text and `--json` build one snapshot and apply one filter, differing only in
the last call. There is no second discovery path and no OpenAPI involvement.

The text renderer takes the visibility decision alongside the snapshot. Most
withheld fields are simply absent from a filtered snapshot and print as
nothing, but risk, confirmation and idempotency always carry a value, so a
withheld one arrives as the declared default and would read as a fact. The
renderer omits them when they were not published and names the withheld fields
once under the header, which is the human-readable partial-visibility state
RFC 0003 asks for.

Exposures are absent from a CLI snapshot, because the CLI imports an
application, not a server: no adapter is composed, so there is nothing to
contribute them. A capability therefore shows no transports. That is the truth
about what this command can see rather than a claim that the capability is
unexposed.

## Alternatives

- Discover the application from the working directory: rejected because there
  is no manifest to discover it from, and guessing would be a convention
  E0A.2 would then have to keep.
- Import the target and catch nothing: rejected because a user module that
  raises is not a CLI defect, and an operator needs the reason rather than a
  stack through `importlib`.
- Default to `agent` visibility: rejected because it would hide the policies
  and dependencies `docs/CLI_SPEC.md` says `agnara inspect` shows, on a local
  tool reading local source.
- Default to `full` with no way to restrict: rejected because the spec
  explicitly denies that offline inspection is permission to dump everything.
- Render from the snapshot alone: rejected because the renderer could not then
  distinguish a withheld risk from a declared `low` one, and would assert a
  fact the filter removed.
- Expose the published-field set on the snapshot instead: rejected for now
  because it would put the deployment's publication posture into every served
  document to solve a problem only a local renderer has. E8.6 may need to
  revisit this for a remote consumer.
- A third-party CLI framework: rejected because `argparse` covers this and the
  CLI's dependency footprint is a packaging decision, not a convenience one.

## Evidence and limits

`tests/cli/test_inspect.py` drives `main` with argument lists and covers both
output modes, JSON determinism across runs, both modes describing the same
filtered snapshot, withheld fields being named rather than defaulted, viewer
simulation, hiding down to an empty result, the empty result still being valid
JSON, malformed targets rejected before import, unimportable and raising
modules, targets that are not an application or not a registry, a capability
that cannot compile, the usage exit code and `--version`.

Limits: `agnara apps`, `agnara capabilities`, `agnara graph` (E8.5),
`agnara schema openapi` (E8.7), `agnara doctor` and all scaffolding remain
unimplemented. There is no `agnara.toml` discovery, no multi-application
project, and no exposure information, so `agnara inspect` cannot yet answer
what a capability is reachable through.

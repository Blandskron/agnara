# agnara-cli

Project introspection and scaffolding CLI. Owns project/app generators, templates and diagnostics.

- Import package: `agnara_cli`
- Depends on: `agnara-core`
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

## Status

`agnara inspect`, `agnara graph`, `agnara schema openapi` and
`agnara context` are implemented. Project and app scaffolding and
`agnara doctor` remain ahead in the backlog.

## `agnara inspect`

```bash
agnara inspect billing.bootstrap:app --dependencies registry
agnara inspect billing.bootstrap:app --json
```

Imports a compiled application and presents its filtered protocol-neutral
introspection snapshot. Text and `--json` build one snapshot and apply one
visibility decision, so the two cannot disagree, and neither derives anything
from OpenAPI.

Importing the target executes the module that defines it. A malformed target
is rejected before any import happens.

`--visibility` selects `full` (default), `agent` or `identity`; `--as-scope`
simulates a viewer's scopes; `--hide` removes named capabilities. Offline
inspection is therefore not a documented bypass of a publication decision.

Exit codes are `0` for an answer, `1` for a target the CLI could not use and
`2` for an invalid command line. Output carries no ANSI decoration. See
ADR 0047 and `docs/CLI_SPEC.md`.

## `agnara graph`

```bash
agnara graph billing.bootstrap:app --dependencies registry
```

Draws capability, dependency and provider relationships from the same filtered
snapshot, with the same target and visibility arguments. There is no second
discovery path: both commands read one `View`, so neither can show something
the other withheld. A withheld relationship source is named rather than drawn
as an empty tree. See ADR 0048.

## `agnara schema openapi`

```bash
agnara schema openapi billing.bootstrap:served
agnara schema openapi billing.bootstrap:document --output openapi.json
```

Exports the OpenAPI document the composition produced. This package must not
import `agnara-http`, so it does not project one — which is also the safer
design: a second projection here could disagree with the one a server serves.

The named attribute may be serialized bytes, the mapping they came from, or a
zero-argument callable returning either. Bytes are emitted unchanged, so an
export is byte-identical to what is served. `--output` writes a file and
refuses to replace one without `--overwrite`. See ADR 0050.

## `agnara context`

```bash
agnara context billing.bootstrap:app --visibility agent
agnara context billing.bootstrap:app --output CAPABILITIES.md
```

Renders the filtered snapshot as Markdown for a model to read, from the same
shared view `agnara inspect` uses. Every rendering states that seeing a
capability is not permission to invoke it, and a withheld field is named rather
than printed as its declared default. Not `llms.txt`, and not a security
boundary. See ADR 0051.

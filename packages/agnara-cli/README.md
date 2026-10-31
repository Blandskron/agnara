# agnara-cli

Project introspection and scaffolding CLI. Owns project/app generators, templates and diagnostics.

```bash
pip install "agnara-cli==1.0.3"
agnara --help
```

This distribution is built and versioned with the synchronized workspace
set. Which versions exist on an index is answered by its PyPI project page,
not by this file: a README ships inside the artifact and cannot describe
the state of a publication that happens after it is built.

It installs the `agnara` console script.
The governed Python exports are listed in
[`docs/API_REFERENCE.md`](../../docs/API_REFERENCE.md); generated projects use
the governed kernel imports. Importing a project target executes that module.

- Import package: `agnara_cli`
- Depends on: the exact synchronized `agnara` version
- Must not import: sibling adapter packages

See `ARCHITECTURE.md` sections 3 and 4 for the package boundaries and the
allowed dependency graph.

## Status

`agnara project create`, `agnara app create` with its `app-api`, `app-mcp`,
`app-agent` and `app-worker` profile shorthands, `agnara apps`,
`agnara inspect`, `agnara graph`, `agnara schema openapi` and `agnara context`
are implemented. The current checkout also implements the static `doctor`
baseline described below; a development-server command remains unimplemented.
The [maturity inventory](../../docs/MATURITY.md) records current boundaries;
proposed commands in a specification do not make them available.

`agnara --help` lists the commands the installed version actually has, which is
the answer to trust over any list written down elsewhere.

## `agnara doctor` (unreleased checkout)

```bash
agnara doctor --project path/to/project
agnara doctor --project path/to/project --json
```

Read-only checks cover the executing Python >=3.14 baseline, strict project
manifest, contained app directories and installed core/CLI/declared HTTP/MCP
version metadata. A2A, Events and Tasks exposures are reported as unavailable
by this diagnostic: it does not inspect the provisional A2A adapter, Events
remains reserved and a durable task runtime is absent. No project or adapter
code is imported, no files are written and no dependencies are installed.

Reports always list unchecked runtime and architecture boundaries. The project's
free-form Python constraint is not evaluated, and matching package metadata does
not prove importability or transitive dependency compatibility. A passing
report is not a runtime-readiness assertion. See the
[doctor contract](../../docs/CLI_SPEC.md#agnara-doctor) and proposed ADR 0096.

The versioned JSON or text report goes to stdout. Any failed check exits 1;
all checks passing exits 0. Argument errors retain exit 2 on stderr. This
command is unreleased checkout behavior, not a claim about the 1.0.3 wheel.

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

The attribute may be a dotted path, so an application held inside a container
or a factory result needs no rearranging to be inspectable:

```bash
agnara inspect billing.bootstrap:container.app --dependencies container.registry
```

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

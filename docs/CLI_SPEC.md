# CLI Specification

## Goal

Agnara should provide a Django-like "create project / create app" experience while generating architecture suitable for modern modular systems.

The CLI should eliminate repetitive setup without hiding the resulting code.

## Invocation

Preferred installed command:

```bash
agnara <command>
```

Equivalent module invocation:

```bash
python -m agnara <command>
```

`python agnara ...` is not the canonical form because `agnara` is a package/console command, not a local script.

## Project creation

```bash
agnara project create commerce
```

Short alias may be considered:

```bash
agnara new commerce
```

Default output:

```text
commerce/
├── pyproject.toml
├── agnara.toml
├── src/
│   └── commerce/
│       ├── __init__.py
│       ├── bootstrap.py
│       ├── settings.py
│       └── apps/
├── tests/
├── AGENTS.md
└── README.md
```

The generator must create only meaningful files.

## App creation

Canonical:

```bash
agnara app create payments
```

Default architecture:

```text
modular-hexagonal
```

Examples:

```bash
agnara app create users
agnara app create catalog --with http
agnara app create tools --with mcp
agnara app create payments --with http,mcp,tasks
agnara app create agents --with mcp,a2a
```

## Profiles

Profiles are scaffolding conveniences, NOT new runtime app types.

```bash
agnara app create catalog --profile api
agnara app create tools --profile mcp
agnara app create assistants --profile agentic
agnara app create jobs --profile worker
agnara app create platform --profile full
```

Proposed mappings:

| Profile | Initial exposures |
|---|---|
| `core` | none |
| `api` | HTTP |
| `mcp` | MCP |
| `agentic` | MCP + A2A |
| `worker` | Tasks + Events |
| `full` | HTTP + MCP + A2A + Events + Tasks |

Default profile: `core`.

Profiles can be combined/overridden with `--with`.

## Convenience aliases

For discoverability and speed, optional aliases may map to the canonical command:

```bash
agnara app-api catalog
agnara app-mcp tools
agnara app-agent assistants
agnara app-worker jobs
```

These MUST behave as aliases only.

For example:

```text
agnara app-mcp tools
```

is semantically equivalent to:

```text
agnara app create tools --profile mcp
```

The implementation must not create separate code paths or framework types for these aliases.

## Architecture options

Canonical:

```bash
agnara app create payments --architecture modular-hexagonal
```

Initial supported architectures:

### `modular-hexagonal`

Recommended default.

Provides explicit domain/application/adapter boundaries without forcing microservices.

### `minimal`

For very small capabilities, experiments and examples.

### `vertical`

Potential future profile for vertical-slice organization.

Do not add architecture templates casually. Each template becomes a maintained public contract.

## Add exposure to an existing app

```bash
agnara app expose payments http
agnara app expose payments mcp
agnara app expose payments a2a
agnara app expose payments tasks
agnara app expose payments events
```

Multiple:

```bash
agnara app expose payments http mcp
```

The command creates adapter scaffolding and updates project metadata without changing domain/application code.

## Remove exposure

Potential command:

```bash
agnara app unexpose payments mcp
```

Must fail safely if user code would be destroyed.

Generated code containing user modifications must never be silently deleted.

## Capability generation

```bash
agnara capability create payments refund
```

Possible options:

```bash
agnara capability create payments refund \
  --input RefundCommand \
  --output RefundReceipt \
  --risk high \
  --effects financial-write
```

The generator should create application-layer code and tests, not automatically invent business logic.

## Expose a capability

Potential advanced form:

```bash
agnara expose payments.refund --http "POST /refunds"
agnara expose payments.refund --mcp
agnara expose payments.refund --a2a
```

This is useful when an app has multiple capabilities and only some should be public on a transport.

## Introspection commands

```bash
agnara apps
agnara capabilities
agnara inspect payments
agnara graph
agnara context
agnara doctor
```

### `agnara apps`

Lists apps, architecture and exposures.

### `agnara capabilities`

Lists capability IDs and owning apps.

### `agnara inspect`

Shows domain metadata, policies, dependencies and protocol exposures.

Text and `--json` modes consume the same filtered, protocol-neutral
introspection snapshot used by Agnara Explorer. Inspection must not infer its
model from OpenAPI because non-HTTP exposures and capability semantics would
be lost.

The JSON representation requires an explicit format version, deterministic
ordering and no ANSI decoration. Offline inspection still applies a declared
publication/redaction policy; it is not permission to dump secrets, dependency
instances or private policy internals.

#### Implemented form

Until `agnara.toml` exists (E0A.2), the application is named explicitly:

```bash
agnara inspect billing.bootstrap:app
agnara inspect billing.bootstrap:app --dependencies registry --json
agnara inspect billing.bootstrap:app --visibility agent --as-scope billing:write
agnara inspect billing.bootstrap:app --path src --hide billing.reconcile
```

Importing a target executes the module that defines it; a malformed target is
rejected before any import happens.

`--dependencies` names a `DIRegistry` in the same module. Without it the
application compiles against an empty registry, so a capability that declares
a dependency fails with the reason rather than being described as if it had
none.

`--visibility` chooses which fields are published: `full` (the default, for
local inspection of source the operator can already read), `agent` (what a
caller needs to choose and call a capability) or `identity` (names only).
`--as-scope` simulates a viewer holding those scopes, applying the same scope
rule a transport applies. `--hide` removes named capabilities. The text output
names any withheld fields under the header, so a partial view is legible as
one.

Exit codes: `0` when the command produced its answer, including "nothing is
visible"; `1` for a target or application the CLI could not use, reported as a
diagnostic on stderr rather than a traceback; `2` for an invalid command line.

Exposures are absent, because the CLI imports an application rather than
composing a server, so no adapter contributes them. See ADR 0047.

### `agnara graph`

Displays project/app/capability dependency relationships.

#### Implemented form

```bash
agnara graph billing.bootstrap:app --dependencies registry
agnara graph billing.bootstrap:app --visibility agent --as-scope billing:write
```

`agnara graph` takes the same target and visibility arguments as
`agnara inspect` and reads the same filtered snapshot, so the two cannot
disagree about what a viewer may see. It draws each visible capability, its
dependency parameters, and the provider each resolves to with that provider's
scope, kind and own requirements.

When the visibility decision withholds dependencies or providers, the command
names the withheld relationship source instead of drawing an empty tree.
Providers no visible capability reaches are listed separately, computed
transitively. See ADR 0048.

### `agnara context`

Renders the same filtered snapshot as Markdown for a model to read.

```bash
agnara context billing.bootstrap:app --visibility agent
agnara context billing.bootstrap:app --output CAPABILITIES.md
```

It takes the same target and visibility arguments as `agnara inspect`, so it
cannot describe a capability that command would hide from the same viewer.

Every rendering, including an empty one, states that seeing a capability is not
permission to invoke it. A field the visibility decision withheld is named
under a "This view is partial" line rather than printed as its declared
default, because a model told `risk: low` about a withheld risk is misled about
the thing that matters most. The snapshot's format and version appear in the
header so a stale context is identifiable.

This is not `llms.txt` and must not be presented as canonical discovery or as
authorization. See ADR 0051. The E8.12 research decision in
[ADR 0053](adr/0053-llms-txt-documentation-index.md) reserves optional
`llms.txt` generation for documentation publishing; it adds no CLI flag,
runtime route or output format. Choosing that filename with `--output` does
not change the meaning of the generated context.

### `agnara doctor`

Checks:

- Python version;
- project manifest;
- missing adapters;
- dependency cycles;
- invalid app registration;
- protocol configuration;
- architecture rule violations.

## Development commands

Potential:

```bash
agnara dev
agnara test
agnara schema openapi
agnara schema asyncapi
agnara mcp inspect
```

Agnara should not unnecessarily wrap every existing ecosystem command. CLI commands are justified only when they add framework-specific value.

### `agnara schema openapi`

Exports the same deterministic OpenAPI 3.2 projection that `agnara-http` can
serve. It consumes compiled capabilities, HTTP exposures and schema-port
output; it does not read a manually maintained parallel schema.

The command should support stdout and an explicit output path, machine-readable
diagnostics and non-interactive operation.

#### Implemented form

```bash
agnara schema openapi billing.bootstrap:served
agnara schema openapi billing.bootstrap:document --output openapi.json
agnara schema openapi billing.bootstrap:build --pretty
```

`agnara-cli` must not import a sibling adapter, so the CLI does not project a
document: it exports the one the composition produced. That is also the safer
design, because a second projection here could disagree with the one a server
serves.

The named attribute may be the serialized bytes an HTTP surface would serve,
the mapping those bytes came from, or a zero-argument callable returning
either. Bytes are emitted unchanged, so an export is byte-identical to what is
served; a mapping is serialized with the same arguments the HTTP projection
uses.

`--output` writes the file and prints nothing, refusing to replace an existing
file without `--overwrite`. `--pretty` indents for a reader and is no longer
byte-identical to the served document. See ADR 0050.

### Documentation preview

`agnara docs` remains an evaluated command, not an accepted command. It is
justified only if it adds Agnara-specific value such as starting the configured
development composition and reporting/opening its selected provider. It must
not duplicate `agnara dev`, silently enable production documentation or own a
second set of route/provider settings.

Human documentation interfaces are optional consumers. Agents and automation
use `agnara schema openapi` and `agnara inspect --json`; neither command parses
HTML.

## Non-interactive mode

All generators must work in CI and agent environments:

```bash
agnara app create payments --profile full --no-input
```

Interactive prompts may exist for humans, but every prompt must have a flag equivalent.

## Dry run

Generators should support:

```bash
agnara app create payments --with http,mcp --dry-run
```

Output:

```text
CREATE src/commerce/apps/payments/...
UPDATE agnara.toml
UPDATE project composition
```

No files are changed.

## Machine-readable output

Important commands should support:

```bash
--json
```

Example:

```bash
agnara inspect payments --json
```

This is essential for coding agents and automation.

## Safe generation rules

The CLI MUST:

- refuse accidental overwrite by default;
- be deterministic;
- make generated provenance clear where useful;
- avoid timestamps in generated source unless required;
- support dry-run;
- produce stable paths;
- validate identifiers;
- update metadata atomically where possible;
- never delete modified user files without explicit force/confirmation.

## Exit codes

Define stable exit codes before 1.0 for automation.

At minimum distinguish:

```text
success
usage/config error
generation conflict
architecture validation failure
runtime/project error
```

## Future plugin generators

Eventually third-party adapters may register generators:

```text
agnara app expose payments kafka
```

The plugin system must not permit arbitrary template code execution without clear trust boundaries.

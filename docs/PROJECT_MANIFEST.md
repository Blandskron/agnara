# Project Manifest

## Goal

Agnara needs an explicit, machine-readable project description that supports humans, CLI tooling and coding agents without making configuration the runtime architecture.

Proposed file:

```text
agnara.toml
```

## Example

```toml
[project]
name = "commerce"
python = ">=3.14"

[defaults]
architecture = "modular-hexagonal"

[apps.users]
module = "commerce.apps.users"
path = "src/commerce/apps/users"
architecture = "modular-hexagonal"
exposures = ["http"]

[apps.payments]
module = "commerce.apps.payments"
path = "src/commerce/apps/payments"
architecture = "modular-hexagonal"
exposures = ["http", "mcp", "tasks"]
```

## Rules

The manifest is:

- explicit;
- deterministic;
- human-readable;
- agent-readable;
- updateable by CLI;
- versionable in Git.

It is not intended to contain secrets.

Secrets belong in environment/provider configuration.

## Implemented form

ADR 0059 records the decided format and `agnara_cli` implements a reader for
it. `[project] name` must be a valid Python identifier; `python` is validated
as a non-empty string and deliberately not parsed as a PEP 440 specifier.
`[defaults] architecture` and each `[apps.<name>] architecture` accept
`modular-hexagonal`, `minimal` or `vertical`; `exposures` accepts `http`,
`mcp`, `a2a`, `tasks` or `events`. Each app requires `module` and `path`, and
an app inherits the project default architecture when it declares none.

An unknown table or key is rejected rather than ignored, so a typo fails
instead of silently disabling an app. An app `path` must be relative, must use
`/` separators and may not contain `..`, because generators will later write
to it. Two apps may not share a module or a path. Declaration order is
preserved.

`agnara apps` reads the manifest and lists apps, architecture and exposures.
It imports nothing, so it reports declared intent rather than runtime state.

## Runtime relationship

The project manifest describes composition intent.

Python remains capable of explicit/manual composition for advanced scenarios.

The framework should detect meaningful divergence between manifest and runtime registration rather than silently accepting contradictory state.

## Why not `INSTALLED_APPS`

Agnara should learn from Django's explicit app registry while avoiding stringly typed runtime configuration as the only composition mechanism.

The manifest can drive scaffolding/discovery while Python composition remains typed and inspectable.

## Why not only `pyproject.toml`

`pyproject.toml` is excellent for packaging and tool configuration.

A dedicated `agnara.toml` makes the application composition contract:

- easier to locate;
- easier for agents to modify safely;
- independent of build backend;
- usable for projects that may eventually contain multiple deployable Agnara runtimes.

This is a proposed decision and should be revisited before 1.0 if ecosystem experience favors `pyproject.toml`.

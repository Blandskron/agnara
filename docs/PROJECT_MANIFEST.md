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

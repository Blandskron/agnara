# ADR 0059 — The `agnara.toml` Project Manifest Format

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #229 (E0A.2)

## Context

`docs/PROJECT_MANIFEST.md` proposed `agnara.toml` and its rules but left the
format underspecified: which keys exist, what each accepts, what happens to an
unrecognised one, and what the file is authoritative *for*. RFC 0002 lists
"manifest vs typed composition source-of-truth balance" among its open
questions.

Every remaining EPIC 0A item depends on the answer. `agnara project create`
writes this file, `agnara app create` updates it, and `--dry-run` reports
`UPDATE agnara.toml`. A generator cannot safely write a file whose shape is not
decided.

## Decision

### The manifest describes intent; Python composes

This answers RFC 0002's open question for the manifest's own scope. The
manifest records what a project *contains*: which apps exist, where their
code lives, which layout each uses, which exposures each was scaffolded with.
It is read by tooling and written by generators. It is never imported,
executed or consulted at runtime to decide behaviour, and reading it runs no
project code.

Typed Python composition stays the runtime truth, as
`docs/PROJECT_MANIFEST.md` already stated and as the rejection of a
`INSTALLED_APPS`-style stringly-typed registry requires. Detecting divergence
between the two is left to `agnara doctor`, which `docs/CLI_SPEC.md` already
lists "project manifest" among its checks.

### Shape

```toml
[project]
name = "commerce"          # required, a valid Python identifier
python = ">=3.14"          # optional, non-empty string

[defaults]
architecture = "modular-hexagonal"   # optional

[apps.users]                          # key: a valid Python identifier
module = "commerce.apps.users"        # required, dotted module path
path = "src/commerce/apps/users"      # required, project-relative, POSIX
architecture = "modular-hexagonal"    # optional, inherits [defaults]
exposures = ["http"]                  # optional
```

`architecture` accepts `modular-hexagonal`, `minimal` or `vertical`, and
`exposures` accepts `http`, `mcp`, `a2a`, `tasks` or `events` — the sets
`docs/CLI_SPEC.md` names. An app inherits `[defaults] architecture`, which
itself defaults to `modular-hexagonal`. Declaration order is preserved rather
than sorted, because the order is the operator's and re-sorting would make
diffs lie.

Two apps may not share a `module` or a `path`. Either would make a generator's
next write ambiguous.

### Unknown keys are refused

An unrecognised table or key fails the load, naming what was found and what is
accepted.

The alternative — ignoring it — produces the worst failure this format can
have: `exposure = ["http"]` sits in a working manifest, looks correct, and does
nothing. A file an agent is expected to edit safely cannot have silent
no-ops.

The cost is stated rather than hidden: a manifest written for a newer Agnara is
rejected by an older one instead of degrading. That is the intended trade while
the format is pre-1.0, and it should be revisited before 1.0, when an
additive-compatible reader may matter more than typo detection.

### A path may not leave the project

`path` must be relative, must use `/` separators and may contain no `..`
segment. Reading a manifest is harmless; generators will write to these paths,
and validating containment at the point the value is parsed is what makes that
later write safe. A backslash is refused rather than normalised so one manifest
means the same thing on every platform.

### `python` is not parsed

The field is validated as a non-empty string and no further. Interpreting a
PEP 440 specifier requires a dependency `agnara-cli` does not have and should
not acquire for this. Checking a declared floor against Agnara's 3.14 minimum
belongs to `agnara doctor`. Saying this plainly is better than a validator that
appears to check a specifier and does not.

### `agnara apps` reads it

`docs/CLI_SPEC.md` specifies `agnara apps` as listing apps, architecture and
exposures, which is exactly this file's content. It ships here, as the
manifest's first reader, because a format with no consumer cannot be validated
end to end and AGENTS.md warns against structure nothing uses.

The command imports nothing. It reports declared intent, and its description
says so, so an operator is not misled into reading it as runtime state.

## Consequences

`docs/CLI_SPEC.md`'s note that the application must be named explicitly
"until `agnara.toml` exists (E0A.2)" is *not* lifted. Resolving a target from
the manifest needs a convention for where a composed application lives, and
that convention belongs with the generator that creates it. The note is updated
to say what still blocks it rather than being deleted.

A manifest is not required. `find_manifest` returning nothing is a normal
answer, and every existing command keeps working without one.

The public surface of `agnara-cli` grows by the manifest model, its loader and
its errors. That is deliberate: `agnara doctor` and the generators are separate
work that will consume the same reader rather than parse the file again.

## Alternatives considered

**Put the manifest in `pyproject.toml`.** `docs/PROJECT_MANIFEST.md` already
argues against it and asks for the decision to be revisited before 1.0 if
ecosystem experience favours it. Nothing here changes that; this ADR
implements the proposed file rather than reopening the question.

**Model the manifest in `agnara-core`.** Rejected: core is transport-neutral
and runtime-focused, the manifest is a tooling artefact, and putting it in core
would invite the runtime to consult it — exactly the stringly-typed
composition the project rejected.

**Accept unknown keys for forward compatibility.** Rejected above, with its
cost recorded.

**Validate `path` only when writing.** Rejected: the value is parsed once and
used by several future commands, so the check belongs where the value enters,
not at each use.

## Scope

No generation, no template, no manifest writing, no `--dry-run`, no
`agnara doctor`, and no manifest-driven target resolution. Proposed status does
not claim maintainer architectural approval.

## Evidence

- `tests/cli/test_manifest.py` — 56 cases: the accepted shape, inheritance,
  order preservation, and every rejection including unknown tables and keys,
  four escaping paths, unknown architectures and exposures, duplicate modules
  and paths, invalid TOML, non-UTF-8 bytes, and discovery.
- `tests/cli/test_apps.py` — 12 cases driving `main`: text and deterministic
  JSON, default inheritance, POSIX paths in the export, an empty project,
  discovery from a subdirectory, and three operator errors reported as one
  line on stderr with no traceback.

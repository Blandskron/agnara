# ADR 0064 — A Profile Is a Starting Point That `--with` Extends

- Status: Proposed
- Date: 2026-09-06
- Tracking: GitHub Issue #248 (E0A.7)

## Context

ADR 0013 decided what a profile is: `api`, `mcp`, `agentic`, `worker` and
`full` "select initial adapter scaffolding only" and are "not persisted as
runtime application types". `docs/CLI_SPEC.md` gives the mapping and the
default (`core`), and E0A.6 built the exposure resolution a profile needs.

One sentence in `docs/CLI_SPEC.md` is genuinely ambiguous:

> Profiles can be combined/overridden with `--with`.

Combining and overriding are different behaviours, and the sentence names
both. `agnara app create catalog --profile api --with mcp` either scaffolds
HTTP **and** MCP, or MCP **only**.

## Decision

### `--with` adds to a profile

The union. `--profile api --with mcp` scaffolds both.

Three things point this way:

- the column in `docs/CLI_SPEC.md` is headed **"Initial exposures"** — a
  starting point, not a final answer;
- ADR 0013's worked example says a profile "creates a normal `tools` app and
  *adds* MCP exposure scaffolding";
- override produces a reading nobody wants: `--profile full --with http` would
  *reduce* the app to HTTP. A user who wants only HTTP writes `--with http`
  and no profile, so override makes the combination useful only for shrinking
  a profile — a need no one has expressed and an easy thing to express
  directly.

Order is the profile's exposures first, then whatever `--with` adds that the
profile did not already bring. An exposure named twice is scaffolded once. So
`--profile worker --with http` declares `["tasks", "events", "http"]`, and
`--profile api --with http` declares `["http"]`.

### A profile leaves no trace of itself

Nothing about the profile reaches `agnara.toml`. The manifest records
`exposures` — the result — exactly as E0A.6 left it, and there is no `profile`
key.

This is ADR 0013's decision carried through to the file: a profile that was
persisted would be a runtime app type in everything but name, and the next
reader would reasonably ask what the runtime does differently for an `agentic`
app. Nothing, and the manifest should not suggest otherwise.

The consequence is that `--profile agentic` and `--with mcp,a2a` produce
byte-identical projects. That is the point, and it is tested.

### `minimal` refuses a profile that brings exposures

The same rule ADR 0063 states for `--with`, for the same reason: a minimal app
has no `adapters/` package. `--profile core` is accepted on a minimal app,
because it brings nothing to refuse.

The message names the flag that actually caused the refusal — `--profile api`,
not `--with` — since a diagnostic pointing at a flag the user did not pass
wastes the reader's time.

## Consequences

- `PROFILES` is a table in the CLI, not a concept in the core. Adding a
  profile is one line and no new behaviour.
- A profile can never disagree with the app on disk, because it resolves to
  exposures before anything is generated and the manifest records the result.
- If a real need for override appears, it is a new flag with a name that says
  so, not a change to what `--with` means. Changing this later would silently
  alter existing commands.

## Alternatives considered

**Override: `--with` replaces the profile's exposures.** Rejected for the
reasons above. It also makes `--with` mean two different things depending on
whether `--profile` is present, which is the kind of context-dependence that
makes a CLI hard to remember.

**Record the profile in the manifest.** Rejected: ADR 0013 forbids it, and it
would invite a runtime meaning that does not exist.

**Reject `--profile` and `--with` together.** Rejected: `docs/CLI_SPEC.md`
explicitly says they can be used together, and refusing the combination would
force a user who wants `full` plus nothing extra to enumerate five exposures
by hand.

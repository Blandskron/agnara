# ADR 0061 — The Generated App Is a Working Example

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #233 (E0A.3, E0A.4)

## Context

`agnara app create` is the second generator. ADR 0060 built the plan-then-apply
mechanism and recorded that E0A.9 `--dry-run`, E0A.10 conflict detection and
E0A.11 `--json` stayed in progress until a second consumer existed, because a
mechanism with one caller has not been shown to be reusable. This is that
consumer.

`docs/SCAFFOLDING.md` specifies the modular-hexagonal layout and states the
generator "must NOT generate dozens of meaningless empty files". That sentence
is the design constraint: the question is not which directories to create but
what to put in them.

## Decision

### The generated app runs

Domain, application port, application capabilities, an outbound adapter that
implements the port, and tests — all present, all working together. The
generated app's capabilities register on an `Agnara` application, compile into
execution plans and invoke successfully against the generated adapter.

A skeleton of empty `__init__.py` files would satisfy the tree and teach
nothing. A reader opening a generated app sees why the layers are separated
because the dependencies actually point that way, not because a comment says
they should.

### The example is domain-neutral

An app may be called `payments`, `catalog` or `users`. A generator that
invented banking concepts for a catalog would produce code its first reader has
to delete, so the example is a `Record` with a `Reference`, a
`RecordRepository` port and an in-memory adapter. Every docstring says what to
rename it to.

What is *not* neutral, and is the point, is the direction of every dependency:

```text
adapters/inbound  -> application -> domain
adapters/outbound -> application (implements its ports)
```

Four tests enforce it rather than describing it. No generated module imports a
transport. No domain or application module imports an adapter. The domain
imports nothing from the application. And `module.py` is the only non-test
module that knows both the application and its adapters — the app's composition
boundary, and the only one.

The app's own tests are excluded from that last rule. Wiring an adapter to the
code under test is what testing a composition means, and forbidding it would
push the same import somewhere less honest.

### The manifest is appended to, never rewritten

`agnara app create` adds `[apps.<name>]` to `agnara.toml` by appending to the
existing text, not by re-serializing a parsed model. Re-serializing would
silently discard the comments and the ordering an operator wrote, which
AGENTS.md's "update project metadata safely" and "never silently delete
modified files" both rule out. A test asserts the generated header comment
survives.

An app already declared in the manifest is refused. So is an invalid manifest,
before anything is written.

### An intended update is not a conflict

The mechanism needed exactly one addition to carry a second consumer: a
`FileAction` can declare that its target is *meant* to be rewritten. Rewriting
`agnara.toml` is an update; finding a file where the generator meant to create
one is still a conflict and is still refused, with the existing content
untouched. Two tests cover both halves, including that a refused run leaves the
manifest unmodified.

That is the evidence E0A.9, E0A.10 and E0A.11 were waiting for, so they move to
complete.

### Both commands render their result with the same function

`--dry-run` and a real run now print through one renderer. They previously
built similar strings separately, which is precisely the drift ADR 0060 argued
against; a test caught the two disagreeing about a path prefix. One plan, one
rendering, whether or not it was applied.

## What is deliberately absent

**`bootstrap.py` is not edited.** `docs/CLI_SPEC.md`'s dry-run sketch shows
`UPDATE project composition`, and this command does not do it. Rewriting a
user's composition root means parsing and modifying their Python, which needs a
code-modification strategy — where to insert, how to detect an existing
registration, what to do with a file that has been restructured — that deserves
its own decision. Until then the command prints the two lines to add, which is
honest about who is doing the work.

**No inbound adapter files.** Every app is created with no exposures.
`--with` and `--profile` are E0A.6 and E0A.7, and `docs/SCAFFOLDING.md` is
explicit that only requested inbound adapters are added. `adapters/inbound/`
exists as a documented, empty package.

## Consequences

Generated apps carry an example that users will delete. That is intended: the
cost of deleting five short files is much lower than the cost of a layout
nobody can tell the purpose of.

The template is a set of Python string functions, as ADR 0060 chose. It is now
noticeably larger, and the argument for a checked-in template directory grows
with it. ADR 0060 said to revisit when `--with` and `--profile` need
conditionals; that remains the right trigger, and this ADR does not reopen it.

A generated app is linted by the generated project's own Ruff configuration.
Two tests run the real linter against the generated tree, so a template that
stops being clean fails here rather than in a user's first commit.

## Alternatives considered

**Generate empty modules with docstrings only.** Rejected by
`docs/SCAFFOLDING.md`'s own rule, and it would leave the port/adapter
relationship — the thing the layout exists for — undemonstrated.

**Generate a domain-specific example from the app name.** Rejected: it would
guess wrong, and a wrong guess is worse than a neutral one because it looks
authoritative.

**Register the app automatically in `bootstrap.py`.** Rejected above, on the
grounds that modifying a user's Python needs its own decision.

**Re-serialize `agnara.toml` from the parsed model.** Rejected: it deletes
comments and ordering without saying so.

## Scope

No `--with`, `--profile`, `minimal` template, CLI aliases, `app expose`,
`capability create`, or composition-root editing. Proposed status does not
claim maintainer architectural approval.

## Evidence

`tests/cli/test_app_create.py` — 35 cases: the specified layout, byte-identical
output across two runs, a multi-word app name becoming a camel-case error
class, every file compiling, the app registering and invoking end to end with
its port supplied by the runtime, the app's own tests executed, the real Ruff
lint and format checks, four layering rules, the manifest declaration and
comment preservation, a second app appended without disturbing the first,
`agnara apps` listing it, a dry run leaving both the tree and the manifest
untouched, an already-declared app refused, a stray app file still treated as a
conflict with the manifest left unmodified, a missing manifest pointing at
`project create`, an invalid manifest refused before any write, five invalid
names, the never-prompt guard, and deterministic JSON marking the manifest as
an intended update rather than a conflict.

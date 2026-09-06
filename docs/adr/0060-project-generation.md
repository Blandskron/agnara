# ADR 0060 — Generators Plan Before They Write

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #231 (E0A.1)

## Context

`agnara project create` is the first generator. AGENTS.md states what every
generator must do before any generator exists: support dry-run, be
deterministic, refuse overwrite by default, run non-interactively, expose
machine-readable output, update project metadata safely and never silently
delete modified files.

Those properties are cheap to design in and expensive to retrofit. Code that
decides and writes in the same pass cannot answer "what would you do?" without
a second implementation of the answer, and the two drift.

## Decision

### Two phases: plan, then apply

A generator builds a `GenerationPlan` — every file it would write, its
contents, and whether something is already at that path — without touching the
filesystem beyond existence checks. `apply_plan` writes it.

Everything a caller needs is answerable from the plan: `--dry-run` renders it,
`--json` serializes it, and conflict detection inspects it. There is no second
code path that could disagree with the real one, which is what makes a dry run
worth trusting.

Actions are sorted by path when the plan is built. Two runs with the same
inputs therefore produce the same plan, the same rendering and the same JSON,
regardless of the order a template happened to build its mapping in.

### Conflicts are refused before the first write

`apply_plan` checks the whole plan, and if any action would replace an existing
file it raises before writing anything, naming every conflicting path. A
refused run leaves the directory exactly as it was — not half-generated.

`--overwrite` authorizes replacement for that run. There is no configuration
that makes it the default, and there is never a prompt.

### Generated files are written with `\n`

A project is shared and reviewed in diffs, so its line endings are its own
decision rather than that of the machine that happened to create it.

### Determinism means no ambient input

Templates are pure functions of the project name. Nothing reads the clock, the
environment, a random source or the network. A generated project that changed
between two runs would make its own diff untrustworthy.

### Validation happens before any directory exists

The project name is checked with the manifest's rule — a single lower-case
Python identifier — before anything is created, because it becomes a package
directory, an import path and `[project] name`. A name that would produce a
project that cannot load is refused rather than generated.

Lower case is required in addition to the manifest rule: the package directory
and the import path must agree on a case-insensitive filesystem.

## What is generated, and what is not

`docs/CLI_SPEC.md` gives the tree. Two choices inside it are worth recording.

**`bootstrap.py` declares no capability.** It builds the application and the
dependency registry and stops. A generated example capability would be deleted
by every real user, and `agnara app create` is where capabilities arrive. What
the composition root does establish is the convention the tooling reads:
`agnara inspect <project>.bootstrap:app --path src` works on a freshly
generated project, and a test asserts it.

**`settings.py` reads no environment.** It is a frozen value type constructed
by `bootstrap`. Where configuration comes from is a decision the project has
not made, and a generator that picked one — environment variables, a file,
a provider — would make a security-relevant choice silently. The generated
docstring says so and says where to add a loader.

The generated project depends on `agnara` and nothing else. Adding a transport
would put a protocol dependency in a project's application layer before the
project asked for one, which `docs/APPLICATION_MODEL.md` and AGENTS.md forbid;
a test walks every generated module to assert it.

## Consequences

E0A.9 `--dry-run`, E0A.10 conflict detection and E0A.11 `--json` are
implemented here, on shared machinery, for one command. They are recorded as in
progress rather than complete: the mechanism earns "done" when a second
generator — `agnara app create`, E0A.3 — uses it, because a mechanism with
one caller has not yet been shown to be reusable.

The generated project's Ruff configuration is its own, not this repository's.
The test that lints it runs the real linter against the generated tree under
the rules it ships with, so a template that stops being clean fails here rather
than in a user's first commit. Verified non-vacuous: an unused import added to
one template fails both the lint and the format check.

`GenerationPlan`, `FileAction` and `GenerationError` become public API of
`agnara-cli`, because `agnara app create` and `agnara capability create` will
build plans rather than reimplement writing.

## Alternatives considered

**Write as you go, and implement `--dry-run` separately.** Rejected: two code
paths for one behaviour, and the preview is the one nobody tests until it
lies.

**A template engine.** Rejected for now: it would add a dependency for string
substitution the standard library does. Revisit when templates need
conditionals — `--with` and `--profile` (E0A.6, E0A.7) may force it, and that
is the right moment to decide, not this one.

**Copy a checked-in template directory.** Attractive, and it would make the
templates reviewable as real files. Rejected because packaging data files
correctly across wheel, editable and zip installs is its own problem, and
because a template directory of Python files would be linted by this
repository's configuration rather than the generated project's.

**Prompt for anything.** Rejected outright. `docs/CLI_SPEC.md` requires
generators to work in CI and agent environments; a prompt hangs both. A test
patches `input` to raise, so adding one fails.

## Scope

No `agnara app create`, no templates beyond the default project, no `--with`
or `--profile`, no CLI aliases, no golden-file corpus, no cross-platform path
suite, and no manifest-driven target resolution. Proposed status does not
claim maintainer architectural approval.

## Evidence

`tests/cli/test_project_create.py` — 31 cases against a really generated
project: the exact tree, byte-identical output across two runs, `\n` endings,
every Python file compiling, the composition importing and compiling, the
project's own tests executed, the generated manifest accepted by the E0A.2
reader, `agnara apps` and `agnara inspect` reading it, no transport import, the
real Ruff lint and format checks, a dry run leaving no trace, a refused run
leaving every file untouched, `--overwrite`, five invalid names, and
deterministic versioned JSON with POSIX paths.

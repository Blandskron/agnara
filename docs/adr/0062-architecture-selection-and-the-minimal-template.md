# ADR 0062 — Architecture Selection Describes What Was Generated

- Status: Proposed
- Date: 2026-09-06
- Tracking: GitHub Issue #244 (E0A.5)

## Context

ADR 0012 makes modular-hexagonal the default scaffold and keeps `minimal` as
an escape hatch "for examples and tiny modules". `docs/CLI_SPEC.md` names three
architectures — `modular-hexagonal`, `minimal` and a future `vertical` — and
specifies the selection flag:

```bash
agnara app create payments --architecture modular-hexagonal
```

ADR 0061 delivered the default template. Until this ADR there was only one, so
`agnara app create` had nothing to select between. It still wrote an
`architecture` key into the new `[apps.<name>]` table, taking the value from
the project's `[defaults] architecture`.

That produced a manifest that could contradict the directory beside it. A
project declaring `minimal` as its default got a manifest entry saying
`minimal` and a full hexagonal tree on disk, and `agnara apps` — whose whole
job is to report what the manifest declares without importing anything —
reported the declared value. Reproduced on `develop` before this change.

## Decision

### The manifest entry is a claim about the files

`agnara app create` resolves one architecture, generates that template, and
records that same value. The declaration and the generated layout are produced
from a single decision rather than from two sources that happen to agree while
only one template exists.

This is why the defect mattered more than the missing template did. `agnara
apps` reads the manifest instead of the filesystem precisely so it can describe
a project without importing it; that only works while the manifest is true.

### Resolution order

An explicit `--architecture` wins. Otherwise the project's `[defaults]
architecture` applies. There is no third source and no prompt.

### A reserved name is refused, not substituted

`ARCHITECTURES` is the manifest vocabulary and stays wider than the set of
implemented templates, because a manifest may legitimately name `vertical`
before a generator exists for it. Selecting one without a template is an
error naming the alternatives, never a silent fallback to the default.

Generating a different layout than the one asked for is the failure this ADR
exists to prevent; doing it in response to an explicit flag would be worse
than doing it by accident.

A project whose *default* has no template still generates apps when a usable
architecture is passed explicitly, so an unimplemented default does not block
the project.

### `minimal` declares the same capabilities as the default

The two templates generate `get_record` and `list_records` over the same
`Record`/`Reference` vocabulary. The only difference is where the data comes
from: `modular-hexagonal` depends on a port that an outbound adapter supplies,
`minimal` holds it in the module.

Someone choosing between them is then reading one difference rather than two
unrelated examples, and that difference is exactly the question
`--architecture` asks. A minimal app has no protected parameters at all, which
is the visible consequence of having no ports.

### A minimal app registers like any other

`module.register(app, dependencies)` is unchanged, and `dependencies` is
accepted and unused. Growing an app from `minimal` to `modular-hexagonal`
therefore changes the app's internals and not the composition root.

## Consequences

- `agnara apps` can be trusted about architecture; it could not be before.
- Two templates are now maintained public contracts, as `docs/CLI_SPEC.md`
  warns. `docs/CLI_SPEC.md` already says not to add them casually.
- `vertical` remains reserved. It is accepted by `--architecture` only so it
  can be refused with an explanation rather than as an unknown value.
- E0A.6 `--with` exposure selection and E0A.7 profiles remain ahead. Profiles
  are aliases over these options per ADR 0013, so they compose with this
  resolution order rather than replacing it.

## Alternatives considered

**Keep one template and drop the `architecture` key.** Rejected: the key is
specified in `docs/CLI_SPEC.md` and read by `agnara apps`, and `minimal` is an
E0A.5 deliverable.

**Restrict `--architecture` to implemented templates.** Rejected: argparse
would reject `vertical` as an invalid choice, which reads like a typo. The
useful message is that the name is real and the generator is not written yet.

**Fall back to the default when an architecture has no template.** Rejected
outright. Writing a layout other than the requested one, and then declaring
it, is the defect this ADR removes.

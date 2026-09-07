# RFC 0007 — Distribution version identity and dependency constraints

- Status: Answered by ADR 0069
- Date: 2026-09-07
- Tracking: GitHub Issue #280
- Supplements: ADR 0021
- Answered by: ADR 0069

## Summary

Two things about Agnara's seven distributions are undecided, and the second one
is currently producing a broken install.

1. **What version of the core may an adapter accept?** All six adapters declare
   `dependencies = ["agnara"]` with no bound.
2. **What version does `develop` carry between releases?** ADR 0021 sets
   versions on the release branch, so `develop` keeps the last released version
   while its code diverges from it.

They are independent. Answering only the first leaves the failure below intact,
which is the main thing this RFC exists to say.

ADR 0021 already states the intent both questions serve: "one version
identifies a tested cross-package workspace state". It does not say how that
intent is enforced across distribution boundaries.

## Motivation

### The failure

Build the workspace and install one adapter wheel on its own:

```bash
uv build --all-packages --out-dir dist/
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python dist/agnara_cli-0.1.0a3-py3-none-any.whl
```

The resolver installs the local `agnara-cli` wheel and fetches `agnara` from
PyPI, because the requirement is unbounded and the published `0.1.0a3`
satisfies it. `develop` has since renamed `agnara.introspection.AppDescriptor`
to `ApplicationDescriptor` under that same version string, so the most basic
command fails:

```text
$ .venv/bin/agnara --version
ImportError: cannot import name 'ApplicationDescriptor' from 'agnara.introspection'
```

`importlib.metadata` shows the substitution directly: `agnara-cli` carries a
`direct_url.json` naming the local wheel, `agnara` carries none.

### An exact pin does not fix it

Rebuilding `agnara-cli` with `dependencies = ["agnara==0.1.0a3"]` and repeating
the install produces the identical `ImportError`. `==0.1.0a3` is satisfied by
PyPI's `0.1.0a3`. This was measured, not reasoned about.

The constraint form governs which *version numbers* an adapter accepts. It
cannot distinguish two builds that carry the same number, and that is exactly
what `develop` produces today.

### Why this is worth deciding now

The reproduction is currently reachable only by someone building the workspace
and installing an adapter without its sibling core, because only `agnara` is
published. That is a narrow audience — and it is precisely the audience
`0.1.0a4` is about. Its gates require reference applications that install
Agnara as an ordinary dependency; if the adapters are published to support
that, this failure becomes reachable by `pip install agnara-http`.

The decision is also expensive to reverse. A constraint form is baked into
published package metadata and cannot be changed for a release already
uploaded, and a version scheme change alters the release procedure.

## The two questions

### Question 1 — constraint form

What should `packages/agnara-*/pyproject.toml` declare?

| Option | Declares | Accepts a differently versioned core | Cost |
| --- | --- | --- | --- |
| **A. Unbounded** (today) | `agnara` | any version, forever | none now; wrong once published |
| **B. Exact pin** | `agnara==0.1.0aN` | none | six extra edits per release unless automated |
| **C. Compatible range** | `agnara>=0.1.0aN,<0.2` | any core in the range | requires a compatibility promise the alpha line does not make |
| **D. Floor only** | `agnara>=0.1.0aN` | any future core | assumes forward compatibility; strictly weaker than C |

Option A is the current state and contradicts ADR 0021's stated intent: an
adapter that accepts any core does not identify a tested workspace state.

Option B matches that intent most directly. Its cost is real but bounded and
mechanical: the release procedure already updates seven `pyproject.toml`
versions in step 2, so pinning adds six dependency edits to an operation that
is already a synchronized sweep. That argues for deciding B and the automation
together rather than treating the automation as a prerequisite.

Options C and D presuppose a compatibility window. `docs/PUBLIC_API.md` says no
API is `stable` during the alpha line and every export is `provisional`, so
there is currently no basis for claiming that a core one alpha newer is
compatible. They become reasonable candidates at `0.1.0b1`, when the beta gates
introduce a supported public API surface — which suggests whatever is decided
now should be revisited there rather than treated as permanent.

### Question 2 — version identity between releases

What version do the seven `pyproject.toml` files carry on `develop` after a
release is published?

| Option | `develop` carries | Reproduction above | Cost |
| --- | --- | --- | --- |
| **A. Last released version** (today) | `0.1.0a3` | remains | none |
| **B. Next-target dev version** | `0.1.0a4.dev0` | fixed | changes ADR 0021 step 2 and the changelog/version consistency gate |
| **C. Local version segment** | `0.1.0a3+dev` | fixed | PEP 440 local versions cannot be uploaded to PyPI, which is a feature here |

Option A is what makes the failure possible: a build of `develop` and the
published release are the same name and different code. PEP 440 exists to
express exactly this distinction, and the project is not currently using it.

Option B is the conventional answer and makes the target explicit, but it
couples `develop`'s version to a decision about which release comes next, and
`RELEASE_PLAN.md` deliberately keeps target selection a separate judgment.
`0.1.0a4` is already the recorded `current_target`, so the coupling exists in
practice; whether it should exist in package metadata is the question.

Option C is weaker but cheaper: it marks a build as not-a-release without
naming the next one. A local version is also unpublishable by construction,
which turns "never publish a `develop` build by accident" from a rule into a
property.

Note that ADR 0021 already reserves a sentinel for a related purpose —
"`0.0.0` remains an unreleased-development sentinel and must not be published"
— so the idea that a non-release build carries a distinguishable version is
not foreign to the existing decision. It was simply only applied before the
first release.

## Interaction with the readiness gates

The `0.1.0a4` gate `reference-apps-exist` asks that reference applications
install Agnara as an ordinary dependency. If the adapters stay unpublished,
those applications cannot use HTTP or MCP at all. If they are published under
the current constraint and version scheme, they can be installed into a state
that raises `ImportError` on import.

Neither is a good answer, which is why this RFC pairs with the separate
question of whether the adapters are published. This RFC does not answer that
one; it establishes what would have to be true first.

## What this RFC does not decide

Nothing. Per `docs/rfc/README.md` an RFC holds an open design question and the
answer belongs in an ADR that supersedes or amends ADR 0021.

It also does not decide whether the adapter distributions are published, or
whether the `develop` version scheme should apply to `agnara` itself as well as
the adapters — the reproduction involves both sides, and a scheme that applies
to only one of them would be incoherent.

## Open questions

- Are questions 1 and 2 answered in one ADR or two? They are independent, but
  the reproduction needs both, and splitting them risks shipping the half that
  does not fix it.
- If B is chosen for question 1, does the version sweep become tooling, or does
  the release procedure carry six more manual edits? ADR 0021's negative
  consequences already name "a change in one package increments every
  first-party package version" as accepted cost.
- Should the CI packaging gate additionally assert that first-party
  requirements were satisfied by the built artifacts rather than an index? The
  #278 gate installs all seven wheels together, which avoids the substitution
  but does not assert its absence.
- Does this get revisited at `0.1.0b1`, when a supported public API surface
  makes a compatibility range meaningful for the first time?

## Prior art

`ARCHITECTURE.md` section 4 fixes the dependency direction between packages.
ADR 0017 fixes distribution and import names. ADR 0021 fixes synchronized
versions and the release procedure. This RFC covers the seam none of them
addresses: what one distribution requires of another once they are separate
installable artifacts rather than one workspace.

## Resolution

ADR 0069 answers both questions together. During alpha, every adapter requires
the exact synchronized core version, and `develop` carries the selected current
target as `<target>.dev0`. The implementation must migrate the project versions,
six core requirements, lockfile, release tooling and gates atomically; none of
those metadata changes are part of this decision-only RFC closure.

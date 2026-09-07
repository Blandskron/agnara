# Public API Stability

This document owns compatibility expectations for Agnara's Python API.
`docs/API_DESIGN.md` owns the intended shape and examples; the machine-readable
[`public-api.json`](public-api.json) file owns the exact classified export list.

## Stability vocabulary

| Classification | Meaning |
| --- | --- |
| `stable` | Compatibility is promised under the stable release policy. Breaking changes require a major release. |
| `provisional` | Intentionally public and expected to remain recognizable, but pre-1.0 feedback may require an incompatible change. |
| `experimental` | Public only for evaluation. It may change or disappear in the next pre-1.0 release. |
| `internal` | Unsupported implementation detail. Internal names are excluded from public manifests and `__all__`. |

No API is classified `stable` during the alpha line. All 123 currently governed
exports are `provisional`: they are deliberate public entry points, but the
alpha line explicitly makes no compatibility promise. A stable classification
requires a later, explicit decision supported by the beta and release-candidate
gates; descriptive phrases such as "stable identifier" do not silently promote
a Python symbol.

## Governed surface

The manifest governs the seven package entry points below, not just the
top-level one. A count is not a substitute: the release gate compares the
ordered names and classifications in the manifest with each module's literal
`__all__`, read without importing the package.

| Module | Exports |
| --- | --- |
| `agnara` | 41 |
| `agnara.introspection` | 23 |
| `agnara.schema` | 15 |
| `agnara.execution` | 14 |
| `agnara.policy` | 13 |
| `agnara.core.di` | 9 |
| `agnara.capability` | 8 |

Governing the subpackages is not a formality. The first three lines of the
README and of `examples/quickstart.py` import from `agnara`, `agnara.core.di`
and `agnara.execution`, so two thirds of the documented entry path lived
outside the governed surface until these manifests existed.

A module the manifest does not name is ungoverned by definition, and 23 of
them are. Thirty modules of the `agnara` package declare a non-empty
`__all__`; the seven above are governed. The rest — `agnara.errors`,
`agnara.application`, `agnara.execution.result` and twenty others — publish
names that nothing classifies, and Historical Reference Applications
#001-#009 import thirteen of them. Issue #289 records the measurement and the
decision it needs: whether each is an entry point, an implementation detail
that should stop declaring `__all__`, or a module whose names belong on its
parent package.

No test asserts the reverse direction. The gate reads the manifest and holds
the implementation to it; it cannot notice a public module the manifest never
mentions, and it cannot name a leaf module at all, because it resolves a
manifest entry only to an `__init__.py`. Adding a public *subpackage* without
classifying it therefore fails nothing today. That test is worth having, but
it cannot be written before the boundary above is decided, because it would
fail on 23 modules on the day it landed.

The manifest resolves module names to files. It may only name modules of the
`agnara` package, and a name that does not resolve inside it is refused rather
than followed.

## Change policy

- Every public addition must enter the manifest with an explicit
  classification in the same change.
- Removing or renaming a provisional API before 1.0 requires a `Changed` or
  `Removed` changelog entry and concrete migration guidance, as ADR 0021
  already requires for pre-1.0 breaks.
- Experimental APIs require a changelog entry when changed or removed;
  migration guidance is provided when a replacement exists.
- Stable APIs are deprecated before removal and may be removed only in a new
  major release. The minimum supported deprecation window will be decided
  before any symbol is promoted to stable.
- Internal names carry no compatibility promise and must not be imported by
  examples, generated projects or integration tests exercising public usage.
- Security fixes may shorten a deprecation path, but the changelog must state
  that exception without disclosing embargoed details.

The manifest is a review gate, not an automatic stability promotion. Updating
the snapshot makes a change explicit; it does not make that change compatible.

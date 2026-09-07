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

No API is classified `stable` during the alpha line. All 218 currently governed
exports are `provisional`: they are deliberate public entry points, but the
alpha line explicitly makes no compatibility promise. A stable classification
requires a later, explicit decision supported by the beta and release-candidate
gates; descriptive phrases such as "stable identifier" do not silently promote
a Python symbol.

## Governed surface

The manifest governs every non-private core module that declares a non-empty
`__all__`: eight package entry points and 22 leaf modules. A count is not a
substitute. The release gate compares each ordered export list and also walks
the source tree in the reverse direction, so adding a public package or leaf
module without classifying it fails the release gate.

| Module | Exports |
| --- | --- |
| `agnara` | 41 |
| `agnara.introspection` | 23 |
| `agnara.schema` | 15 |
| `agnara.execution` | 14 |
| `agnara.policy` | 14 |
| `agnara.core.di` | 9 |
| `agnara.capability` | 8 |
| `agnara.exposure` | 7 |
| `agnara.app` | 2 |
| `agnara.application` | 1 |
| `agnara.capability.definition` | 1 |
| `agnara.capability.identity` | 1 |
| `agnara.capability.metadata` | 4 |
| `agnara.capability.registry` | 2 |
| `agnara.errors` | 12 |
| `agnara.execution.context` | 1 |
| `agnara.execution.invocation` | 1 |
| `agnara.execution.plan` | 1 |
| `agnara.execution.result` | 4 |
| `agnara.execution.runtime` | 2 |
| `agnara.execution.telemetry` | 3 |
| `agnara.introspection.builder` | 2 |
| `agnara.introspection.descriptors` | 13 |
| `agnara.introspection.visibility` | 8 |
| `agnara.policy.base` | 7 |
| `agnara.policy.confirmation` | 4 |
| `agnara.policy.principal` | 2 |
| `agnara.policy.scopes` | 1 |
| `agnara.schema.port` | 3 |
| `agnara.schema.standard` | 12 |

The 22 governed leaf modules include `agnara.errors`, `agnara.application`,
`agnara.execution.result`, `agnara.policy.confirmation` and the implementation
modules underneath the governed packages. Their 87 exports intentionally
remain valid provisional entry points for the alpha line. No symbol was
renamed, promoted or made stable by classifying these spellings.

Governing the subpackages is not a formality. The first three lines of the
README and of `examples/quickstart.py` import from `agnara`, `agnara.core.di`
and `agnara.execution`, so two thirds of the documented entry path lived
outside the governed surface until these manifests existed.

The boundary decision is literal and reviewable: a non-private module with a
non-empty literal `__all__` is public and must be classified. An internal
module uses an underscore-prefixed path or declares no public exports. This
keeps the source declaration, human policy, machine manifest and release gate
in agreement instead of maintaining a second subjective module allowlist.

The manifest resolves both package `__init__.py` files and leaf `.py` modules.
It may only name real non-private modules inside the `agnara` package; anything
outside that root, syntactically invalid, ambiguous or absent is refused rather
than followed (ADR 0074, Issue #289).

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

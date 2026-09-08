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

No API is classified `stable` during the alpha line. All 282 currently governed
exports are `provisional`: they are deliberate public entry points, but the
alpha line explicitly makes no compatibility promise. A stable classification
requires a later, explicit decision supported by the beta and release-candidate
gates; descriptive phrases such as "stable identifier" do not silently promote
a Python symbol.

Nothing is `experimental` today either. `agnara-http` is an `EXPERIMENTAL`
*distribution* in `docs/MATURITY.md`, which is a statement about how settled
the package is; its seven exports are still deliberate entry points rather than
evaluation spikes, so they are `provisional` like everything else. Marking a
symbol `experimental` is a decision to make in the change that introduces it,
not a mood.

## Governed surface

The manifest governs **every shipped distribution**, not the kernel alone. An
application consuming Agnara from outside this repository imports `agnara_http`
and `agnara_mcp` as readily as `agnara`, so a governed core beside an
ungoverned adapter is not a governed framework (ADR 0076).

| Distribution | Import root | Governed modules | Classified exports | Entry point exports |
| --- | --- | --- | --- | --- |
| `agnara` | `agnara` | 30 | 220 | 41 |
| `agnara-a2a` | `agnara_a2a` | 1 | 0 | 0 |
| `agnara-cli` | `agnara_cli` | 1 | 4 | 4 |
| `agnara-events` | `agnara_events` | 1 | 0 | 0 |
| `agnara-http` | `agnara_http` | 2 | 14 | 7 |
| `agnara-mcp` | `agnara_mcp` | 9 | 40 | 20 |
| `agnara-telemetry` | `agnara_telemetry` | 3 | 4 | 2 |

282 exports across 47 modules. A count is not a substitute for the list. The
release gate compares each module's ordered export list against the manifest
and also walks each distribution's source tree in the reverse direction, so
adding a public package or leaf module without classifying it fails the gate.

`agnara-http` and `agnara-mcp` re-export their leaf modules through the package
entry point, so the same name is classified once per module it is reachable
from; that is why a distribution's export total exceeds its entry-point count.

### `agnara`

| Module | Exports |
| --- | --- |
| `agnara` | 41 |
| `agnara.app` | 2 |
| `agnara.application` | 1 |
| `agnara.capability` | 8 |
| `agnara.capability.definition` | 1 |
| `agnara.capability.identity` | 1 |
| `agnara.capability.metadata` | 4 |
| `agnara.capability.registry` | 2 |
| `agnara.core.di` | 9 |
| `agnara.errors` | 12 |
| `agnara.execution` | 14 |
| `agnara.execution.context` | 1 |
| `agnara.execution.invocation` | 1 |
| `agnara.execution.plan` | 1 |
| `agnara.execution.result` | 4 |
| `agnara.execution.runtime` | 2 |
| `agnara.execution.telemetry` | 3 |
| `agnara.exposure` | 7 |
| `agnara.introspection` | 23 |
| `agnara.introspection.builder` | 2 |
| `agnara.introspection.descriptors` | 13 |
| `agnara.introspection.visibility` | 8 |
| `agnara.policy` | 14 |
| `agnara.policy.base` | 7 |
| `agnara.policy.confirmation` | 4 |
| `agnara.policy.principal` | 2 |
| `agnara.policy.scopes` | 1 |
| `agnara.schema` | 16 |
| `agnara.schema.port` | 3 |
| `agnara.schema.standard` | 13 |

Governing the subpackages is not a formality. The first three lines of the
README and of `examples/quickstart.py` import from `agnara`, `agnara.core.di`
and `agnara.execution`, so two thirds of the documented entry path lived
outside the governed surface until these manifests existed.

### `agnara-http`

| Module | Exports |
| --- | --- |
| `agnara_http` | 7 |
| `agnara_http.composition` | 7 |

The package re-exports one module, so the two lists must not diverge.
`docs/HTTP_COMPOSITION.md` is the supported guide; the documentation UI
providers, the Explorer and the authorized discovery endpoint are implemented
but deliberately unreachable through this surface (ADR 0071, ADR 0072).

### `agnara-mcp`

| Module | Exports |
| --- | --- |
| `agnara_mcp` | 20 |
| `agnara_mcp.authorization` | 4 |
| `agnara_mcp.discovery` | 1 |
| `agnara_mcp.dispatch` | 3 |
| `agnara_mcp.interaction` | 2 |
| `agnara_mcp.protocol` | 3 |
| `agnara_mcp.result` | 2 |
| `agnara_mcp.schema` | 1 |
| `agnara_mcp.tools` | 4 |

### `agnara-telemetry`

| Module | Exports |
| --- | --- |
| `agnara_telemetry` | 2 |
| `agnara_telemetry.metrics` | 1 |
| `agnara_telemetry.tracing` | 1 |

### `agnara-cli`

| Module | Exports |
| --- | --- |
| `agnara_cli` | 4 |

`agnara-cli` is consumed as the `agnara` command. `EXIT_OK`, `EXIT_FAILED`,
`EXIT_USAGE` and `main` are what a caller needs to run that command in-process,
and nothing else is a contract. Thirteen further names — manifest parsing,
generation planning and target resolution — were re-exported from
underscore-prefixed modules through `0.1.0a3` without ever being documented,
used or designed as an API; `0.1.0a4` removes them (ADR 0076). Code that
needs them is reading the CLI's implementation and should say so by importing
the private module directly.

### `agnara-a2a` and `agnara-events`

| Module | Exports |
| --- | --- |
| `agnara_a2a` | 0 |
| `agnara_events` | 0 |

Both distributions hold a reserved namespace: they own a package boundary and a
dependency direction, and export nothing. The empty surface is classified
rather than merely absent, because an empty `__all__` is skipped by the reverse
walk — without a manifest entry, a reserved namespace would be the one place a
first export could appear ungoverned.

### Where the boundary is

The boundary decision is literal and reviewable: a non-private module with a
non-empty literal `__all__` is public and must be classified. An internal
module uses an underscore-prefixed path or declares no public exports. This
keeps the source declaration, human policy, machine manifest and release gate
in agreement instead of maintaining a second subjective module allowlist.

The manifest resolves both package `__init__.py` files and leaf `.py` modules.
It may only name real non-private modules inside the distribution that declares
them; anything outside a workspace package, belonging to a sibling
distribution, syntactically invalid, ambiguous or absent is refused rather than
followed (ADR 0074, ADR 0076, Issue #289).

## Auditing an application

`scripts/check_public_imports.py` decides mechanically whether a tree consumes
Agnara through the governed API only. It reads `public-api.json`, parses Python
files and the Python shown in Markdown fences, and reports every import that
names an unclassified module or pulls an unclassified name out of a classified
one.

```bash
python scripts/check_public_imports.py path/to/an/application
```

It runs on trees outside this workspace on purpose, so an application built
against Agnara can be audited with exactly the rule the repository holds its
own examples to. A finding is a framework defect to fix or record, not an
application detail to work around.

Inside this repository the rule is enforced on `examples/`, `README.md` and the
guides under `docs/`. `docs/adr/` and `docs/rfc/` are exempt because a decision
record may quote a rejected or superseded spelling, and `tests/` and
`benchmarks/` are exempt because exercising and measuring internals is what
internals are for. The exemptions are listed with their reasons in
`tests/architecture/test_public_import_audit.py`, so widening them is an edit
rather than an omission.

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

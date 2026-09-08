# ADR 0074 — Complete Core Public-Module Governance

- Status: Proposed
- Date: 2026-09-07
- Tracking: GitHub Issues #288 and #289

## Context

The public API manifest classified eight package entry points, while 22
non-private leaf modules also declared non-empty `__all__` lists. Those lists
are explicit publication signals, several are used by external reference
applications, and no release check noticed additions or changes to them.

The audit also found three private/deep imports in historical applications.
One (`agnara.policy.confirmation.ConfirmationPolicy`) was a deliberately
exported leaf name; two were genuinely private helpers.

## Decision

Every non-private module in the core distribution that declares a non-empty
literal `__all__` is a provisional public entry point during the alpha line.
The manifest classifies both package and leaf modules, and the automated gate
walks source in the reverse direction so a new exported module cannot escape
classification.

`ConfirmationPolicy` is additionally re-exported from `agnara.policy`, beside
the other confirmation contracts. This is an additive provisional API change.

The two genuinely private helpers stay private:

- `agnara._frozen.frozen_slots_dataclass` is a CPython compatibility shim for
  Agnara's own value types, not an application model API. Applications use the
  standard-library dataclass decorator.
- `agnara.execution.runtime._tracking_id` is an implementation detail. Its
  supported observable output is `tracking_id` on public telemetry events, so
  consumers test it through `TelemetryHook` rather than calling the resolver.

Historical applications are not modified in this repository. Their next audit
must use these supported paths; a private test convenience does not become a
framework contract merely because an application imported it.

## Consequences

- All 218 exports across 30 core modules are classified `provisional`.
- Deep imports from a governed leaf are supported during the alpha line.
- Adding a public package or leaf module without updating the manifest fails
  both the readiness checker and its architecture tests.
- No internal helper is promoted to satisfy an accidental external import.
- Beta/RC work still decides whether any provisional spelling becomes stable.

## Threat analysis

Manifest paths are resolved only inside the core source root. Invalid,
underscore-prefixed, missing or ambiguous module paths are refused, preventing
the JSON document from redirecting the checker outside the distribution.
Literal AST inspection avoids importing untrusted package code during release
readiness evaluation.

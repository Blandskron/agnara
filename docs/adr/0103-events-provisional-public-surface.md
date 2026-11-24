# ADR 0103 — Provisional Events public surface

- Status: Proposed
- Date: 2026-11-24
- Tracking: GitHub Issue #804 (EVT-04)
- Related: ADR 0070, ADR 0073, ADR 0099, ADR 0101, RFC 0011

## Context

[ADR 0101](0101-initial-inbound-event-projection.md) established the initial
inbound CloudEvents 1.0 structured-mode projection, 13-outcome manual
settlement table, cooperative host shutdown lifecycle and opt-in AsyncAPI 3.1.0
Draft-07 export. EVT-03 implemented those modules internally under
`agnara_events` and verified them both in unit/conformance suites and against a
live RabbitMQ 4.2.5 / `aio-pika` 9.6.1 container, while keeping
`agnara_events.__all__` empty.

As with `agnara-a2a` under [ADR 0099](0099-a2a-provisional-public-surface.md),
the profile needs an importable, manifest-governed surface so applications can
compose inbound event consumers without reaching into private underscore modules,
while keeping signatures free to evolve before any 1.x stability commitment.

## Decision

### D1 — Stability: provisional

Every `agnara_events` export is classified `provisional` in
[public-api.json](../public-api.json). A provisional name is governed,
importable and checked by the release gates like a stable one, but its signature
and behaviour may change in a minor release after a reviewed decision. It is not
part of the 1.x compatibility promise. Promotion to `stable` requires a separate
accepted ADR and wider operational evidence.

### D2 — Exports

| Name | Role |
| --- | --- |
| `declare_inbound_event`, `compile_inbound_event`, `compile_event_surface` | Declare and compile one inbound subscription and emit its ADR 0070 surface record. |
| `EventSubscriptionExposure`, `CompiledEventBinding`, `EventsDefinitionError` | Immutable exposure/binding value types and composition refusal error (`DefinitionError`). |
| `Delivery`, `DeliverySource` | Broker-neutral delivery and single-consumer source protocols implemented by the host. |
| `consume_inbound_events`, `ConsumerBudgets`, `ConsumerDiagnostic`, `SettlementAction`, `SettlementUncertaintyError` | Serial single-in-flight consumer runtime, finite budgets, redacted diagnostics and settlement uncertainty error. |
| `project_asyncapi`, `AsyncAPIInfo`, `AsyncAPIExportError` | Opt-in filtered AsyncAPI 3.1.0 / JSON Schema Draft-07 projector and safe export error. |
| `CLOUDEVENTS_JSON_CONTENT_TYPE`, `ASYNCAPI_VERSION`, `DRAFT_07_SCHEMA_FORMAT` | Exact media type and specification constants for the profile. |

### D3 — Zero broker or schema-library dependencies

`agnara-events` declares only `agnara==1.0.4` in `pyproject.toml` and imports
only Python's standard library and public `agnara` packages. Broker SDKs,
connection management, dead-letter policies and JSON Schema validators stay in
the host or test fixtures.

### D4 — Distribution role and maturity

`agnara-events` changes role from `reserved` to `adapter` in
[distributions.json](../distributions.json). Its maturity moves from
`PLANNED` to `EXPERIMENTAL` in [MATURITY.md](../MATURITY.md), reflecting the
provisional complete-result inbound profile without claiming multi-broker
support, event publishing, streaming handlers or confirmation channels.

## Consequences

- Applications can import `agnara_events` names through the governed public API
  audit (`scripts/check_public_imports.py`) without private module imports.
- Every `agnara_events` export remains `provisional` until promoted explicitly.
- All seven distributions in `docs/distributions.json` now expose governed
  import surfaces (`1` kernel, `6` adapters).

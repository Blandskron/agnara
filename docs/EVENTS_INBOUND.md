# Consuming inbound CloudEvents 1.0 deliveries

The provisional exports in [ADR 0103](adr/0103-events-provisional-public-surface.md)
implement the inbound CloudEvents 1.0 structured-mode profile decided in
[ADR 0101](adr/0101-initial-inbound-event-projection.md). Broker transport
libraries stay outside `agnara-events`; the host implements `Delivery` and
`DeliverySource`.

## Run the example

With Python >=3.14, from the repository root:

```bash
uv sync --locked
uv run python examples/events_inbound.py
```

The complete [source](../examples/events_inbound.py) uses an in-memory delivery
source and standard-library types only. The output lines are:

```text
asyncapi: 3.1.0
surfaces: 1
success: acknowledge
conflict: reject
invalid_input: reject
type_mismatch: reject
internal_failure: release
cancelled: release
```

Followed by the ordered resource lifecycle trace ending with `ledger.close`,
`delivery.release`, and `container.close`. The intentional handler failure also
emits a redacted operator warning on standard error; private diagnostic text
never appears in `ConsumerDiagnostic`.

## Declare once and bind a host-verified principal

At composition, `declare_inbound_event` binds a registered capability to a
logical `subscription_id`, exact CloudEvents `type`, host-verified `Principal`,
and optional logical `public_address` (without URL schemes or credentials).
`compile_inbound_event` refuses streaming capabilities and capabilities requiring
confirmation, then `compile_event_surface` emits the ADR 0070 surface record.

Producer attributes, headers, and extension fields cannot select a capability,
principal, tenant, or injected dependency. Decoded `data` passes to the
compiled plan with a fresh `ExecutionContext`, `materialize_json`, and a
monotonic `attempt_seconds` deadline.

## Envelope bounds and settlement table

`consume_inbound_events` decodes structured `application/cloudevents+json`
objects (`specversion == "1.0"`, `65,536`-byte limit before UTF-8 decode,
nesting depth `32`, no duplicate keys, no non-finite numbers, no `data_base64`,
and no batches) and maps every canonical outcome:

- `Success` -> `acknowledge` (return value discarded)
- Malformed envelope, `type_mismatch`, `invalid_input`, `unauthenticated`,
  `forbidden`, `interaction_required`, `not_found`, `conflict` -> `reject`
- `rate_limited`, `unavailable`, `timeout`, `internal_failure`, or unfinished
  delivery cancelled on shutdown -> `release`

If settlement fails, consumption stops immediately and raises
`SettlementUncertaintyError` with redacted correlation metadata.

## Opt-in AsyncAPI 3.1.0 projection

`project_asyncapi` filters out private exposures (`public_address=None` or
`is_visible(...) == False`) before translating remaining input schemas into
JSON Schema Draft-07 (`application/schema+json;version=draft-07`). Protected DI
parameters and server URLs are omitted. Note that Draft-07 accepts lexically
integral floats such as `2.0` as `integer`, whereas strict Python runtime
validation rejects `2.0` as `invalid_input`.

## Verification and limits

```bash
uv run python -m pytest tests/events tests/docs/test_events_inbound_example.py
uv run python -m pytest tests/release/test_integrated_dogfooding.py
uv run python scripts/check_public_imports.py examples/events_inbound.py docs/EVENTS_INBOUND.md
```

The installed-artifact gate builds all seven candidate wheels, installs them
outside the checkout, copies the exact example, and runs the
[consumer](../tests/reference_apps/events_guide.py) under Python `-I`.
For a live RabbitMQ 4.2.5 / `aio-pika` 9.6.1 round-trip fixture using Docker,
see [experiments/events/README.md](../experiments/events/README.md). Exports
stay `provisional` and maturity stays `EXPERIMENTAL`; event publishing, binary
mode, batches, streaming handlers, and per-producer dynamic principals remain
outside this profile.

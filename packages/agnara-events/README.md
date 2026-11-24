# agnara-events

`agnara-events` provides Agnara's provisional inbound CloudEvents 1.0
structured-mode adapter and opt-in AsyncAPI 3.1.0 / JSON Schema Draft-07
projection ([ADR 0101](../../docs/adr/0101-initial-inbound-event-projection.md),
[ADR 0103](../../docs/adr/0103-events-provisional-public-surface.md)).

```bash
pip install "agnara-events==1.0.4"
```

All 19 exports in `agnara_events` are classified `provisional` in
`docs/public-api.json` and may change before promotion. The package depends only
on the synchronized `agnara` kernel and Python's standard library; broker SDKs,
connections and retry topologies remain host-owned behind `Delivery` and
`DeliverySource`.

See the [inbound events guide](../../docs/EVENTS_INBOUND.md),
[public API policy](../../docs/PUBLIC_API.md) and
[maturity matrix](../../docs/MATURITY.md).

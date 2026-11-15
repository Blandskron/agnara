# ADR 0101 — Initial inbound event projection

- Status: Proposed
- Date: 2026-11-13
- Tracking: GitHub Issue #787 (EVT-02)
- Related: ADR 0017, ADR 0018, ADR 0046, ADR 0070, ADR 0086, ADR 0091,
  ADR 0094, RFC 0011

## Context

[EVT-01](../../experiments/events/README.md) exercised RabbitMQ 4.2.5 and
aio-pika 9.6.1 on Python 3.14.4. The fixture observed commit before
acknowledgement, safe replay after channel loss, publish ACL enforcement,
scope refusal, bounded redelivery and cooperative shutdown. The inventory
revision `9007199254740993` survived the broker, decoder, compiled input
and SQLite. The Draft 07 probe translated one fixed tuple and exposed a
difference between JSON Schema's integer semantics and Python validation.

The fixture uses a Pydantic experiment for inventory bounds and an
application return value for snapshot conflicts. EVT-03 must exercise the
compiled input contract and report a conflict as canonical `Failure(CONFLICT)`
so the consumer never interprets an application-specific success value.
The single-node evidence covers channel loss. Restart, reconnect and
cluster failover require separate evidence.

## Proposed decision

### Composition and authority

Start with one inbound subscription bound at startup to one registered
complete-result execution plan, one allowed CloudEvents type and one
host-verified service principal. Refuse streaming and
confirmation-requiring plans at composition. Use the compiled plan to
validate inputs, run policies, acquire dependencies and validate the
declared output. Discard the successful output after settlement. Publishing
events, request/reply and per-producer principals need separate decisions.

The host configures broker ACLs and authenticates its connection. The first
fixture allows one authoritative publisher on the channel. The subscription
principal is independent of that publisher's credential. Producer attributes
and headers cannot select the capability, principal, tenant, confirmation
evidence or dependencies. Invoke with only the decoded `data` object and a
fresh context. An insufficient scope fails before effects through the
existing policy boundary. The host must stop or recompose the subscription
when it learns that the configured principal has been revoked. The fixed
principal has no automatic refresh contract.

### Envelope and bounds

Accept one UTF-8 JSON object with media type `application/cloudevents+json`
and `specversion` equal to `1.0` in the first profile. Compare the event type
to the exact configured value. Require a nonempty string ID and a nonempty
URI-reference source. Require object-valued `data` and allow
`datacontenttype` to be absent or exactly `application/json`. Reject
`data_base64`, batches and binary-mode deliveries. Ignore optional
attributes and extensions after parsing. The [CloudEvents JSON snapshot]
defines the envelope; these restrictions define the initial profile.

Use a 65,536-byte body limit before decoding, a maximum JSON nesting
depth of 32, and the interpreter's integer digit bound. Reject invalid
UTF-8, duplicate member names at any depth, non-finite numbers (including
overflow during parsing) and malformed or over-limit bodies before
invocation. Preserve integer tokens as Python integers without a
floating-point intermediate. The initial broker fixture must also bound
broker message size because the client may buffer a delivery before the
adapter checks its length. EVT-01 implemented a body length guard and
demonstrated type refusal and integer fidelity. Boundary tests for the size
limit and stricter parser are EVT-03 acceptance requirements.

### Delivery and settlement

| Canonical outcome | Settlement request |
| --- | --- |
| Success | Acknowledge after the compiled invocation returns. |
| Malformed envelope or mismatched type | Reject without requeue. |
| `invalid_input` | Reject without requeue. |
| `unauthenticated` | Reject without requeue. |
| `forbidden` | Reject without requeue. |
| `interaction_required` | Reject without requeue. |
| `not_found` | Reject without requeue. |
| `conflict` | Reject without requeue. |
| `rate_limited` | Release for bounded redelivery. |
| `unavailable` | Release for bounded redelivery. |
| `timeout` | Release for bounded redelivery. |
| `internal_failure` | Release for bounded redelivery with redacted diagnostics. |
| Cancellation before invocation completes | Release unfinished delivery during shutdown when the channel permits. |

Use one in-flight message with prefetch one and manual settlement. The
RabbitMQ fixture uses a quorum queue with delivery limit 2 and a dead-letter
route. EVT-01 observed delivery counts 0, 1 and 2 for forced transient
failure. Require effective bounded redelivery and dead-letter configuration
for the next fixture. Verify those properties against the real broker before
generalizing the consumer contract. Reject and release map to
`reject(requeue=False)` and `reject(requeue=True)` on the pinned client.
An acknowledgement or rejection call sends a frame without a broker
response. If a channel fails while settling, stop consumption and surface
settlement uncertainty to the host. A delivery tag from that channel cannot
be reused. The host explicitly opens a new session. Redelivery and final
disposition depend on broker state. [RabbitMQ quorum queues] · [aio-pika API]

The broker owns dead-letter routing and may retain the producer's original
body and headers. The fixture must restrict access to that queue. Adapter
diagnostics expose only safe categories and locally generated correlation
identifiers. They omit payloads, raw exception text and policy internals.

Duplicates reach the capability. `source` and `id` carry no authority and
provide no adapter deduplication. Application effects must tolerate replay
under the profile's retry and settlement model. The inventory fixture does
so by applying an absolute snapshot with a monotonic business revision in
one transaction. Serial invocation limits local concurrency. Redelivery can
reorder work, so the profile promises no global or per-key delivery order.

### Host lifecycle

The host owns a single consumer and its broker connection on the
container's loop. It supplies finite positive attempt and shutdown budgets.
Derive each attempt's monotonic deadline at entry. On shutdown, stop
receiving, let the owned invocation finish within the budget, then cancel and
join unfinished work before releasing its delivery. Completed invocations
use the outcome table while the channel is usable. Close the broker
connection before the container. Treat failed release as a channel failure
and rely on the broker's unacknowledged-delivery handling. Cleanup is
cooperative, so a deadline does not prove that resources closed or that
effects rolled back. No hidden consumer task or reconnect loop is implied.
EVT-03 must test stop/settlement races and observable cleanup order.

### AsyncAPI projection

Propose opt-in [AsyncAPI 3.1.0] output from the same served subscription
snapshot, filtered before building the document. Publish one `receive`
operation referencing its channel and message. Use an explicitly public
logical channel address configured for the real subscription. Keep server
URLs, credentials, topology and internal authority out of the document.
Describe the structured envelope as the message payload with
`application/cloudevents+json` content type. Embed the compiled input
schema under its `data` property. Omit protected inputs and validate
both the whole document and the payload. Discovery grants no authority.

Declare `application/schema+json;version=draft-07` explicitly. Recursively
permit a small schema subset with boolean schemas, primitive types,
`enum`, `const`, numeric bounds, string length bounds, object
`properties`/`required`/`additionalProperties`, and homogeneous array
`items` and length bounds. A fixed tuple with `prefixItems`, `items: false`
and exact length constraints becomes Draft 07 array-form `items` with
`additionalItems: false`, preserving the lengths and positional schemas.
Use an allowlist of schema keywords at schema positions, not on object
property names or literal values. Refuse unsupported shapes, references,
unreviewed dialect keywords, non-JSON fragments and non-finite values.
Fail export for an unsupported **visible** exposure with a safe diagnostic.
A filtered private exposure must never appear in the document or the error.
Serving the consumer and exporting its documentation have separate lifecycles.

Draft 07 can accept an integral floating-point literal such as `2.0` as an
integer. The compiled Python input can reject it. Document this lexical
difference and test both results. Keep runtime validation authoritative.
EVT-01 checked Draft 07 payload fragments. Full AsyncAPI document validation
and the refusal path belong in EVT-03.

## API and follow-up

The [governed manifest](../public-api.json) lists zero exports for
`agnara_events`. Review the following composition operations against the
manifest before assigning public names. EVT-03 can exercise them internally.

| Operation | Inputs and result |
| --- | --- |
| Declare | A registered capability identity, subscription identity, event type, host principal and optional publication address. Produces an explicit inbound exposure. |
| Compile | The exposure and registered plans. Produces an immutable binding after checking the capability profile and configuration. |
| Consume | The compiled binding, an owned container, a delivery source and finite lifecycle budgets. Runs until the host stops it or the session fails. |
| Project | The served binding and explicit publication configuration. Produces a detached AsyncAPI document or a safe export error. |

The delivery interface supplies receive, acknowledge, reject and release.
Keep queue topology, delivery tags and client types inside the RabbitMQ
integration fixture. Core and the base events package have no broker
dependency.

After maintainer review, scope EVT-03 to real broker round trips with the
pinned client, coverage of every settlement row, decoder and lifecycle
failures, and a validated AsyncAPI sample with unsupported-schema tests.
EVT-04 governs any later package, public exports, runnable guide and support
claims. [Maturity](../MATURITY.md) describes the current shipped surface.

[CloudEvents JSON snapshot]: https://github.com/cloudevents/spec/blob/fc1f6f31f5f011a72183f1bcea20c987cb683ade/cloudevents/formats/json-format.md
[AsyncAPI 3.1.0]: https://github.com/asyncapi/spec/blob/b3fac5bb522771428ea57b16129b273cd3ea0180/spec/asyncapi.md
[RabbitMQ quorum queues]: https://www.rabbitmq.com/docs/4.2/quorum-queues
[aio-pika API]: https://docs.aio-pika.com/apidoc.html

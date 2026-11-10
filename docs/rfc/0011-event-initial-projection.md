# RFC 0011 — Initial event projection boundary

- Status: Open research; no implementation decision
- Date: 2026-10-28
- Tracking: GitHub Issue #691
- Related: ADR 0017, ADR 0018, ADR 0046, ADR 0070, ADR 0084, ADR 0086,
  ADR 0091, ADR 0094, RFC 0005, RFC 0009, RFC 0010

## Purpose and current boundary

Determine the smallest useful event adapter that preserves Agnara's capability
semantics. `agnara-events` reserves a namespace and exports nothing.
[Architecture](../../ARCHITECTURE.md) assigns it event capability
abstractions, AsyncAPI projection and broker plugins, and forbids hardcoding
Kafka, NATS or RabbitMQ in the base package. This proposal adds no broker
client, dependency, endpoint, public syntax or support claim.
[Maturity](../MATURITY.md) remains authoritative.

"Event" is overloaded in this repository. Telemetry start/terminal events
(ADR 0023) and stream units (ADR 0084) are not broker messages and are not
in scope. ADR 0084 deliberately has no core event envelope or event-kind
vocabulary, and this proposal does not add one.

## Research checkpoint and source hierarchy

The checkpoint was read on 2026-10-28.

| Identity | Inspected source | Meaning here |
| --- | --- | --- |
| Documentation format | [AsyncAPI 3.1.0][asyncapi], commit `b3fac5bb522771428ea57b16129b273cd3ea0180` | Candidate contract for describing channels and operations; not a runtime protocol. |
| Event envelope | [CloudEvents v1.0.2][cloudevents], tag `ce@v1.0.2`, commit `fc1f6f31f5f011a72183f1bcea20c987cb683ade` | Candidate interoperable envelope; not an Agnara core type. |
| Broker / client SDK | None selected | A later feasibility slice selects one isolated broker and client with an ADR 0010-style pin. |

Facts from those snapshots that shape the options:

- An AsyncAPI document describes one **application**. Each operation has an
  `action` of `send` or `receive` relative to that application, a channel
  reference and message references. Protocol-specific details live in
  bindings. A `reply` object describes request/reply.
- The AsyncAPI Schema Object is a superset of **JSON Schema Draft 07**. The
  formats every implementation must support are the AsyncAPI 3.1.0 Schema
  Object and Draft 07. JSON Schema 2020-12 is not listed; a custom
  `schemaFormat` is allowed but its implementation is optional.
- CloudEvents requires `id`, `source`, `specversion` and `type`. Producers must
  keep `source` + `id` unique per distinct event, a re-sent duplicate may reuse
  them, and consumers may treat identical pairs as duplicates. Context
  attributes should not carry sensitive information, and intermediaries may log
  them. Intermediaries must forward events of 64 KB or less, and consumers
  should accept at least that size.

An observation from the current repository: the kernel's standard schemas
emit `prefixItems` for fixed tuples, a JSON Schema 2020-12 keyword with no
Draft 07 equivalent of the same name. Publishing compiled schemas as AsyncAPI
Schema Objects unchanged would therefore be inaccurate. ADR 0097 can publish
compiled schemas directly because OpenAPI 3.2 Schema Objects build on JSON
Schema 2020-12; AsyncAPI 3.1.0 offers no such match.

## Options

| Option | Benefit | Unresolved cost |
| --- | --- | --- |
| AsyncAPI document only | Exercises filtered discovery without a broker. | Describes operations nothing serves; like an unserved A2A card (RFC 0010), it misleads consumers. |
| Inbound `receive`: one capability consumes one subscription | Reuses the complete-result invocation boundary; each message is one invocation and its outcome decides acknowledgement. | Needs a delivery contract (ack, redelivery, dead letter), a non-caller principal model and owned consumer concurrency. |
| Outbound `send`: publish declared events | Documents what an application emits. | Applications can already publish through their own port without the framework. Making it reliable means an outbox, transactions and durable storage the kernel does not have. |
| Request/reply over a broker | Matches AsyncAPI `reply`. | Combines both directions with correlation, timeouts and reply-address trust; this is essentially RPC over a broker. |

Investigate inbound `receive` first, with AsyncAPI projection of the served
operations in the same feasibility fixture. Outbound publication and
request/reply need their own RFC follow-up. Producer-side reliability must not
be implied by documenting a `send` operation.

## Candidate inbound profile

Every statement in this section is a proposed constraint to test, not a
description of a shipped API.

### Composition and dispatch

One subscription selects exactly one complete-result capability and its
compiled plan, recorded as an ADR 0070 exposure. The channel and the
CloudEvents `type` the subscription accepts are configured at composition. A
message's attributes never select another capability; a `type` mismatch is
refused without invocation. Streaming capabilities (ADR 0084) are not
consumers in the first profile.

The base `agnara-events` package would own a broker-neutral consumer port
(receive, acknowledge, reject, release). Broker integrations would be separate
plugins, following ADR 0017 naming, with their own exact pins. The base package
imports no broker client. The core imports nothing from either.

### Envelope and input

Messages are CloudEvents 1.0 with `datacontenttype` `application/json` (or
absent with JSON data), in the structured or binary mode the selected broker
binding defines. `data` is a JSON object of capability inputs and is the only
input source. The compiled input contract remains authoritative. `subject`,
`time`, extensions and broker headers are untrusted metadata: they are not
forwarded as inputs, dependency values or trusted context. Whether non-JSON
data or other envelopes are ever accepted is a separate decision.

Each broker client's decoder must be inspected for the numeric-fidelity
problem ADR 0098 found in protobuf `Value`. The feasibility slice must show
that integers survive decoding before relying on the kernel's strict integer
validation.

### Principal and authority

A broker message has no per-request caller authentication equivalent to an
HTTP credential. The proposed model is that the host authenticates the
**connection** to the broker. A subscription is composed with an explicit,
host-verified service principal, and every invocation from that subscription
runs as that principal. Policy, confirmation and validation still run before
dependency acquisition and handler effects.

CloudEvents `source`, extension attributes and broker headers are
producer-asserted. They never become the principal, a tenant selector or
confirmation evidence. Producer authentication is a broker/ACL property; a
per-producer principal needs the broker to supply verified identity and a
separate decision. Capabilities requiring confirmation cannot be satisfied
without a human channel, and the first profile should refuse them at
composition.

### Delivery semantics and failures

The profile assumes at-least-once delivery: a message can be delivered more
than once and acknowledgement follows completion, never precedes it. The
feasibility report must map every canonical `FailureCode` to an outcome. The
starting proposal:

| Outcome | Broker action | Rationale |
| --- | --- | --- |
| `Success` | Acknowledge | Output is validated by the declared contract, then discarded. Results are not published without an outbound decision. |
| Envelope invalid, `type` mismatch, `invalid_input` | Reject without redelivery (dead letter where available) | Redelivery cannot fix the message. |
| `unauthenticated`, `forbidden`, `interaction_required` | Reject without redelivery | A subscription principal problem or missing human channel; retrying would loop. |
| `not_found`, `conflict` | Reject without redelivery by default | Application-specific. A per-exposure retry choice may be needed. |
| `rate_limited`, `unavailable`, `timeout` | Release for bounded redelivery | Transient, but bounded so a poison message cannot loop forever. |
| `internal_failure` | Bounded redelivery, then dead letter | Unknown cause; diagnostics stay redacted. |
| Consumer shutdown before completion | Release, never acknowledge | The work was not completed. |

Brokers differ in dead-letter, delay and redelivery-count support. The port
must expose what the selected broker actually offers rather than emulating
missing features in memory.

Duplicate suppression is not automatic. ADR 0091 allows an adapter to use the
idempotency runtime only after an accepted adapter decision defines its
authenticated principal and a scoped selector. A candidate key is the
subscription plus CloudEvents `source` + `id`. That key is producer-controlled:
a producer with publish rights could collide with another's IDs to suppress
its events. Using it needs a broker that authenticates producers, or an
explicit single-trusted-producer assumption. Until then, at-least-once
duplicates reach handlers, and the documentation must say so.

### Limits, ordering and lifecycle

A consumer is owned concurrent work. The host's lifespan starts it inside
structured concurrency on one event loop. The adapter bounds in-flight
invocations (prefetch/concurrency) and joins every task on shutdown. No core
fire-and-forget task, global consumer registry or hidden thread is introduced.
On shutdown the consumer stops receiving, lets in-flight invocations finish or
cancels them at a deadline, releases unfinished messages, then closes the
broker connection and finally the container.

Each invocation has a configured deadline, and expiry is `timeout`. A size
limit applies before decoding; CloudEvents' 64 KB interoperability floor is a
reasonable default to evaluate, not a decided value. Ordering guarantees
(per partition, key or queue) are broker-specific. Concurrency above one may
reorder processing, and the profile must state the ordering it preserves for
the selected broker rather than implying global order.

### AsyncAPI projection

Filter exposures and fields before constructing the document (ADR 0018,
ADR 0046). Publish one `receive` operation per served subscription, with its
channel, message and the CloudEvents content type. Server URLs, credentials,
broker topology and private capabilities are not published automatically, and
publication grants no authority.

Message payload schemas come from the compiled input contract. Because
AsyncAPI's default schema format is Draft 07, the projection must either
translate the supported 2020-12 constructs faithfully (for example
`prefixItems` to Draft 07 array-form `items` with `additionalItems: false`) or
refuse the exposure. A non-standard `schemaFormat` that tooling may ignore is
not acceptable. The `agnara schema asyncapi` command listed in the
[CLI specification](../CLI_SPEC.md) stays unimplemented until this projection
exists.

## Feasibility gates and proposed work sequence

These work packages require their own Issues and review. No runtime package,
dependency or workflow change is authorized by this RFC.

| Slice | Required evidence before closure |
| --- | --- |
| EVT-01: broker and envelope feasibility | Select one broker and one client for an isolated, hash-locked experiment on Python 3.14. Show receive/ack/reject/release, redelivery counting, dead-letter behavior, graceful shutdown with in-flight messages and numeric fidelity. Inventory client defaults (threads, prefetch, auto-ack, reconnect). Inspect the AsyncAPI Draft 07 translation of current kernel schemas. Record platform limits honestly. |
| EVT-02: projection decision | An ADR settles dispatch, envelope, principal, the complete failure/ack table, dedupe stance, limits, ordering, lifecycle and AsyncAPI schema translation. A public-API proposal is reviewed against the manifest, with no example imports. |
| EVT-03: internal adapter fixture | Real broker round trips in CI through the compiled invocation path, with no handler/policy reimplementation. Broker SDK types stay inside the plugin or experiment. |
| EVT-04: governed usable surface | Separate approval for exports, distributions, exact pins, installed-wheel consumers, runnable examples, AsyncAPI generation and maturity changes proven by CI. |

## Threat and acceptance matrix

| Boundary | Required future test evidence |
| --- | --- |
| Dispatch | Message `type`, extensions, headers or `source` cannot select another capability; mismatches are refused without invocation. |
| Authority | Producer-asserted attributes never become the principal, tenant or confirmation evidence. Unauthorized subscription principals are refused before DI and handler effects. |
| Delivery | No acknowledgement before completion. Every outcome row is asserted, poison messages stop at the redelivery bound and shutdown releases unfinished work. |
| Duplicates | Redelivered messages are documented as reaching handlers unless an accepted dedupe decision exists; colliding producer IDs cannot suppress another producer's events where dedupe is enabled. |
| Shape and limits | Oversized, malformed, non-JSON and wrong-type messages fail before effects; integers survive decoding. |
| Redaction | Dead-lettered messages and logs carry no secret values, exception text or policy internals beyond what the producer sent. |
| Lifecycle | Bounded concurrency, joined tasks, same-loop cleanup, cancellation propagation and broker reconnect behavior are proven for the chosen client. |
| Discovery | AsyncAPI documents only served operations, filtered before serialization, with schemas valid under the declared format. |
| Packaging | Core and the base package import no broker client; sibling adapters are not dependencies. |

## Questions requiring a decision

1. Is inbound consumption the right first projection, or should outbound
   publication with an explicit application port come first?
2. Which broker and client should EVT-01 use, given lifecycle control, explicit
   acknowledgement, dead-letter support and Python 3.14 availability?
3. Is a per-subscription service principal sufficient, and what broker identity
   evidence would justify per-producer principals?
4. Should CloudEvents be mandatory, or should the broker-native message format
   be supported first? Which binding mode is used?
5. What is the default failure/ack table, retry bound and dedupe stance, and
   which choices are per-exposure configuration?
6. How should the AsyncAPI projection treat kernel schemas without a faithful
   Draft 07 translation?

Record answers in a later ADR and explicit implementation Issues. Until then
the reserved package, its zero-export manifest and the absence of event support
remain unchanged. [RFC 0009](0009-streaming-model.md) owns streaming and
[RFC 0005](0005-protocol-neutral-delegation.md) owns delegation; this proposal
does not settle either.

[asyncapi]: https://github.com/asyncapi/spec/blob/b3fac5bb522771428ea57b16129b273cd3ea0180/spec/asyncapi.md
[cloudevents]: https://github.com/cloudevents/spec/blob/fc1f6f31f5f011a72183f1bcea20c987cb683ade/cloudevents/spec.md

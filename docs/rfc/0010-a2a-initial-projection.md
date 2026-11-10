# RFC 0010 — Initial A2A projection boundary

- Status: Open research; first-profile answers proposed in ADR 0098
- Date: 2026-10-28
- Tracking: GitHub Issue #683
- Related: ADR 0010, ADR 0046, ADR 0070, ADR 0086, ADR 0094, ADR 0098, RFC 0005, RFC 0009

## Purpose and current boundary

Determine the smallest useful A2A adapter that preserves Agnara's existing
capability semantics. The published 1.0.3 `agnara-a2a` package reserves a
namespace with no exports. This checkout adds the provisional ADR 0099 surface
through #701, following the #695 fixture. This proposal itself adds no
protocol-support claim. [Maturity](../MATURITY.md) remains authoritative.

The [A2A-01 report](../research/a2a-initial-feasibility.md) records an isolated
SDK checkpoint and fit gaps.
[ADR 0098](../adr/0098-a2a-complete-result-projection.md) proposes the
projection contract for the first profile; it remains under review. An approved RFC
document alone does not authorize the runtime slices below. No model calls,
reasoning engine or task scheduler are implied by an A2A adapter.

## Research checkpoint and source hierarchy

The initial checkpoint was read on 2026-10-28. Its source-inspection status is
not the current installation or dependency decision; ADR 0099 subsequently
selected `a2a-sdk[http-server]==1.3.0`. Keep these identities separate:

| Identity | Inspected source | Meaning here |
| --- | --- | --- |
| Protocol line | A2A `1.0` | Candidate wire contract, not an Agnara support declaration. |
| Specification release | [A2A v1.0.1](https://github.com/a2aproject/A2A/releases/tag/v1.0.1), commit `3303592588e388e62e0f69f701af531d2f4e3991` | Immutable research snapshot. |
| SDK candidate | [a2a-python v1.3.0](https://github.com/a2aproject/a2a-python/releases/tag/v1.3.0), commit `0d9dafb92328144384eca58a6e8ab80cb8f7d445` | Source inspection only; neither installed nor selected as a dependency. |

Use the snapshot's [protocol definitions][proto] and
[specification][spec] together. Rendered tables and SDK objects do not override
normative fields. The specification's section 1.4 refers to `spec/a2a.proto`,
but the inspected tree stores it under `specification/a2a.proto`; the link here
resolves the actual file. Do not copy an example's older version header into
a new binding. A feasibility report must disposition discrepancies between
the chosen specification and SDK before claiming interoperability.

The inspected definitions place protocol version and binding on each
`AgentInterface`; `AgentCard.version` identifies the application agent.
`SendMessageRequest` contains a message, configuration, metadata and optional
tenant routing, without a skill-ID selector. `SendMessageResponse` permits a
message or a task. These facts motivate the options below; they do not settle
Agnara routing or establish that a message-only server meets every required
operation. See [the exact definitions][proto] and specification sections 3–5.

The candidate SDK's [package metadata][sdk-project] includes HTTP, model and
protobuf dependencies and optional server/binding extras. A Python requirement
or classifier is not evidence that Agnara's Python 3.14 environment resolves,
installs or interoperates with it. ADR 0010 requires a separately reviewed
exact SDK pin and dependency audit before adoption.

## Options

| Option | Benefit | Unresolved cost |
| --- | --- | --- |
| Card projection only | Exercises field publication and immutable metadata without invocation. | A card describing an unserved endpoint is misleading; an internal projection fixture is not a deployable A2A server. |
| One capability per surface, complete-result messages | Uses the existing invocation boundary and makes dispatch explicit without guessing from natural language. | Must prove the permitted message-only subset and the behavior of all required operations. |
| Task-first agent surface | Can eventually represent long-running work, retrieval and cancellation. | Needs task ownership, storage, authorization, expiry, restart and replay decisions that the kernel does not provide. |

Investigate the second option first, with a card projection as part of the
same feasibility fixture. If its mandatory-operation gate fails, report the
blocking requirement and return to design; do not relabel missing behavior as
an optional feature. Task-first implementation remains a separate RFC/ADR.

## Candidate complete-result profile

Every statement in this section is a proposed constraint to test, not a
description of a shipped API.

### Composition and dispatch

One named A2A surface selects exactly one complete-result capability from a
frozen registry and its matching compiled plan. A future adapter contributes
neutral exposure records through ADR 0070; it does not add an A2A runtime to
core or depend on the HTTP/MCP sibling packages. A surface is a deployment
projection, not another bounded-context app class.

Publish one deliberately described skill for that surface. Skill names,
descriptions and examples are explicit public metadata, not copied handler
docstrings or instructions that execute. Multiple-skill dispatch needs its
own contract: a skill ID is descriptive metadata in this protocol, not the
equivalent of MCP's tool-name selector. Do not select capabilities from text,
caller metadata, tenant values or a claimed execution identity.

### Input and successful output

The first candidate accepts one structured message part containing an object
of capability inputs. Reject unsupported text/file mixtures, multiple parts,
recognized state or routing fields outside the profile and unsupported
output-mode requests before handler effects. Unrecognized fields are ignored
as specification section 5.7 recommends; fixed dispatch means they cannot
select work (ADR 0098 D2). Validate size, depth and JSON-compatible values at the adapter
boundary; the compiled input contract remains authoritative. A transport
field may not replace a DI parameter or trusted context.

An immediate successful result becomes one agent message with one structured
part containing an object envelope, provisionally `{"result": value}`.
The envelope permits scalar, collection and null results without pretending
the underlying output is always an object. The value must have passed the
existing compiled output contract and the reviewed serialization boundary.
No return-annotation inference or second application output declaration is
introduced. The envelope, field-presence rules and null behavior need an ADR
and round-trip client tests before they become a compatibility promise.

No task is invented around a synchronous result. The first profile does not
accept task continuation or maintain conversation history. Requests implying
existing task/context state must be explicitly refused according to the
reviewed binding contract, rather than silently running a fresh invocation.
Message identifiers and metadata remain untrusted correlation, never Agnara
execution identities, idempotency keys or resumption authority.

### Authentication, policy and failures

The host authenticates the caller and supplies a verified principal through
an explicit adapter bridge. Its credentials, raw request and SDK objects do
not reach domain handlers. The existing execution boundary evaluates policy,
confirmation and validation before dependencies and handler effects.

Capability discovery and security-scheme declarations grant no authority.
The first profile creates no confirmation evidence from message acceptance,
card metadata or client claims. A canonical interaction-required outcome is
not a suspended A2A task; refusal/mapping needs a documented safe outcome.
There is no delegated authority or transport idempotency projection.

The feasibility report must map every canonical failure category and host
authentication failure to an exact binding outcome. Distinguish malformed
protocol input from application denial/failure; never return a successful
agent message containing an unmarked error. Unexpected exceptions, output
violations and schema diagnostics must not expose values, paths or internal
policy details. Cancellation propagates to owned work; a timeout is distinct
from a durable task cancellation operation.

### Card publication and lifecycle

Filter selected capabilities and fields before constructing or serializing
a card, following ADR 0046. Explicitly configured public metadata must cover
the required card/skill fields; missing consent fails composition rather
than falling back to private definition text. Publish only the interface,
protocol revision and modes actually served. Streaming, push notifications,
extended cards and extensions remain unadvertised until implemented and
tested. Signing and authenticated card variants need separate decisions.

The proposed first hosted card is explicitly public and independent of
caller credentials. Any later per-principal card needs request-isolated
filtering and a private cache contract before implementation. Public-card
cache validators must describe the complete public bytes, not only the
application version. Card caching never bypasses invocation authorization.
The host supplies the advertised deployment URL; request headers must not
silently choose it. No private URL or credential is inferred from runtime DI.

An application host owns the chosen SDK/server tier, a container and their
event loop. Requests drain or cancel before clients/server resources and
containers close; teardown order must be demonstrated for the selected tier.
Use structured ownership, propagate cancellation and avoid process-global
registries or retained background tasks. No cross-loop reuse, durable task
store or free-threading support follows from immutable discovery metadata.

## Feasibility gates and proposed work sequence

These work packages require their own Issues and review. A2A-01 has the
isolated checkpoint linked above; later slices remain separate work. No
runtime package or workflow change is authorized by this RFC.

| Slice | Required evidence before closure |
| --- | --- |
| A2A-01: specification/SDK feasibility | Exact protocol/spec/SDK identities; installed Python 3.14 resolution and import/call evidence in an isolated experiment; inventory of the selected SDK tier's defaults, dependencies and lifecycle. Classify every required operation as implemented, expressly optional or blocking with normative references. |
| A2A-02: projection decision | ADR answers routing, structured envelope, principal bridge, complete failure table, card consent, size/time limits, identifiers and unsupported operations. Public API proposal is reviewed against the manifest; no example import exists before implementation. |
| A2A-03: internal adapter fixture | Official pinned client round trips across the chosen binding; no handler/reflection/policy reimplementation. Keep SDK types and dependencies inside the adapter/experiment. Card projection alone cannot close this slice. |
| A2A-04: governed usable surface | Separate approval for exports, exact adapter dependencies, installed-wheel consumers, runnable examples and exposure/introspection integration. Update maturity only for behavior proven by CI. |

A2A-01 must examine `SendMessage` and all required task retrieval/list/cancel
behavior, including what happens when no tasks exist. Check the remaining
streaming, push and extended-card operations individually against the pinned
specification. A false feature flag is not a blanket excuse to omit an
operation whose requirements say otherwise. Choose one binding and prove it;
do not list JSON-RPC, HTTP+JSON and gRPC as supported merely because the SDK
contains implementations. No implementation pin is chosen by this RFC.

## Threat and acceptance matrix

| Boundary | Required future test evidence |
| --- | --- |
| Skill versus dispatch | Another skill ID, capability ID or tenant claim cannot redirect an invocation. Recognized continuation/routing fields fail without effects; unrecognized fields are ignored and cannot select work. |
| Publication and authority | Hidden capabilities, fields and deployment details never reach serialized cards. A visible skill still refuses an unauthorized caller before DI/handler effects. |
| Credential and identity isolation | Two concurrent callers cannot share principal, confirmation, metadata or correlation state. Message/context/task IDs cannot select execution identity or cross-owner state. |
| Shape and resource limits | Malformed, mixed, excessive and unsupported parts/modes fail before application effects; valid scalar/object/list/null outputs round-trip through the chosen envelope. |
| Failure and redaction | Every canonical category has an asserted protocol mapping; invalid outputs and unexpected exceptions disclose no secret values, paths or diagnostics. |
| Lifecycle | Success, failure, deadline, caller cancellation and disconnect prove bounded ownership, joined tasks and same-loop cleanup. No task record or replay promise is fabricated. |
| Protocol truthfulness | Card interfaces/flags match served behavior; unsupported revision/operation and no-task cases follow the reviewed required-operation matrix. |
| Packaging and boundaries | Core imports no SDK; sibling adapters are not dependencies. The exact SDK pin, public exports and installed-wheel tests match the accepted contract. |

## Questions requiring a decision

1. Can the selected revision and SDK tier satisfy mandatory operations while
   returning only immediate messages, and with what exact no-task responses?
2. Is one capability per surface a useful first deployment model, or is an
   application-owned dispatcher necessary before an adapter is worthwhile?
3. Which binding and minimal SDK extras meet lifecycle/authentication needs
   without introducing another hidden HTTP composition model?
4. What exact envelope, failure table and unsupported-interaction outcome are
   safe and interoperable? What body, part, depth and time bounds are chosen?
5. Is public-card-only discovery sufficient initially? Which decisions would
   separately authorize filtered cards, signatures, tasks or additional modes?

[ADR 0098](../adr/0098-a2a-complete-result-projection.md) proposes answers for
the first profile; #695 exercises it and #701 adds the provisional public
surface under [ADR 0099](../adr/0099-a2a-provisional-public-surface.md).
The [current guide](../A2A_SERVICE.md) links A2A-04b's runnable example,
installed candidate-wheel consumers and bounded Uvicorn/h11 loopback evidence.
It also documents the opt-in application-owned disconnect recipe under proposed
ADR 0100. These fixtures do not settle broader host/protocol support or promote
the provisional exports to stable; those remain separate maintainer decisions.
[RFC 0005](0005-protocol-neutral-delegation.md) owns delegation and
[RFC 0009](0009-streaming-model.md) owns the protocol-neutral streaming
questions; this proposal does not settle either by adopting SDK defaults.

[spec]: https://github.com/a2aproject/A2A/blob/3303592588e388e62e0f69f701af531d2f4e3991/docs/specification.md
[proto]: https://github.com/a2aproject/A2A/blob/3303592588e388e62e0f69f701af531d2f4e3991/specification/a2a.proto
[sdk-project]: https://github.com/a2aproject/a2a-python/blob/0d9dafb92328144384eca58a6e8ab80cb8f7d445/pyproject.toml

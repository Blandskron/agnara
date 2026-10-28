# ADR 0098 — A2A complete-result projection

- Status: Proposed
- Date: 2026-10-28
- Tracking: GitHub Issue #687 (A2A-02)
- Answers: RFC 0010 questions 1–5 for the first profile
- Related: ADR 0010, ADR 0024, ADR 0043, ADR 0046, ADR 0070, ADR 0086,
  ADR 0094, RFC 0005, RFC 0009, [A2A-01 report](../research/a2a-initial-feasibility.md)

## Context

[RFC 0010](../rfc/0010-a2a-initial-projection.md) proposed one capability per
A2A surface, answered with immediate messages and no tasks. The
[A2A-01 report](../research/a2a-initial-feasibility.md) showed that
`a2a-sdk[http-server]==1.3.0` can serve that exchange, and that numeric
fidelity, discarded unknown fields and permissive minor-version handling block
using the SDK defaults unchanged.

This record settles the contract that A2A-03 must implement and test. It adds
no dependency, export, endpoint or support claim, and `agnara-a2a` stays
`PLANNED` with zero exports. Section references are to the pinned A2A v1.0.1
[specification][spec] and [protocol definitions][proto]. Each mapping below is
marked as **required** by that snapshot, **recommended** (a SHOULD) or a
**profile** choice that this ADR makes and a later record may relax.

## Decision

### D1 — Scope, revision and binding

The first profile serves one binding, JSON-RPC 2.0 over HTTP, at protocol
revision `1.0` exactly. It answers `SendMessage` with one immediate `Message`
and never creates a `Task`. Streaming, push notifications, extended cards,
extensions, signed cards, HTTP+JSON and gRPC remain unserved and unadvertised.

An admission gate owned by the adapter runs before the SDK dispatcher. It
compares the `A2A-Version` header with the reviewed set `{"1.0"}` by exact
`Major.Minor` and returns `VersionNotSupportedError` (`-32009`) otherwise.
An empty header means revision `0.3` (section 3.6.2, required) and is refused
the same way. This replaces the SDK validator, which A2A-01 observed accepting
`1.99` on a `1.0` interface. Adding a revision needs a reviewed record and its
own tests.

### D2 — Dispatch is fixed by composition

A surface is composed with exactly one complete-result capability and its
compiled plan, recorded as an ADR 0070 exposure. No request field selects
work. Skill IDs, `tenant`, metadata, extensions, message text and claimed
identities are never dispatch inputs. A deployment that needs several
capabilities composes several surfaces at distinct URLs. A multi-skill
dispatcher needs its own decision.

Unknown request fields are ignored, as section 5.7 recommends for forward
compatibility. This resolves a conflict with RFC 0010, which proposed
rejecting "extra routing selectors". Because dispatch is fixed, an
unrecognized field cannot change which capability runs. The A2A-01
observation that the SDK discards a synthetic `capabilityId` is therefore
the intended outcome, not a gap. The admission gate does not re-parse raw
JSON to look for extra keys. RFC 0010 is updated accordingly.

**Recognized** fields that imply behavior outside the profile are refused
before invocation; see D6. Rejecting them is not a dispatch decision; it stops
the server from silently running a fresh invocation for a request that
expected state.

### D3 — Input envelope and numeric domain

The request message must have `role: ROLE_USER` and exactly one `Part`
carrying `data` whose value is a JSON object of capability inputs. That object
is the only input source. Part `metadata`, `filename` and `media_type` (when
present it must be `application/json`) select nothing.

The SDK parses `data` as protobuf `Value`, which has one double-precision
number type. With the inspected protobuf 7.36.2 runtime, every JSON number
reaches Python as `float`: `5` arrives as `5.0`, and `9007199254740993`
arrives as `9007199254740992.0`. Without normalization, any capability with an
`int` parameter would reject every well-formed call. The adapter applies one
documented conversion before the compiled input contract runs:

- a finite float with an integral value and magnitude at most
  `2**53 - 1` becomes `int`;
- any other finite float stays `float`;
- an integral value of magnitude `2**53` or more is refused as
  `invalid_input`, because it may already have been rounded; this also
  refuses legitimate values such as `1e20`;
- booleans, strings, `null`, objects and arrays pass unchanged.

The compiled input contract remains authoritative: the adapter never invents
defaults, coerces strings or fills dependency parameters. The standard
schema's existing rule that accepts a JSON integer for a declared `float`
then applies unchanged. Exact
values outside this domain must be modelled as strings by the application;
the adapter never stringifies a number. A fractional `5.5` passed to an `int`
parameter still fails validation in the kernel.

The A2A-01 report recorded the rounding. The integral-float observation was
reproduced with the same isolated environment on 2026-10-28 by parsing
`{"a": 5, "c": 9007199254740993}` with `google.protobuf.json_format`. A2A-03
must turn both into regression tests through the official client.

### D4 — Successful output envelope

A successful outcome becomes one agent `Message` (`role: ROLE_AGENT`) with a
fresh server-generated `messageId` and one `data` part whose value is
`{"result": value}`, with `mediaType` `application/json`. The value has
already passed the plan's output contract (ADR 0086). The envelope keeps the
ADR 0043 rules: explicit JSON built-ins only, tuples become arrays, no cycles,
depth at most 64, and `null` stays distinct from an absent part.

Integers outside `±(2**53 - 1)` and non-finite floats cannot be carried
faithfully by `Value` and become a redacted `internal_failure` instead of a
rounded success. Clients see integral numbers serialized as JSON numbers that
protobuf may render with a fractional part (`5.0`); this is a property of the
binding, not a change to the capability contract. The response sets no
`contextId` and no `taskId`. Whether an official client accepts a message
without `contextId` is an A2A-03 test obligation; if it does not, a fresh
opaque value per response is the fallback, never an echo of client input.

### D5 — Authentication, principal and policy

The host authenticates the caller in front of the adapter, as with HTTP
composition. A missing or invalid credential is refused there with HTTP `401`
and a challenge for the declared scheme (section 3.3.2, required), before the
SDK parses a body. The adapter takes a required, explicit principal resolver
over the authenticated request scope and has no anonymous default. A
deployment that wants an anonymous surface must say so.

SDK `ServerCallContext.state`, raw headers and credentials never reach the
capability context. A2A-01 observed the default context builder copying
headers, including `Authorization`, into SDK state; the adapter's handler
reads only the resolved principal. Card `securitySchemes` and
`securityRequirements` are public metadata configured at composition and grant
no authority. The kernel evaluates policy, confirmation and input validation
before dependency acquisition and handler effects (ADR 0024, AGENTS.md
security discipline).

The first profile has no confirmation evidence channel. Composition refuses a
capability declared with `Confirmation.REQUIRED`. With `Confirmation.POLICY`, a
resulting `INTERACTION_REQUIRED` outcome is refused as in D6; it never becomes
an `INPUT_REQUIRED` or `AUTH_REQUIRED` task.

### D6 — Failure table

Failures are JSON-RPC error objects, never a successful `Message` wrapping an
error. Error `data` carries one `google.rpc.ErrorInfo` object (section 9.5,
recommended) with `reason` and `domain: "agnara"`; it never carries canonical
`Failure.details`, validation paths, values, exception text or policy
internals. Code `-32000` lies in JSON-RPC's implementation-defined server range
but outside the `-32001` to `-32099` block that A2A reserves (section 9.5),
so it cannot collide with a future A2A error.

**Protocol input, decided before invocation:**

| Condition | Outcome | Basis |
| --- | --- | --- |
| Body exceeds the byte limit (D7) | HTTP `413`, no JSON-RPC body | Profile |
| Invalid JSON / invalid request object | `-32700` / `-32600` from the SDK | JSON-RPC 2.0 |
| Unknown method | `-32601` | JSON-RPC 2.0 |
| `A2A-Version` empty or not in `{"1.0"}` | `-32009` | Section 3.6.2, required |
| `message.taskId` present | `-32001` `TaskNotFoundError` | Section 3.4.2, required: no tasks exist |
| `message.contextId` present | `-32004` `UnsupportedOperationError` | Section 3.4.1, required: reject, do not generate |
| `referenceTaskIds` or message `extensions` non-empty | `-32004` | Profile |
| `configuration.taskPushNotificationConfig` present | `-32003` | Section 3.3.4, required |
| `acceptedOutputModes` non-empty and excludes `application/json` | `-32005` `ContentTypeNotSupportedError` | Section 3.3.2 |
| A text, raw or URL part, or a non-JSON `mediaType` | `-32005` | Section 3.1.1 |
| Zero or several parts, a non-object `data`, `role` not user, non-empty `tenant`, or JSON depth over the limit | `-32602` Invalid params | Section 3.3.2 validation |
| Number outside the D3 domain | `-32602` with reason `INVALID_INPUT` | Profile |

`historyLength` and `returnImmediately` have no effect on a direct `Message`
(section 3.2.2) and are ignored. Request and message `metadata` are untrusted
and are not forwarded.

**Canonical capability outcomes** (`agnara.execution.result.FailureCode`):

| `FailureCode` | JSON-RPC code | `ErrorInfo.reason` | Message |
| --- | --- | --- | --- |
| `invalid_input` | `-32602` | `INVALID_INPUT` | Canonical caller-safe message |
| `unauthenticated` | `-32000` | `UNAUTHENTICATED` | Canonical message |
| `forbidden` | `-32000` | `FORBIDDEN` | Canonical message |
| `not_found` | `-32000` | `NOT_FOUND` | Canonical message |
| `conflict` | `-32000` | `CONFLICT` | Canonical message |
| `rate_limited` | `-32000` | `RATE_LIMITED` | Canonical message |
| `interaction_required` | `-32000` | `INTERACTION_REQUIRED` | Fixed text; no interaction request is serialized |
| `unavailable` | `-32000` | `UNAVAILABLE` | Canonical message |
| `timeout` | `-32000` | `TIMEOUT` | Canonical message |
| `internal_failure` | `-32603` | `INTERNAL_FAILURE` | Fixed text "Internal error" |

`unauthenticated` here is a policy outcome after the host accepted a
credential; host authentication failures are HTTP `401` (D5). Unexpected
handler exceptions, output-contract violations and unrepresentable results
reach this table only through the kernel's redacting result path, as
`internal_failure`. `not_found` describes an application resource and is
unrelated to `TaskNotFoundError`. A2A-03 asserts every row through the
official client.

**Other operations**, as observed for the stateless fixture in A2A-01:

| Operation | Outcome | Basis |
| --- | --- | --- |
| `GetTask`, `CancelTask` | `-32001` for any ID | Sections 3.1.3, 3.1.5, 3.3.2: does not exist or is not accessible |
| `ListTasks` | Empty list, empty `nextPageToken`, after host authentication | Section 3.1.4 |
| `SendStreamingMessage`, `SubscribeToTask` | `-32004` | Section 3.3.4, required |
| Push-configuration methods (4) | `-32003` | Section 3.3.4, required |
| `GetExtendedAgentCard` | `-32004` | Section 3.3.4, required with the flag false |

### D7 — Limits and deadlines

The admission gate reads at most a configured number of body bytes before
the SDK parses, with a default of 1 MiB. JSON nesting deeper than 64 levels in
`data` is refused as `-32602`; the byte bound also bounds parser recursion.
Each invocation runs under a required, configured deadline with a default of
30 seconds; expiry yields `timeout` through the existing cooperative deadline
model ([deadlines](../DEADLINES.md)). Deployments may lower these
values. Raising them is allowed but documented as their own risk. These defaults
are starting points to be measured in A2A-03, not benchmarked guarantees.

### D8 — Agent Card publication

The card is public, unsigned and identical for every caller. Composition
requires explicit public metadata: card `name`, `description` and `version`,
plus the skill's `id`, `name`, `description` and at least one tag (section 4.4,
required fields). Missing metadata fails composition. Nothing falls back to
docstrings, capability IDs or definition text, and hidden fields are filtered
before construction (ADR 0046).

The card publishes exactly one `AgentInterface` with binding `JSONRPC`,
`protocolVersion` `"1.0"` and the URL supplied by the host; request headers
never choose that URL. All capability flags are `false`. Input and output
modes are `["application/json"]`. The ETag covers the full serialized public
bytes, and the host chooses the `Cache-Control` policy; A2A-01 observed the SDK
emitting none. Per-caller cards, signatures and the extended card need
separate decisions.

### D9 — Identifiers

The response `messageId` is a random UUID generated per response. Client
`messageId`, `metadata` and any tenant value are untrusted correlation data.
They are never an Agnara execution identity, idempotency key, principal or
resumption token, and they are not echoed into the response. The kernel's
execution ID is not exposed on the wire. Transport idempotency
(section 3.3.1, optional) is not offered.

### D10 — Handler tier and lifecycle

The adapter implements the SDK's lower-level `RequestHandler` interface rather
than `DefaultRequestHandler`. For this profile, the default V2 handler's
active-task, queue and store machinery would be configured and then never
used, and its input-mode validation is off by default. The adapter's handler
implements exactly D3–D6, and A2A-03 re-tests every check the default handler
would otherwise have provided.

The handler owns no background work and no task state. Each `SendMessage`
awaits its invocation inside the request task, so caller disconnect and
cancellation propagate to the owned work (RFC 0010 lifecycle). The host creates
the SDK routes, admission gate, handler and container on one event loop inside
its ASGI lifespan. On shutdown it stops accepting requests, lets in-flight
invocations finish or cancels them at the deadline, closes SDK resources and
then the container. No process-global registry is used.

### D11 — Dependencies and public API shape

The adapter, not the kernel, will depend on `a2a-sdk` with the smallest extra
set that provides the JSON-RPC routes, which is `http-server` at the inspected
checkpoint. The SDK brings protobuf and Pydantic into the adapter only. The
exact pin, joint resolution with the workspace lock, advisories and wheel
contents are decided in A2A-03 under ADR 0010, not by this record.

The future public surface should mirror the existing adapters rather than add
a new composition style: an exposure declared at the composition root
(compare `Mcp(app, surface=...)`), a builder that takes compiled exposures,
plans, a container, card metadata, a principal resolver and limits (compare
`build_mcp_server` and the HTTP `principals=` resolver), and adapter-specific
definition errors. Names, signatures and exports are decided in A2A-04 against
[public-api.json](../public-api.json). No example imports or documentation of
unshipped syntax are added before then.

## Consequences

- A2A-03 can build an internal fixture whose acceptance criteria are the tables
  above, run through the official pinned client.
- Applications cannot pass exact integers beyond `2**53 - 1` through this
  surface without modelling them as strings; this is documented, not hidden.
- Clients that rely on a `TaskState` lifecycle (`INPUT_REQUIRED`,
  `AUTH_REQUIRED`, `WORKING`) will not get one. Long-running work and
  confirmation flows stay out of scope until a task-first record.
- Capability failures use code `-32000` plus `ErrorInfo.reason`, which generic
  A2A clients may show only as a server error. That is the honest
  representation; no category is disguised as an A2A-specific error.
- Several surfaces require several URLs and cards.

## Alternatives

- **Reject unknown fields with a raw-envelope gate:** rejected. It contradicts
  section 5.7 and adds a second parser, while fixed dispatch already removes
  the redirection risk.
- **Return failures as a `Message` with a failure envelope:** rejected. Clients
  would read a protocol success, which RFC 0010 forbids for unmarked errors and
  which makes errors depend on parsing a payload convention.
- **Return a terminal `Task` (`FAILED`, `REJECTED`) for failures:** rejected. It
  creates a task that `GetTask` would then have to find, breaking the no-task
  profile.
- **Map categories onto A2A-specific codes** (for example `forbidden` to
  `-32001`): rejected as semantically false.
- **Use `DefaultRequestHandler` with an in-memory store:** rejected for this
  profile. It is viable, but it carries unused task lifecycle and still needs
  the D3/D6 checks.
- **Carry large numbers as strings automatically:** rejected. It silently
  changes the capability's published types.

## Remaining evidence

A2A-03 must still show compiled Agnara invocation through the official client,
policy before effects, cleanup, redaction, concurrent principal isolation,
every D6 row, disconnect handling and cross-platform CI. A2A-04 decides
exports, the exact dependency pin, examples and maturity. Until then there is
no A2A support.

[spec]: https://github.com/a2aproject/A2A/blob/3303592588e388e62e0f69f701af531d2f4e3991/docs/specification.md
[proto]: https://github.com/a2aproject/A2A/blob/3303592588e388e62e0f69f701af531d2f4e3991/specification/a2a.proto

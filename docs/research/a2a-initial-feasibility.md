# A2A-01 — Initial SDK feasibility

- Date: 2026-10-28
- Tracking: GitHub Issue #685
- Input: [RFC 0010](../rfc/0010-a2a-initial-projection.md)
- Status: Isolated research evidence; no adapter or support declaration

## Result

The immediate-message path is technically usable in the inspected SDK on
conventional CPython 3.14.4/Windows 11. Both the stateless fixture handler and
the SDK's default handler returned an immediate message through its official
JSON-RPC client and ASGI routes. The default handler retained zero tasks after
that exchange, and its absent-task operations returned the expected errors.
This answers the basic feasibility question without requiring Agnara to adopt
a durable task runtime.

The SDK is **not a configuration-only fit** for the proposed Agnara profile.
Three observed differences require explicit decisions before implementation:
large JSON integers lose precision through protobuf `Value`; unknown routing
fields disappear before the handler; and the version validator accepts an
unadvertised minor such as `1.99` on an interface declaring `1.0`. Host
authentication, sanitized context, limits and lifecycle wiring are also
explicit host responsibilities. Proceed to a separate A2A-02 decision; do not
add exports or dependencies to `agnara-a2a` from this result.

## Reproducible evidence and exact scope

The [experiment README](../../experiments/a2a/README.md) gives executable
commands; [probe.py](../../experiments/a2a/probe.py) contains the asserted
observations and [observed-windows.json](../../experiments/a2a/observed-windows.json)
retains the result, complete resolved versions and source/lock hashes.
[requirements.lock](../../experiments/a2a/requirements.lock) pins all 30
distributions with hashes independently of the workspace lock.

| Identity | Observed checkpoint |
| --- | --- |
| Interpreter/platform | CPython 3.14.4; Windows 11 `10.0.26300`; GIL enabled. |
| Specification | A2A v1.0.1, commit `3303592588e388e62e0f69f701af531d2f4e3991`; candidate wire line `1.0`. |
| SDK | `a2a-sdk[http-server]==1.3.0`; source checkpoint `0d9dafb92328144384eca58a6e8ab80cb8f7d445`. |
| Selected binding | JSON-RPC, through `JsonRpcTransport` and `create_jsonrpc_routes`. |
| Server dependencies | Isolated resolution includes Starlette 1.10.0, SSE-Starlette 3.6.0, HTTPX 0.28.1, protobuf 7.36.2 and Pydantic 2.14.1. Full inventory is in the evidence JSON. |
| Request boundary | In-process HTTPX ASGI transport; explicit Starlette lifespan, synthetic public fixture and no network socket. |

Installation succeeded using `uv pip compile ... --python-version 3.14
--generate-hashes`, a separate `uv venv`, and `uv pip sync`; the hash-required
sync command in the README was also checked. No SDK installation or version
change was made to the workspace environment. The experiment imports no Agnara
package. It proves the SDK path in isolation, not a combined Agnara adapter,
joint dependency resolution or installed first-party wheel interoperability.

The four installed SDK files hashed in the evidence were compared byte for
byte with the pinned upstream files linked below. No moving `main` source is
used to explain an installed behavior. The probe's dynamic imports preserve
this isolation without weakening workspace type/lint gates.

## Operation matrix

The normative references are specification sections 3.1 and 3.3.4 at
[the pinned snapshot][spec]. The table distinguishes the candidate's narrow
coverage from complete protocol conformance. All listed rejection codes were
observed over ASGI against **both** handlers with well-formed required fields;
SDK exception construction and wire serialization were exercised, not mocked.

| Operation | Obligation for the candidate | Observed result |
| --- | --- | --- |
| `SendMessage` | Baseline operation; section 3.1.1 permits an immediate message instead of a task. | Official client round-trips scalar, nested object, list and null result envelopes. Default handler also returns a message. |
| `GetTask` | Baseline operation, not disabled by a streaming flag; absent/inaccessible task follows section 3.1.3. | `TaskNotFoundError`, JSON-RPC `-32001`; also asserted through the official client for the default handler. |
| `ListTasks` | Baseline operation, including authorization, request validation and pagination semantics in section 3.1.4. | Empty list with empty `nextPageToken`; default handler has zero tasks before/after the message. Nonempty paging, filters and ownership are untested. |
| `CancelTask` | Baseline operation; absent task follows section 3.1.5. | `TaskNotFoundError`, `-32001`; not an implementation of durable cancellation. |
| `SendStreamingMessage` | Optional streaming; false flag requires refusal under section 3.3.4. | `UnsupportedOperationError`, `-32004`. |
| `SubscribeToTask` | Same streaming gate. | `UnsupportedOperationError`, `-32004`. |
| `CreateTaskPushNotificationConfig` | Optional push support; false flag requires refusal. | `PushNotificationNotSupportedError`, `-32003`; no webhook contacted. |
| `GetTaskPushNotificationConfig` | Same push gate. | `-32003`. |
| `ListTaskPushNotificationConfigs` | Same push gate. | `-32003`. |
| `DeleteTaskPushNotificationConfig` | Same push gate. | `-32003`. |
| `GetExtendedAgentCard` | False extended-card flag requires `UnsupportedOperationError`; supported-but-unconfigured is a different case. | False flag returns `-32004`. The distinct configured-capability/missing-card case is outside the chosen profile. |

An unknown method returns `-32601`. No operation was silently dropped because
the candidate creates no tasks. The stateless fixture explicitly implements
these no-task/feature decisions; it is not credited with the SDK default
handler's request validators or task-store semantics. The default handler's
same operation matrix is retained separately in the evidence. These tests do
not establish every normative success, invalid-input, paging or concurrency
requirement, and therefore do not certify a server.

## Fit gaps that block turnkey adoption

### Numeric fidelity

Sending the JSON integer `9007199254740993` through the SDK parser produced
`9007199254740992.0`. The structured part uses protobuf `Value`, whose numeric
branch cannot preserve arbitrary Python integers. This is not an Agnara schema
validation result: rounding occurs before any Agnara invocation exists.

A2A-02 must decide a declared safe numeric profile with rejection before
conversion, or application-authored string fields where exact large values
are required. Do not silently stringify business values, weaken the core
integer contract, or claim that retaining raw inbound JSON alone fixes the
official client's outbound protobuf conversion. Scalars/lists/null fitting
the inspected data representation round-tripped, without implying that every
valid kernel result has a lossless A2A representation.

### Raw-envelope validation and dispatch

The [JSON-RPC dispatcher][dispatcher] parses parameters with unknown-field
discard enabled. A synthetic `capabilityId` selector was ignored and the echo
handler still ran; no alternate capability was selected. This fails RFC 0010's
proposed reject-before-effects rule even though it does not demonstrate
redirected invocation. A handler receiving only the parsed protobuf cannot
recover discarded fields.

Decide where a bounded raw-envelope gate belongs before SDK parsing, what it
rejects and how a single canonical payload reaches the runtime. The SDK
dispatcher reads JSON from the host request; this experiment adds no body or
depth limit. Inspecting that source is not evidence of a safe production limit.
Do not smuggle a raw SDK request into domain handlers to recover lost data.

### Protocol revision boundary

An empty header and `9.0` were rejected with `-32009`. A request declaring
`1.99` was accepted despite the card advertising `1.0`. The inspected
[validator][version-validator] compares major versions. Specification section
3.6.2 requires semantics of the requested major/minor and refusal of an
unsupported revision. An Agnara binding must define/enforce its reviewed
revision set before dispatch; accepting a request is not evidence of support
for an unimplemented future minor. This is a concrete compatibility gate for
the candidate, not a declaration that all SDK versioning behavior is invalid.

## Defaults and ownership to carry into A2A-02

| Boundary | Source/observation | Required disposition |
| --- | --- | --- |
| Authentication | With no host auth middleware, the fixture receives an unauthenticated SDK user. [The default context builder][context] copies headers into SDK state, including a synthetic Authorization header. | Install a trusted authentication boundary and explicit principal bridge. Never forward arbitrary SDK state/headers into an Agnara context. This public fixture is not an authentication bypass finding. |
| Handler tier | The public `DefaultRequestHandler` alias selects V2. [Its source][default-handler] manages active-task state even for an immediate-message exchange. | Decide whether to use V2 with explicit ownership or a lower `RequestHandler` implementation. The latter needs its own validators/failure contract; it is not automatically simpler. |
| Task lifetime | Default handler returned a message with zero retained tasks; its `aclose` drains active work. | Wire `aclose` into host lifespan. No durable storage, restart, cross-owner or replay guarantee follows from this probe. |
| Input modes | Default handler's `validate_input_modes` option defaults false. | Enable or replace it deliberately alongside the stricter one-structured-part profile. No natural-language routing or model reasoning is introduced. |
| Card publication | Explicit public fixture card; [SDK routes][card-routes] produced an ETag and a conditional `304`, without a default Cache-Control header. | Apply Agnara publication/field consent before construction; select deployment cache policy and advertised URL explicitly. The first profile is unsigned/public only. |
| Resource ordering | Shared official transport client closes before handler and lifespan; caller cancellation reaches the stateless handler; no tasks remain after either tier exits. | Preserve same-loop ownership and test real server disconnect/graceful shutdown separately. ASGI transport does not start lifespan automatically; this experiment enters it explicitly. |
| Dependencies | SDK server extras are isolated; none of their 30 resolved versions were adopted by the workspace. | Recheck minimal extras, advisories and joint resolution on the exact future adapter pin. Installability alone is not adoption approval. |

## Disposition and remaining evidence

A2A-01 has produced an installable, executable checkpoint and identified the
decisions blocking direct adoption. The message-only/no-task option remains
worth considering; the data, envelope and version differences prevent calling
the SDK defaults an equivalent projection of current Agnara contracts.

The next separately scoped A2A-02 ADR should resolve those three gaps, exact
failure/interaction mapping, authenticated principal construction, allowed
parts/modes, request limits and chosen handler lifecycle. It may narrow or
reject this candidate. No public import or decorator should be invented as
part of that decision. [ADR 0098](../adr/0098-a2a-complete-result-projection.md)
proposes those dispositions. It treats discarded unknown fields as consistent
with specification section 5.7 once dispatch is fixed by composition.

Future A2A-03/04 evidence still needs actual compiled Agnara invocation,
policy-before-effects and cleanup tests, output-error redaction, concurrent
authority isolation, invalid required fields/modes, network client/server
disconnect behavior, full required-operation coverage, installed artifacts and
cross-platform CI. No Linux/macOS, free-threading, other binding, authenticated
card, streaming, push, delegation or production-readiness claim is made here.
The public package remains reserved with zero exports.

[spec]: https://github.com/a2aproject/A2A/blob/3303592588e388e62e0f69f701af531d2f4e3991/docs/specification.md
[dispatcher]: https://github.com/a2aproject/a2a-python/blob/0d9dafb92328144384eca58a6e8ab80cb8f7d445/src/a2a/server/routes/jsonrpc_dispatcher.py
[context]: https://github.com/a2aproject/a2a-python/blob/0d9dafb92328144384eca58a6e8ab80cb8f7d445/src/a2a/server/routes/common.py
[version-validator]: https://github.com/a2aproject/a2a-python/blob/0d9dafb92328144384eca58a6e8ab80cb8f7d445/src/a2a/utils/version_validator.py
[default-handler]: https://github.com/a2aproject/a2a-python/blob/0d9dafb92328144384eca58a6e8ab80cb8f7d445/src/a2a/server/request_handlers/default_request_handler_v2.py
[card-routes]: https://github.com/a2aproject/a2a-python/blob/0d9dafb92328144384eca58a6e8ab80cb8f7d445/src/a2a/server/routes/agent_card_routes.py

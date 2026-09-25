# RFC 0008 — Framework embedding and ecosystem composition

- Status: Partially resolved by ADR 0094
- Tracking: GitHub Issue #282
- Related: ADR 0093, ADR 0094, RFC 0005

## Current contract

ADR 0094 defines the framework-neutral, async, complete-result embedding
boundary. A host owns routing, lifecycle, authentication, sessions,
transactions, responses and telemetry. It maps a verified caller to an
Agnara `Principal`, supplies value-only inputs and invokes a frozen
`CapabilityRuntime` explicitly. Agnara retains capability policy,
confirmation, schema validation, execution identity and result semantics.
The host does not pass a raw request, ORM session, credential or span into
capability metadata or handlers. See `docs/INTEROPERABILITY.md` and
`docs/MATURITY.md` for the validated fixtures and support limits.

Standalone, Agnara-hosted, embedded and side-by-side applications share this
boundary. Version-pinned Starlette, FastAPI, Django and Litestar fixtures,
plus a SQLAlchemy + SQLite host fixture, validate selected compositions.
They do not make an automatic framework plugin or broad compatibility promise.

## Open questions

1. How would streaming cross a host boundary without transferring lifecycle
   or cancellation ownership ambiguously?
2. What explicit delegation contract would permit a host or parent capability
   to narrow authority without confused-deputy behavior? RFC 0005 owns the
   protocol-neutral delegation design.
3. Should cross-application composition exist, and if so how would registry,
   policy, DI and failure ownership be made explicit? ADR 0093 currently
   refuses it.
4. Which host-specific integrations warrant a supported adapter rather than a
   conformance fixture? Each requires its own versioned evidence and review.
5. Whether a synchronous host entry point can preserve the same cancellation
   and lifecycle contract requires a separate design.

No open question changes the current 1.x public API or support claim. Any
answer must keep framework SDKs out of core and preserve independent policy
checks for every capability invocation.

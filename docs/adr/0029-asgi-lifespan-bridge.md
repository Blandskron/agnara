# ADR 0029 — ASGI Lifespan Bridge

- Status: Proposed
- Date: 2026-09-03
- Tracking: GitHub Issue #127

## Context

ADR 0005 puts compilation at startup, and E3.6 gives dependency providers
async cleanup. Neither can run under a server, because the ASGI boundary from
E6.1 recognized only `http` scopes and refused `lifespan`.

The lifespan protocol is small but easy to get wrong in ways that only show up
in production: swallowing a startup failure so a server boots with a broken
application, converting task cancellation into a reported failure, or leaving a
half-entered resource behind when the protocol is violated.

There is a second, architectural trap. Starlette-style lifespan hands
application state back to the framework, which then attaches it to the HTTP
application object. Copying that would make the HTTP adapter the owner of
state that MCP, A2A, events and direct invocation need equally.

## Decision

An application lifecycle is one async context manager factory. Startup enters
it, shutdown exits it, and the dispatcher owns nothing else.

```text
lifespan.startup  → enter   → lifespan.startup.complete
                            → lifespan.startup.failed  (message = traceback)
lifespan.shutdown → exit    → lifespan.shutdown.complete
                            → lifespan.shutdown.failed (message = traceback)
```

One dispatcher runs one cycle. A second cycle, an unexpected event, a non-dict
event and a non-string event `type` are all refused explicitly rather than
tolerated, because an ASGI server that violates the protocol is a bug worth
surfacing, not a condition worth guessing through.

`asyncio.CancelledError` propagates. A cancelled startup is the server
shutting down, not an application that failed to start, and reporting it as
`startup.failed` would put a false cause in the operator's log.

The `message` field carries the full traceback. Unlike an RFC 9457 problem
(ADR 0028), it is delivered to the server that is hosting the application, not
to a client, so redacting it would only hide the cause from the one party
entitled to it.

**The lifecycle cannot return a value.** A context manager that yields
anything other than `None` is refused. Application state belongs to dependency
providers, which every transport shares.

A `lifespan` scope with no configured dispatcher is still refused with
`_UnsupportedScopeError`. Raising is the ASGI-sanctioned way for an
application to say it has no lifespan, and a server running `lifespan="auto"`
handles that itself. Silently completing the protocol would claim a lifecycle
that does not exist.

## Consequences

- A server cannot boot an application whose startup failed.
- Cancellation during boot or drain stays cancellation.
- A protocol violation cannot leave a resource entered: the lifecycle is
  released before the error propagates.
- The dispatcher is single-use, so a server that re-runs lifespan against the
  same instance fails loudly instead of double-entering resources.
- Startup compilation is not implemented here. There is no composition root
  yet; the lifecycle callable is where a later one will compile the registry
  and the dependency graph.
- Applications cannot use lifespan as a state channel. That is deliberate and
  will feel restrictive to anyone arriving from Starlette or FastAPI.
- WebSocket scopes, hot reload, signal handling and readiness endpoints remain
  unimplemented rather than approximated.

## Guardrails

- No lifecycle type enters `agnara-core` in this decision.
- The lifespan `message` field is never reused for a client-facing response.
- The lifecycle return value is never used to carry application state.
- Exactly one `startup.complete` or `startup.failed`, and at most one
  `shutdown.complete` or `shutdown.failed`, per cycle.

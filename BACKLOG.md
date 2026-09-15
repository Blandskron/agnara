# Backlog

This file owns decomposed work ready to implement on the path to `1.0.0`.
`ROADMAP.md` owns the destination and `docs/INITIATIVES.md` owns dependency
order.

## Ready after design acceptance

- [x] Implement the accepted protocol-neutral streaming *kernel* contract
  (I2, ADR 0084): declaration, owned one-shot consumption, pull backpressure,
  cancellation, cleanup and post-output failure.
  - [x] Stabilize its shared unary/stream output contract (ADR 0086): explicit
    per-unit declaration, startup compilation and redacted validation failure.
- [x] Implement the accepted HTTP SSE streaming projection (I2, ADR 0085)
  for `1.0.0`, with the ASGI conformance suite the execution-semantics gate
  needs: explicit `Http.sse` exposures, delayed response start, an explicit
  terminal event, owned disconnect handling and redaction.
  - [x] Decide the HTTP SSE projection (ADR 0085).
- [ ] Revisit WebSockets, MCP progress, A2A task events and the event adapter
  after `1.0.0`. Each needs its own ADR answering RFC 0009 Q9 and conformance
  tests; none is a supported or required 1.0 projection (V1-02 scope lock).
- [~] Implement execution identity and operational idempotency (I3).
  - [x] Implement the ADR 0087 runtime execution identity in `ExecutionContext`,
    canonical outcomes, stream diagnostics and lifecycle telemetry (#388).
  - [x] Project generated execution identity through the current HTTP/MCP
    boundaries and tracing bridge without accepting a transport-selected identity (#390).
  - [x] Define and implement the explicit idempotency store, including its
    capability/principal/fingerprint scope, atomic in-flight races, TTL and
    failure-retention evidence (#392). It must not imply replay or automatic
    retry.
  - [x] Make the ADR 0091 direct complete-result boundary operational: claim
    after policy/input preflight and before dependencies or handler work;
    reuse only completed successes; fail closed on storage errors (#400).
  - [x] Audit race, exact TTL, failure/cancellation, bounded capacity,
    sensitive-data and independent-store conformance behavior (#404).
- [ ] Establish performance budgets and CI regression gates (I14).
- [x] Integrate supported HTTP OpenAPI documentation, built-in browser UIs and
  authorized Explorer composition for the 1.0 gate (ADR 0090, #394).
- [x] Implement the accepted same-compiled-application nested capability
  invocation boundary (I8, ADR 0093), with policy/confirmation re-evaluation,
  child context and DI isolation, deadline/cancellation propagation,
  recursion/depth enforcement, idempotency isolation and deterministic abuse
  evidence (#412). Stream, delegated and cross-app composition require their own
  accepted follow-up decisions.
- [x] Verify and harden direct-actor composition propagation (I8, I10): a
  child has a detached actor context, bounded correlation only, no inherited
  delegation evidence, and deterministic two-level deadline/cancellation and
  concurrent telemetry-tree evidence (#414). RFC 0005 delegation remains
  unimplemented.
- [x] Add direct-runtime composition conformance (I2, I3, I8): streaming
  children and streaming parents are refused before producer start, parent
  idempotency cannot select a child namespace, and indirect cycles/depth
  exhaustion stop before the next effect (#416). Stream composition remains a
  separate deferred decision.
- [x] Complete the framework interoperability contract (I20, ADR 0094):
  explicit async complete-result embedding boundary, singular lifecycle/resource
  ownership, value-only principal/context bridge, one-event-loop reuse rules
  and framework-neutral architecture evidence. Concrete framework fixtures
  remain release-gate work; this does not claim integration support.
  - [x] Exercise the first version-pinned external-host fixture (V1-23):
    Starlette 1.6.0 embeds direct complete-result invocation beside native
    routes in one lifespan, with clean-room wheel installation, fail-closed
    principal mapping, composition, idempotency reuse, canonical failure and
    stream refusal, plus disconnect cancellation evidence. It remains an
    experimental fixture rather than framework support or release closure.
  - [x] Exercise FastAPI progressive adoption (V1-24): FastAPI 0.141.1 keeps
    its native routes, dependency-based verified actor mapping, exception
    handling and middleware while directly invoking the same compiled Agnara
    snapshot. A separately mounted public `HttpApplication` surface proves
    complete and SSE projection with explicitly coordinated child lifespan and
    separate OpenAPI ownership. This remains a clean-room experimental fixture,
    not FastAPI integration support, merged documentation or release closure.
- [ ] Complete the security program evidence (I10).

## Deferred decisions

- [ ] D7 Decide whether `agnara.core.di` remains the public dependency
  injection spelling before API stabilization.
- [ ] D6 Rename the introspection snapshot field `.apps` to `applications`
  only with an intentional snapshot-format migration.
- [ ] Configure an independent reviewer identity when one is available.

No item in this backlog authorizes a publication before the `1.0.0` release
gates are satisfied.

# Backlog

This file owns decomposed work ready to implement on the path to `1.0.0`.
`ROADMAP.md` owns the destination and `docs/INITIATIVES.md` owns dependency
order.

## Ready after design acceptance

- [x] Implement the accepted protocol-neutral streaming *kernel* contract
  (I2, ADR 0084): declaration, owned one-shot consumption, pull backpressure,
  cancellation, cleanup and post-output failure.
- [ ] Implement the accepted HTTP SSE streaming projection (I2) for `1.0.0`.
  It needs its ASGI conformance suite before the execution-semantics gate can
  close.
  - [x] Decide the HTTP SSE projection (ADR 0085); implementation remains
    separate work.
- [ ] Revisit WebSockets, MCP progress, A2A task events and the event adapter
  after `1.0.0`. Each needs its own ADR answering RFC 0009 Q9 and conformance
  tests; none is a supported or required 1.0 projection (V1-02 scope lock).
- [ ] Implement execution identity and operational idempotency (I3).
- [ ] Establish performance budgets and CI regression gates (I14).
- [ ] Complete interoperability and composition contracts (I20, I8).
- [ ] Complete the security program evidence (I10).

## Deferred decisions

- [ ] D7 Decide whether `agnara.core.di` remains the public dependency
  injection spelling before API stabilization.
- [ ] D6 Rename the introspection snapshot field `.apps` to `applications`
  only with an intentional snapshot-format migration.
- [ ] Configure an independent reviewer identity when one is available.

No item in this backlog authorizes a publication before the `1.0.0` release
gates are satisfied.

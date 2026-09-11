# Backlog

This file owns decomposed work ready to implement on the path to `1.0.0`.
`ROADMAP.md` owns the destination and `docs/INITIATIVES.md` owns dependency
order.

## Ready after design acceptance

- [x] Implement the accepted protocol-neutral streaming *kernel* contract
  (I2, ADR 0084): declaration, owned one-shot consumption, pull backpressure,
  cancellation, cleanup and post-output failure.
- [ ] Project the streaming contract onto each transport (I2): HTTP SSE and
  WebSockets, MCP progress, A2A task events and the event adapter. Each needs
  its own ADR answering RFC 0009 Q9 and its own conformance tests.
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

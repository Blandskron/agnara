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
  - [x] Exercise Django request/ORM boundary conformance (V1-25): Django
    6.1.1 async views retain host request, authentication and ORM/transaction
    ownership while passing only a verified actor to the ADR 0094 bridge.
    The fixture covers canonical failure, composition, idempotency and cleanup;
    sync/WSGI reuse of a live runtime is explicitly not covered. This is
    required evidence, not a Django plugin or integration-support claim.
  - [x] Exercise the selected second host-diversity fixture (V1-26): Litestar
    2.24.0 proves the public host boundary without adding Flask or a core
    special case. Its host-owned result/status mapping, fail-closed principal,
    composition, idempotency and cleanup remain fixture evidence only.
  - [x] Interoperability reliability/security audit and supported-matrix closure (Task 30, I20, I10):
    verified lifecycle/context isolation under adversarial conditions across all host classes
    (Starlette 1.6.0, FastAPI 0.141.1, Django 6.1.1, Litestar 2.24.0), executed the shared conformance
    harness across all host classes in `tests/conformance/test_host_harness.py`, proved framework
    absence and minimal install in an isolated subprocess (`tests/integration/test_framework_absence.py`),
    removed stale references, and updated the I20 supported matrix in `docs/INTEROPERABILITY.md`.
- [ ] Complete the security program evidence (I10).
  - [x] Close the current threat-model and security-boundary evidence (V1-34):
    replace the historical A8 framing with the `1.0.0` candidate model across
    execution identity, direct/HTTP/MCP/embedded invocation, composition,
    idempotency, streaming, schema/persistence and telemetry; record the
    2026-09-20 GitHub alert readback and residual host/application boundaries.
    This is not I10 or release closure: final-candidate audit and maintainer
    review remain mandatory.
- [x] Add schema-boundary conformance (V1-27): Pydantic and msgspec remain
  optional development fixtures. Their supported evidence is JSON-normalized
  nested dataclass-shaped data materialized and validated by the standard
  adapter; no whole-library compatibility or shipped adapter is claimed.
- [x] Add persistence-boundary conformance (V1-28): SQLAlchemy 2.0.54 is an
  optional SQLite-only development fixture in `tests/integration/persistence/`.
  An application-owned invocation provider supplies the store while the host
  retains `Session`, commit and rollback ownership; success, validation,
  policy, handler failure, cancellation, nested invocation and parallel-session
  isolation are covered. PostgreSQL was **NOT RUN** because it remains
  supported-if-evidence, not a required 1.0.0 gate.
- [x] Add shared-host OpenTelemetry conformance (V1-29): the optional
  OpenTelemetry SDK 1.44.0 fixture uses FastAPI 0.141.1 to prove one
  application-owned host trace and one capability span tree. It covers remote
  propagation, nested/parallel isolation, streaming success/late-failure/
  cancellation closure and redaction of payloads, credentials, claims and
  idempotent results. A fresh-interpreter check additionally compiles, invokes
  and streams with `opentelemetry` unimportable, so the bridge is optional in
  behaviour and not only in declared dependencies.

- [x] Rehearse the 1.0.0 release end to end (V1-33): resolved the main/develop
  divergence by cherry-picking the one exclusive commit (a full merge would have
  reverted develop's idempotency runtime), built and installed all seven
  distributions outside the workspace, audited documentation coverage for the
  eleven clean-room features and closed the two gaps, and audited branch
  protection. Three findings: a superseded action pin, two actions not pinned to
  a SHA, and a merge that silently reverted a release gate's evidence. All fixed
  with gates. The governance gap -- rulesets require the CI check but zero
  approving reviews, so the documented review step is unenforced -- is recorded
  for the maintainer rather than changed, because requiring one approval would
  block a solo maintainer from merging. Report in
  `docs/releases/1.0-release-rehearsal.md`. FINAL RELEASE READY: NO.

- [x] Freeze the 1.0 public surface and remove documentation drift (V1-32):
  established the measurement and compatibility policy later finalized by
  V1-31. The canonical surface is now 166 stable exports across 13 modules;
  historical alias paths are absent from the contract.

- [x] Calibrate performance budgets and enforce them (V1-30): the eleven critical
  paths were audited; `benchmarks/runtime_paths.py` now covers the seven that had
  no benchmark. `docs/performance/budgets.json` holds 13 limits expressed as
  ratios between scenarios measured in the same run, calibrated over three runs.
  `scripts/check_performance_budgets.py` enforces them in CI and was demonstrated
  to fail on a real regression. The audit found and fixed a quadratic sweep in
  `InMemoryIdempotencyStore`: one claim plus complete went from 473us at 4,000
  records to a flat 9us. HTTP SSE throughput and free-threaded builds remain
  unbudgeted and are recorded as open.

- [x] Finalize the 1.0 public API (V1-31): classify 166 canonical names across
  13 governed modules as stable, remove 171 duplicate leaf-module export paths,
  move DI to `agnara.di`, and rename introspection snapshot `apps` to
  `applications` with migration guidance and public-import evidence.

## Deferred decisions

- [x] D7 Use `agnara.di` as the public dependency-injection spelling.
- [x] D6 Rename the introspection snapshot field `.apps` to `applications`.
- [ ] Configure an independent reviewer identity when one is available.

No item in this backlog authorizes a publication before the `1.0.0` release
gates are satisfied.

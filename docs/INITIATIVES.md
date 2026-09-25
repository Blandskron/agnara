# Initiatives

This index separates shipped contracts from work that still needs decisions.
[MATURITY.md](MATURITY.md) owns current status; [BACKLOG.md](../BACKLOG.md)
owns open tasks. An initiative is not evidence that a feature is supported.

### I2 Streaming

**Horizon:** current kernel and HTTP contract.
**Status:** `IMPLEMENTED`.

Typed pull-based kernel streams and HTTP SSE are implemented (ADRs 0084–0086).
MCP progress, WebSockets and reserved-adapter projections need separate
contracts and evidence.

### I3 Execution identity and idempotency

**Horizon:** current direct-invocation contract.
**Status:** `IMPLEMENTED`.

Opaque runtime execution identity and explicit direct complete-result
idempotency are implemented (ADRs 0087–0089, 0091). The reference store is
process-local. HTTP and MCP accept no idempotency selector. Durable storage
and adapter projections need separate work.

### I8 Capability composition

**Horizon:** current same-snapshot complete-result contract.
**Status:** `IMPLEMENTED`.

ADR 0093's same-compiled-application complete-result boundary is implemented.
Each nested child re-evaluates policy and confirmation with a fresh context,
identity and DI lifecycle. Delegation, streaming children and cross-application
composition remain outside this contract.

### I9 Public API governance

**Horizon:** current 1.x compatibility contract.
**Status:** `IMPLEMENTED`.

`docs/public-api.json` classifies the canonical exports, and the generated
reference, import audit and installed-artifact checks enforce the inventory.

### I10 Security program

**Horizon:** ongoing maintenance.
**Status:** `IN PROGRESS`.

The current [threat model](THREAT_MODEL.md), authority tests, bounded property
lanes, CodeQL and supply-chain controls cover defined boundaries. Each release
still needs current CI, dependency/index evidence and maintainer judgment.
Host identity, durable stores, exporters and application policy remain external.

### I14 Performance program

**Horizon:** ongoing maintenance.
**Status:** `IMPLEMENTED`.

Fifteen calibrated budgets in `docs/performance/budgets.json` are enforced in
CI with a synthetic failure proof. Benchmarks are regression evidence, not a
claim of superiority over another framework.

### I20 Framework interoperability

**Horizon:** current embedding contract; further ecosystem research.
**Status:** `IMPLEMENTED` for the narrow contract.

ADR 0094's explicit async bridge is exercised by version-pinned Starlette,
FastAPI, Django and Litestar fixtures. SQLite/SQLAlchemy and OpenTelemetry
fixtures validate host-owned infrastructure and telemetry seams. These
fixtures do not create framework-specific support packages or automatic
lifecycle integration. See [INTEROPERABILITY.md](INTEROPERABILITY.md).

### I21 Documentation baseline

**Horizon:** current release preparation.
**Status:** `IN PROGRESS`.

Issue [#512](https://github.com/Blandskron/agnara/issues/512) aligns the
documentation and package metadata for 1.0.3 without runtime or API changes.

### I22 Python 3.15 research

**Horizon:** future research.
**Status:** `PLANNED RESEARCH`.

The declared floor remains Python 3.14. The
[research plan](research/python-315-readiness.md) describes evidence required
before any 3.15 support claim. No implementation is included in 1.0.3.

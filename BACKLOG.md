# Backlog

Legend:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked
- `[?]` Research

The agent must update this file as work progresses and must never mark a task complete without the associated acceptance criteria passing.

## EPIC 0 ???????? Repository foundation

- [x] E0.1 Create `uv` workspace.
- [x] E0.2 Create package boundaries described in `ARCHITECTURE.md`.
- [x] E0.3 Set `requires-python = ">=3.14"`.
- [x] E0.4 Configure Ruff lint + format.
- [x] E0.5 Configure `ty` type checking.
- [x] E0.6 Configure pytest.
- [x] E0.7 Add architecture import tests.
- [x] E0.8 Add GitHub Actions for Linux, macOS and Windows where practical.
- [x] E0.9 Add conventional changelog/release process. Tracking: GitHub Issue
  #16.
- [x] E0.10 Add license after owner decision. Apache License 2.0 was adopted
  by PR #81.
- [x] E0.13 Verify Ruff and `ty` gates. Both are green in CI as of PR #1.
  They still cannot run on the current Windows workstation: an Application
  Control policy refuses their native binaries (`OSError 4551`) from both
  the virtual environment and the interpreter `Scripts` directory. The
  policy must not be weakened. CI is therefore the authoritative record for
  these two gates ???????? see `QUALITY_GATES.md`.
- [x] E0.14 Restore GitHub autonomy. `gh` 2.98.0 is installed and
  authenticated, so Issues, Pull Requests, reviews and merges are available
  again. Work merged before PR #1 carries local `--no-ff` merges with
  documented self-review instead of Pull Requests; that history is not
  retroactively backed by PR review.

### Acceptance

```text
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

all pass on Python 3.14.

Current evidence: all five gates pass in CI on CPython 3.14, across
ubuntu-latest, macos-latest and windows-latest, with 105 tests. See the
checks on PR #1. Locally only `uv sync` and `pytest` can run (E0.13).

## EPIC 1 ???????? Capability model

- [x] E1.1 Define immutable `CapabilityDefinition`.
- [x] E1.2 Define stable capability identity.
- [x] E1.3 Implement `@app.capability`.
- [x] E1.4 Implement deterministic registry.
- [x] E1.5 Detect duplicate IDs.
- [x] E1.6 Freeze registry after compilation.
- [x] E1.7 Expose read-only introspection API.
- [x] E1.8 Add metadata: effects, risk, confirmation, idempotency.

### Acceptance

At least 25 focused unit tests covering registration, metadata, duplicate handling and immutability.

## EPIC 2 ???????? Schema port

- [x] E2.1 Define schema adapter protocol.
- [x] E2.2 Implement standard-Python baseline adapter. Tracking: GitHub Issue
  #30.
- [x] E2.3 Support dataclasses. Tracking: GitHub Issue #32.
- [x] E2.4 Define JSON Schema export interface.
- [x] E2.5 Prototype msgspec adapter separately. Tracking: GitHub Issue #34.
- [x] E2.6 Prototype Pydantic adapter separately. Tracking: GitHub Issue #38.
- [?] E2.7 Benchmark adapters before selecting defaults.

### Acceptance

Core imports neither Pydantic nor msgspec.

## EPIC 3 ???????? Dependency graph

- [x] E3.1 Write DI RFC.
- [x] E3.2 Define provider abstraction.
- [x] E3.3 Define scopes.
- [x] E3.4 Compile dependency DAG.
- [x] E3.5 Detect dependency cycles at compile time.
- [x] E3.6 Support async resource cleanup. Delivered by PR #53.
- [x] E3.7 Implement invocation-scoped cache. Delivered by PR #53.
- [x] E3.8 Verify free-threading safety assumptions. Delivered by PR #56.

## EPIC 4 ???????? Execution compiler/runtime

- [x] E4.1 Define Invocation. Delivered by PR #58.
- [x] E4.2 Define ExecutionContext. Delivered by PR #58.
- [x] E4.3 Compile capability to ExecutionPlan.
- [x] E4.4 Direct invocation.
- [x] E4.5 Cancellation propagation.
- [x] E4.6 Deadlines/timeouts.
- [x] E4.7 Canonical result/failure model.
- [x] E4.8 Structured telemetry hooks.
- [~] E4.9 Benchmark runtime overhead. Tracking: GitHub Issue #105.

## EPIC 5 ???????? Policy engine

- [x] E5.1 Define Principal.
- [x] E5.2 Define policy interface.
- [x] E5.3 Scope policy. Tracking: GitHub Issue #90.
- [x] E5.4 Effects/risk metadata. Delivered with E1.8 by GitHub Issue #2 and
  PR #4; metadata remains data rather than authorization (ADR 0008).
- [x] E5.5 Confirmation requirement. Tracking: GitHub Issue #96.
- [x] E5.6 Define the protocol-neutral delegation model, including explicit
  actor/subject separation, monotonic authority attenuation, bounded verified
  chains and confirmation binding. Tracking: GitHub Issue #101.
- [x] E5.7 Keep policy tests independent of transports with an executable
  architecture guard. Tracking: GitHub Issue #103.

## EPIC 6 ???????? HTTP adapter

- [ ] E6.1 ASGI boundary.
- [ ] E6.2 Route registry.
- [ ] E6.3 Path/query/header/body binding.
- [ ] E6.4 Response serialization.
- [ ] E6.5 RFC 9457 failures.
- [ ] E6.6 Lifespan.
- [ ] E6.7 Generate deterministic OpenAPI 3.2 from compiled HTTP exposures,
  shared schemas and explicitly publishable metadata. Do not accept a
  handwritten parallel schema as the generated source of truth.
- [ ] E6.8 HTTP conformance tests.
- [?] E6.9 Compare direct ASGI vs minimal Starlette dependency.
- [ ] E6.10 Benchmark against FastAPI, Starlette and Litestar.
- [ ] E6.11 Add pinned OpenAPI 3.2 structural/conformance fixtures, including
  stable `operationId`, schema references, security schemes and documented
  unsupported features.
- [ ] E6.12 Define the replaceable documentation-provider contract without a
  required browser UI dependency.
- [ ] E6.13 Add configurable schema, documentation and Explorer routes with
  deterministic collision detection. Candidate defaults remain provisional.
- [ ] E6.14 Allow OpenAPI, each human UI, Explorer and interactive try-it to be
  disabled independently.
- [ ] E6.15 Implement a Swagger UI provider with pinned self-hosted assets,
  optional explicit CDN mode and versioned compatibility evidence.
- [ ] E6.16 Implement a ReDoc provider with the same provider contract and
  versioned compatibility evidence.
- [?] E6.17 Spike Scalar and re-evaluate actively maintained alternatives
  against identical OpenAPI 3.2, CSP, accessibility, mobile, dependency and
  bundle-size fixtures before selecting any default.
- [ ] E6.18 Add documentation UI browser tests for CSP, XSS payloads, disabled
  routes, OAuth redirect handling, authentication state and try-it controls.
- [ ] E6.19 Enforce the documentation asset policy: pinned local assets by
  default; exact-version CDN, origin allowlist and integrity/CSP documentation
  only through explicit opt-in.

### HTTP documentation acceptance

- core imports and declares no OpenAPI or UI implementation;
- one compiled application produces deterministic OpenAPI through HTTP and CLI
  export;
- UI packages are removable without changing capability runtime behavior;
- an installation with no UI provider can still generate OpenAPI;
- hidden/private operations and sensitive schema material are absent before
  serialization;
- no external network asset is required by the production baseline;
- supported OpenAPI/UI versions and known gaps are recorded by conformance
  tests rather than implied by marketing claims.

## EPIC 7 ???????? MCP adapter

- [ ] E7.1 Pin supported MCP spec version.
- [ ] E7.2 Tool projection from capabilities.
- [ ] E7.3 Schema mapping.
- [ ] E7.4 Discovery.
- [ ] E7.5 Authorization integration.
- [ ] E7.6 Canonical interaction-required mapping to MCP.
- [ ] E7.7 Task/MRTR research.
- [ ] E7.8 Official SDK conformance tests.
- [ ] E7.9 Benchmark tool invocation overhead against FastMCP where meaningful.

## EPIC 8 ???????? Documentation and introspection

- [x] E8.0 Define the interactive documentation and Agnara Explorer
  architecture. Tracked by Issue #9.
- [ ] E8.1 Define an immutable, versioned protocol-neutral introspection
  snapshot for projects, apps, capabilities, exposures, dependencies,
  policies, effects, risk, idempotency, confirmation and schemas.
- [ ] E8.2 Define and enforce discovery visibility, redaction and authorization
  controls before serialization; private capabilities, secrets, dependency
  instances and policy internals must not leak.
- [ ] E8.3 Implement `agnara inspect [app]` as a human-readable presentation of
  the filtered introspection snapshot.
- [ ] E8.4 Implement deterministic, versioned `agnara inspect [app] --json`
  output from the same snapshot rather than HTML or OpenAPI.
- [ ] E8.5 Implement `agnara graph` as a human-readable relationship view over
  the same snapshot without a second discovery path.
- [ ] E8.6 Add an authorized machine-readable discovery endpoint with the same
  versioned serialization as CLI JSON and explicit cache behavior.
- [ ] E8.7 Implement `agnara schema openapi` over the same OpenAPI projection
  served by `agnara-http`, with stdout/file output and stable exit behavior.
- [ ] E8.8 Implement a read-only Agnara Explorer MVP over protocol-neutral
  introspection, including non-HTTP transport availability.
- [ ] E8.9 Add Explorer project/app/capability, schema, dependency and policy
  views without exposing runtime object values or non-publishable metadata.
- [ ] E8.10 Add Explorer authorization, partial-visibility, cache-control and
  disabled-surface tests.
- [ ] E8.11 Add accessibility, keyboard, screen-reader, deep-link and responsive
  mobile tests for Agnara Explorer.
- [?] E8.12 Research generated `llms.txt` without treating it as an
  authorization or canonical discovery format.
- [ ] E8.13 Generate agent context from the versioned filtered snapshot.
- [ ] E8.14 Validate architecture metadata and cross-surface snapshot
  consistency.

### Introspection dependency order

Each line above is intended to become one Issue, branch and reviewable PR.
E8.1 precedes E8.3 through E8.6 and E8.8 through E8.9. E8.2 precedes any
remotely served machine-readable discovery or Explorer release. E8.7 depends
on E6.7 and E6.11. Explorer views follow the read-only E8.8 shell rather than
expanding that first PR into a complete frontend.

## EPIC 9 ???????? Telemetry

- [ ] E9.1 Telemetry port in core.
- [ ] E9.2 OpenTelemetry adapter.
- [ ] E9.3 Common capability spans.
- [ ] E9.4 transport span linking.
- [ ] E9.5 MCP/GenAI semantic convention compatibility.
- [ ] E9.6 no-op telemetry cost benchmark.

## EPIC 10 ???????? v0.1 release gate

- [ ] Capability definition stable enough for alpha.
- [ ] Direct invocation stable.
- [ ] HTTP usable.
- [ ] OpenAPI generated.
- [ ] MCP usable.
- [ ] Core has no forbidden dependencies.
- [ ] Cross-platform CI green.
- [ ] Baseline benchmarks published.
- [ ] Security threat model present.
- [ ] API docs present.
- [ ] Migration policy for alpha documented.

## Post-v0.1

- [ ] A2A adapter.
- [ ] Tasks.
- [ ] AsyncAPI/event abstractions.
- [ ] WebSocket/SSE enhancements.
- [ ] plugin marketplace/registry research.
- [ ] native/Rust acceleration only if benchmarks justify it.

## EPIC 0A ???????? Project/app scaffolding

- [ ] E0A.1 Implement `agnara project create`.
- [ ] E0A.2 Define and validate `agnara.toml`.
- [ ] E0A.3 Implement `agnara app create`.
- [ ] E0A.4 Implement default `modular-hexagonal` template.
- [ ] E0A.5 Implement `minimal` template.
- [ ] E0A.6 Implement `--with` exposure selection.
- [ ] E0A.7 Implement profiles: core/api/mcp/agentic/worker/full.
- [ ] E0A.8 Implement optional CLI aliases without duplicate code paths.
- [ ] E0A.9 Implement `--dry-run`.
- [ ] E0A.10 Implement non-destructive conflict detection.
- [ ] E0A.11 Implement `--json` output for generator plans/results.
- [ ] E0A.12 Add golden-file tests for generated projects/apps.
- [ ] E0A.13 Add Windows/Linux/macOS path tests.
- [ ] E0A.14 Add architecture tests for generated app dependency direction.

### Acceptance

Generated code must:

- import successfully on Python 3.14;
- pass Ruff/ty/pytest;
- contain no transport dependency in domain/application layers;
- be deterministic for identical inputs;
- refuse overwrite without explicit authorization.

## EPIC 1A ???????? Modular app runtime

- [ ] E1A.1 Define app/module descriptor.
- [ ] E1A.2 Register app-owned capabilities.
- [ ] E1A.3 Detect duplicate app identities.
- [ ] E1A.4 Expose app metadata through introspection.
- [ ] E1A.5 Define cross-app public contract rules.
- [ ] E1A.6 Freeze app registry during project compilation.

## EPIC 0B ???????? Agentic repository governance

- [x] E0B.1 Establish GitHub Issue labels for type/area/priority.
- [x] E0B.2 Configure branch rulesets for `main`.
- [x] E0B.3 Configure branch rulesets for `develop`.
- [x] E0B.4 Require relevant CI checks before merge.
- [x] E0B.5 Configure allowed merge strategies.
- [x] E0B.6 Validate GitHub CLI autonomous workflow.
- [x] E0B.7 Validate Issue ???????? branch ???????? PR ???????? merge ???????? close flow.
- [x] E0B.8 Decide single-agent or dual-agent review mode for repository
  governance. Mode B (single-agent) is in force: PR required, CI required,
  zero required approvals, documented self-review, no fabricated approval.
  Migrate to Mode A when E0B.9 delivers a second identity.
- [ ] E0B.9 Configure independent reviewer identity when available.
- [x] E0B.10 Configure auto-merge policy where safe. Auto-merge is enabled
  at the repository level; it can only complete once the required `CI` check
  passes and conversations are resolved.
- [x] E0B.11 Replace placeholder OWNER/REPO in security Issue template.
- [ ] E0B.12 Document release and hotfix automation evidence.
- [x] E0B.13 Establish permanent AI-agent attribution policy across commits,
  Pull Requests, reviews and squash merges without inventing identities or
  rewriting history. Tracking: GitHub Issue #12.

### Acceptance

- normal work cannot bypass the documented PR flow;
- agent can create and close an Issue through a merged PR;
- required checks are enforced;
- force-pushes to protected branches are blocked;
- no workflow requires an impossible self-approval;
- the complete lifecycle is visible and understandable to a human maintainer.

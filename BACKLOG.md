# Backlog

Legend:

- `[ ]` Not started
- `[~]` In progress
- `[x]` Done
- `[!]` Blocked
- `[?]` Research

The agent must update this file as work progresses and must never mark a task complete without the associated acceptance criteria passing.

## EPIC 0 — Repository foundation

- [x] E0.1 Create `uv` workspace.
- [x] E0.2 Create package boundaries described in `ARCHITECTURE.md`.
- [x] E0.3 Set `requires-python = ">=3.14"`.
- [~] E0.4 Configure Ruff lint + format. Configured; not yet verified — see E0.13.
- [~] E0.5 Configure `ty` type checking. Configured; not yet verified — see E0.13.
- [x] E0.6 Configure pytest.
- [ ] E0.7 Add architecture import tests.
- [ ] E0.8 Add GitHub Actions for Linux, macOS and Windows where practical.
- [ ] E0.9 Add conventional changelog/release process.
- [ ] E0.10 Add license only after owner decision.
- [!] E0.13 Verify Ruff and `ty` gates. Blocked on the current Windows
  workstation: a Windows Application Control policy refuses to execute the
  `ruff` and `ty` native binaries (`OSError 4551`), from both the project
  virtual environment and the interpreter `Scripts` directory. The policy
  must not be weakened to work around this. Both gates therefore run in CI
  (E0.8) before they can be marked complete.
- [!] E0.14 Restore GitHub autonomy. The GitHub CLI (`gh`) is not installed
  on this workstation, so Issues, Pull Requests, reviews and merges cannot
  be created. Until it is installed and authenticated, the repository
  operates in local-only mode and EPIC 0B cannot proceed.

### Acceptance

```text
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

all pass on Python 3.14.

Current evidence: `uv sync` and `pytest` pass locally on CPython 3.14.4
(39 tests). `ruff` and `ty` are configured but blocked locally by E0.13 and
must be proven green in CI before EPIC 0 can be marked complete.

## EPIC 1 — Capability model

- [ ] E1.1 Define immutable `CapabilityDefinition`.
- [ ] E1.2 Define stable capability identity.
- [ ] E1.3 Implement `@app.capability`.
- [ ] E1.4 Implement deterministic registry.
- [ ] E1.5 Detect duplicate IDs.
- [ ] E1.6 Freeze registry after compilation.
- [ ] E1.7 Expose read-only introspection API.
- [ ] E1.8 Add metadata: effects, risk, confirmation, idempotency.

### Acceptance

At least 25 focused unit tests covering registration, metadata, duplicate handling and immutability.

## EPIC 2 — Schema port

- [ ] E2.1 Define schema adapter protocol.
- [ ] E2.2 Implement standard-Python baseline adapter.
- [ ] E2.3 Support dataclasses.
- [ ] E2.4 Define JSON Schema export interface.
- [ ] E2.5 Prototype msgspec adapter separately.
- [ ] E2.6 Prototype Pydantic adapter separately.
- [?] E2.7 Benchmark adapters before selecting defaults.

### Acceptance

Core imports neither Pydantic nor msgspec.

## EPIC 3 — Dependency graph

- [ ] E3.1 Write DI RFC.
- [ ] E3.2 Define provider abstraction.
- [ ] E3.3 Define scopes.
- [ ] E3.4 Compile dependency DAG.
- [ ] E3.5 Detect dependency cycles at compile time.
- [ ] E3.6 Support async resource cleanup.
- [ ] E3.7 Implement invocation-scoped cache.
- [ ] E3.8 Verify free-threading safety assumptions.

## EPIC 4 — Execution compiler/runtime

- [ ] E4.1 Define Invocation.
- [ ] E4.2 Define ExecutionContext.
- [ ] E4.3 Compile capability to ExecutionPlan.
- [ ] E4.4 Direct invocation.
- [ ] E4.5 Cancellation propagation.
- [ ] E4.6 Deadlines/timeouts.
- [ ] E4.7 Canonical result/failure model.
- [ ] E4.8 Structured telemetry hooks.
- [ ] E4.9 Benchmark runtime overhead.

## EPIC 5 — Policy engine

- [ ] E5.1 Define Principal.
- [ ] E5.2 Define policy interface.
- [ ] E5.3 Scope policy.
- [ ] E5.4 Effects/risk metadata.
- [ ] E5.5 Confirmation requirement.
- [ ] E5.6 Delegation RFC.
- [ ] E5.7 Policy tests independent of transports.

## EPIC 6 — HTTP adapter

- [ ] E6.1 ASGI boundary.
- [ ] E6.2 Route registry.
- [ ] E6.3 Path/query/header/body binding.
- [ ] E6.4 Response serialization.
- [ ] E6.5 RFC 9457 failures.
- [ ] E6.6 Lifespan.
- [ ] E6.7 OpenAPI 3.2 generation target.
- [ ] E6.8 HTTP conformance tests.
- [?] E6.9 Compare direct ASGI vs minimal Starlette dependency.
- [ ] E6.10 Benchmark against FastAPI, Starlette and Litestar.

## EPIC 7 — MCP adapter

- [ ] E7.1 Pin supported MCP spec version.
- [ ] E7.2 Tool projection from capabilities.
- [ ] E7.3 Schema mapping.
- [ ] E7.4 Discovery.
- [ ] E7.5 Authorization integration.
- [ ] E7.6 Canonical interaction-required mapping to MCP.
- [ ] E7.7 Task/MRTR research.
- [ ] E7.8 Official SDK conformance tests.
- [ ] E7.9 Benchmark tool invocation overhead against FastMCP where meaningful.

## EPIC 8 — Documentation and introspection

- [ ] E8.1 `agnara inspect`.
- [ ] E8.2 capability graph JSON.
- [ ] E8.3 human-readable capability table.
- [ ] E8.4 generated `llms.txt` research.
- [ ] E8.5 generated agent context.
- [ ] E8.6 architecture metadata validation.

## EPIC 9 — Telemetry

- [ ] E9.1 Telemetry port in core.
- [ ] E9.2 OpenTelemetry adapter.
- [ ] E9.3 Common capability spans.
- [ ] E9.4 transport span linking.
- [ ] E9.5 MCP/GenAI semantic convention compatibility.
- [ ] E9.6 no-op telemetry cost benchmark.

## EPIC 10 — v0.1 release gate

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

## EPIC 0A — Project/app scaffolding

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

## EPIC 1A — Modular app runtime

- [ ] E1A.1 Define app/module descriptor.
- [ ] E1A.2 Register app-owned capabilities.
- [ ] E1A.3 Detect duplicate app identities.
- [ ] E1A.4 Expose app metadata through introspection.
- [ ] E1A.5 Define cross-app public contract rules.
- [ ] E1A.6 Freeze app registry during project compilation.

## EPIC 0B — Agentic repository governance

- [ ] E0B.1 Establish GitHub Issue labels for type/area/priority.
- [ ] E0B.2 Configure branch rulesets for `main`.
- [ ] E0B.3 Configure branch rulesets for `develop`.
- [ ] E0B.4 Require relevant CI checks before merge.
- [ ] E0B.5 Configure allowed merge strategies.
- [ ] E0B.6 Validate GitHub CLI autonomous workflow.
- [ ] E0B.7 Validate Issue → branch → PR → merge → close flow.
- [ ] E0B.8 Decide single-agent or dual-agent review mode for repository governance.
- [ ] E0B.9 Configure independent reviewer identity when available.
- [ ] E0B.10 Configure auto-merge policy where safe.
- [ ] E0B.11 Replace placeholder OWNER/REPO in security Issue template.
- [ ] E0B.12 Document release and hotfix automation evidence.

### Acceptance

- normal work cannot bypass the documented PR flow;
- agent can create and close an Issue through a merged PR;
- required checks are enforced;
- force-pushes to protected branches are blocked;
- no workflow requires an impossible self-approval;
- the complete lifecycle is visible and understandable to a human maintainer.

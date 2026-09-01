# AGENTS.md — Instructions for Coding Agents

## Mission

Build Agnara as a Python 3.14-native, capability-first, transport-neutral framework for modern services consumed by humans, applications and AI agents.

You have broad permission to create, modify, move and delete repository files required by the documented roadmap, but architectural constraints in this file are mandatory.

## Mandatory reading order

Before implementing:

1. `VISION.md`
2. `PRINCIPLES.md`
3. `ARCHITECTURE.md`
4. `docs/rfc/0001-capability-runtime.md`
5. `docs/API_DESIGN.md`
6. `BACKLOG.md`
7. `QUALITY_GATES.md`

Do not start by generating hundreds of files.

## Working method

Work backlog item by backlog item.

Before each task:

1. identify its acceptance criteria;
2. identify affected package boundary;
3. inspect existing implementation;
4. avoid duplicate work;
5. mark `[~]` only when actually starting.

After each task:

1. run focused tests;
2. update docs if behavior changed;
3. run relevant architecture tests;
4. mark `[x]` only when acceptance criteria pass.

## Core invariants

### NEVER couple core to protocols

`agnara-core` MUST NOT import:

- FastAPI;
- Starlette;
- Litestar;
- Pydantic;
- msgspec;
- MCP SDK;
- A2A SDK;
- OpenTelemetry SDK;
- Uvicorn;
- Granian;
- any LLM provider SDK.

If a dependency appears necessary, stop and write an ADR explaining why the interface cannot live in an adapter.

### NEVER make HTTP the semantic source of truth

No core type named around:

- Request;
- Response;
- HTTPException;
- Route;

may define general capability behavior.

Transport packages may use these concepts.

### NEVER make MCP the semantic source of truth

A capability is not intrinsically a tool.

### NEVER make documentation UI the semantic source of truth

`agnara-core` MUST NOT depend on OpenAPI tooling, Swagger UI, ReDoc, Scalar or
another browser documentation implementation.

`agnara-http` may project compiled HTTP exposures to OpenAPI.

Documentation UIs consume generated OpenAPI through replaceable optional
providers. Agnara Explorer consumes filtered protocol-neutral introspection,
not OpenAPI alone.

Human UI and machine-readable discovery must remain independently
configurable. Hiding an operation in a UI is never authorization.

### NEVER put LLM calls in core

Agentic-native means agents are first-class consumers, not that the framework owns model reasoning.

### NEVER optimize by guess

No Rust/native component until benchmarks prove a bottleneck and an ADR is accepted.

## Python baseline

Minimum: Python 3.14.

Prefer modern Python 3.14 language/library capabilities when they simplify the design.

The implementation must not depend on accidental GIL serialization.

Treat shared mutable state as a concurrency problem.

## Concurrency rules

- use structured concurrency for owned concurrent work;
- propagate cancellation;
- do not fire-and-forget tasks from the core runtime;
- make lifecycle ownership explicit;
- document locks and mutable caches;
- prefer immutable compiled registries.

## Public API discipline

The public API is a product.

Do not expose internal implementation classes merely because they exist.

Before adding public syntax, compare it against `docs/API_DESIGN.md`.

Prefer obvious Python over clever magic.

## Dependency injection discipline

DI must remain transport-neutral.

Avoid implicit parameter classification rules that become ambiguous.

Do not copy FastAPI's HTTP-dependent DI model.

## Schema discipline

Core defines schema contracts, not a model-library dependency.

Keep adapters replaceable.

## Error discipline

Core errors are protocol-neutral.

HTTP status codes exist only in HTTP adapter mapping.

MCP/A2A error structures exist only in their adapters.

## Security discipline

Policy evaluation order is security-sensitive.

Do not change it without tests and an ADR/RFC update.

Never treat `risk`, `effects` or `confirmation` metadata as a substitute for authorization.

## Performance discipline

Move reflection and graph work to compilation/startup where possible.

Keep the invocation hot path measurable.

Every optimization must preserve a readable reference design.

## Documentation discipline

Do not claim support for:

- a protocol version;
- free-threading;
- a platform;
- benchmark superiority;
- production readiness;

unless CI or reproducible evidence proves it.

## Backlog discipline

`BACKLOG.md` is the source of task state.

Do not mark multiple large epics complete because scaffolding exists.

## Quality commands

The intended final gate is:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Add package-specific commands when useful.

## Git

Do not push unless the human explicitly asks for a push.

When asked to prepare a final commit, first verify the entire documented quality gate appropriate to the current stage.

## Stop conditions

If two architectural documents conflict:

1. do not invent a compromise silently;
2. identify the conflict;
3. prefer the newer approved ADR;
4. update stale documentation in the same change.

If no decision exists, create a draft ADR with options and proceed only with the least-locking reversible choice.

## Definition of success

The repository should remain understandable to a new human or coding agent without reverse-engineering hidden framework magic.

Agnara should be easier to extend by adding an adapter than by changing its core.

## App and scaffolding invariants

Read before changing generator behavior:

- `docs/APPLICATION_MODEL.md`
- `docs/CLI_SPEC.md`
- `docs/SCAFFOLDING.md`
- `docs/PROJECT_MANIFEST.md`
- `docs/rfc/0002-project-app-scaffolding.md`

An app represents a bounded context.

Do not create separate runtime classes such as `HttpApp`, `McpApp`, `A2AApp` to implement CLI profiles.

Profiles and shortcut commands only choose generated adapters.

Default generated production architecture is modular hexagonal.

Generated domain/application code must not import protocol SDKs.

Generators must:

- support dry-run;
- be deterministic;
- refuse overwrite by default;
- support non-interactive execution;
- expose machine-readable output where documented;
- update project metadata safely;
- never silently delete modified files.

## Documentation and discovery invariants

Read before changing OpenAPI generation, documentation routes/providers,
introspection or Agnara Explorer behavior:

- `docs/rfc/0003-http-documentation-and-capability-explorer.md`
- `docs/adr/0018-replaceable-documentation-providers.md`
- `docs/REFERENCE_RESEARCH.md`

Use pinned self-hosted UI assets as the production baseline. CDN assets
require explicit opt-in, exact versions and documented CSP/integrity effects.

Apply visibility, redaction and authorization before serializing OpenAPI or
introspection. Never expose secrets, runtime dependency values, private
capabilities or sensitive policy internals automatically.

## GitHub autonomous development workflow

Read `GIT_WORKFLOW.md` and `AGENT_OPERATING_MODEL.md` before performing repository work.

Agnara uses:

```text
BACKLOG
→ Issue
→ Branch
→ Implementation
→ Quality Gates
→ Commit
→ Push
→ PR
→ Review
→ Merge
```

GitHub Issues are executable work units.

One Issue → one branch → one PR is the default.

Before starting new work, inspect existing open PRs and Issues.

Normal task branches start from `develop` and target `develop`.

`main` receives releases/hotfixes through PRs.

Agents may autonomously create Issues, branches, commits, PRs, reviews and merges when repository permissions permit.

An agent MUST NOT approve its own Pull Request.

If only one GitHub identity is available, perform a mandatory documented self-review and rely on objective required checks rather than fabricating approval.

If an independent reviewer identity is available, prefer dual-agent review.

Never weaken repository protections to bypass failing work.

Never push normal feature work directly to protected branches.

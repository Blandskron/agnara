# AGENTS.md â Instructions for Coding Agents

Current repository documentation describes the current framework. Historical release reconstruction must use Git history, tags or GitHub Releases and must not be inferred from active documentation.

Never revive superseded release documentation into current context unless the task explicitly requires historical research.

## Bootstrap (START HERE)

If you are an agent and were just told "Lee AGENTS.md y comienza" or similar:
1. **Read `MULTI_AGENT_PROTOCOL.md`**. It defines how you coordinate with other agents safely.
2. Use `python scripts/agent.py next` to find your next assigned task.
3. Use `python scripts/agent.py claim <issue> <worker_id>` to take ownership.
4. If working locally with other agents, use `git worktree` (see protocol doc).

## Mission

Build Agnara as a Python 3.14-native, capability-first, transport-neutral framework for modern services consumed by humans, applications and AI agents.

You have broad permission to create, modify, move and delete repository files required by the documented roadmap, but architectural constraints in this file are mandatory.

## Mandatory reading order

Before implementing:

1. `VISION.md`
2. `PRINCIPLES.md`
3. `ARCHITECTURE.md`
4. `docs/API_DESIGN.md`
5. `BACKLOG.md`
6. `QUALITY_GATES.md`

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

## Frozen core value types

Read `docs/adr/0020-reliable-frozen-slotted-value-types.md` before adding a
frozen slotted dataclass to `agnara-core`.

Use the internal `frozen_slots_dataclass` decorator rather than raw
`@dataclass(frozen=True, slots=True)`. It preserves slots while ensuring that
declared and unknown attribute mutation raises `FrozenInstanceError` instead
of a CPython-generated `TypeError`.

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

Blandskron grants agents standing authorization to create Issues, branches,
commits, pushes and Pull Requests required by an assigned repository task.
Do not ask again for confirmation of those ordinary Git/GitHub workflow
operations. This authorization does not permit an agent to approve or merge
its own PR, bypass protections, publish packages, create release tags or
GitHub Releases, or modify protected-branch governance.

When asked to prepare a final commit, first verify the entire documented quality gate appropriate to the current stage.

For every PR, decide explicitly whether the change needs an entry under
`CHANGELOG.md` `[Unreleased]`. User-visible behavior, public API, configuration,
security, dependency, migration and contributor-workflow changes require one.
Explain justified omissions in the PR.

Read `docs/adr/0095-synchronized-releases-and-curated-changelog.md` before
changing package versions, changelog release headings or Git tags. Never
publish the `0.0.0` development sentinel.

## Authoría de agentes y revisión humana

Lee ADR 0092 y `.github/ai-agent-identities.toml` antes de crear un commit.
Cuando un agente implementa materialmente un cambio, el agente es el autor
primario del commit: usa exactamente su `git_name` y `email` registrados. No
uses a Blandskron como `Author` ni como `Co-authored-by` para trabajo escrito
por el agente. No inventes identidades, no atribuyas trabajo a otro agente y
no agregues trailers por defecto.

Las identidades actualmente registradas incluyen `Codex <codex@openai.com>`,
`Claude <noreply@anthropic.com>` y
`gemini-cli <218195315+gemini-cli@users.noreply.github.com>`; consulta el
registro, no esta lista, como fuente exacta antes de cada commit.

Antes de `push`, verifica la authoría y el mensaje:

```bash
git log -1 --format=fuller
git log -1 --format=%B
```

Confirma que el autor es la identidad exacta del agente, y que Blandskron no
aparece como autor ni coautor salvo que haya implementado materialmente ese
commit y solicitado crédito explícito. Si participaron varios agentes, prefiere
commits separados con la identidad de quien hizo cada parte; no conviertas una
revisión en coautoría.

El agente abre o prepara un PR a `develop`, solicita revisión formal a
`Blandskron` y lo deja sin fusionar. Un comentario o self-review no reemplaza
la revisión formal de GitHub (`Approve`, `Request changes` o `Comment`).
Blandskron es owner, maintainer, revisor, decisor de arquitectura/gobernanza y
autoridad de merge; su revisión, no la authoría del commit, representa su
contribución habitual al trabajo del agente.

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
â Issue
â Branch
â Implementation
â Quality Gates
â Commit
â Attribution verification
â Push
â PR
â Review
â Merge
```

GitHub Issues are executable work units.

One Issue â one branch â one PR is the default.

Before starting new work, inspect existing open PRs and Issues.

Normal task branches start from `develop` and target `develop`.

`main` receives releases/hotfixes through PRs.

Agents may autonomously create Issues, branches, commits and PRs when repository permissions permit. They must request formal review from Blandskron and leave agent-authored PRs unmerged; only the maintainer merges after review and required CI.

An agent MUST NOT approve or merge its own Pull Request. Self-review is supplementary evidence, never a substitute for formal maintainer review.

Never weaken repository protections to bypass failing work.

Never push normal feature work directly to protected branches.

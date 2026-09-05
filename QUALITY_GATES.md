# Quality Gates

## Definition of done

A feature is not done when code exists.

It is done when:

1. public behavior is specified;
2. unit tests cover normal and failure paths;
3. typing passes;
4. lint/format passes;
5. architecture rules pass;
6. documentation is updated;
7. performance-sensitive changes include benchmark evidence;
8. security-sensitive changes include threat analysis;
9. no unrelated coupling was introduced;
10. attribution is truthful and evidence-backed.

## Required local checks

Target commands:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

Exact command names may evolve, but equivalent gates must remain.

Documentation browser conformance is a separate required CI lane because the
ordinary cross-platform gate must not depend on a preinstalled browser. Its
reproducible commands are:

```bash
uv run playwright install --with-deps chromium
AGNARA_RUN_BROWSER_TESTS=1 uv run pytest tests/http/test_documentation_browser.py -m browser
AGNARA_RUN_BROWSER_TESTS=1 uv run pytest tests/http/test_explorer_browser.py -m browser
```

Playwright is version-pinned in the development lock. Without the explicit
environment flag, pytest still collects these tests and reports them skipped;
only the dedicated browser job is evidence that they passed.

Explorer browser checks cover semantic landmarks, accessible names and tree
content, keyboard navigation, direct links/reloads and representative desktop
and mobile viewports. Accessibility-tree assertions are not evidence of an
actual screen-reader session or WCAG certification.

## Where the gates are authoritative

CI is the authoritative record that the gates passed. `.github/workflows/ci.yml`
runs every command above, on Linux, macOS and Windows, plus a lockfile check,
and aggregates them into a single required `CI` status.

A developer machine may be unable to run part of the gate. When that happens:

1. state precisely which gate could not run, and the evidence;
2. do not weaken a security or system policy to work around it;
3. do not mark the affected backlog item complete on local results alone;
4. rely on CI for the missing gate before merge.

Reporting a gate as passing when it was never executed is a worse failure
than a red build.

## Test pyramid

```text
unit
  capability
  registry
  DI
  plan compiler
  policies
  schemas

architecture
  forbidden imports
  package cycles
  dependency direction

contract
  public API behavior

conformance
  ASGI
  OpenAPI
  MCP
  A2A later

integration
  composed application surfaces

benchmark
  startup
  memory
  hot path
  concurrency
```

## Coverage

Do not optimize for a vanity percentage.

Critical runtime branches require explicit behavioral tests.

Coverage should be reported, but missing behavior is more important than reaching an arbitrary number.

## Mutation testing

Evaluate mutation testing after the core stabilizes, especially for:

- policy engine;
- dependency scopes;
- error mapping;
- execution ordering.

## Property-based testing

Use property-based tests where contracts are algebraic or combinatorial:

- router matching;
- schema round trips;
- dependency DAGs;
- metadata normalization.

## Protocol conformance

MCP's bounded official SDK suite and exclusions are recorded in
`docs/MCP_CONFORMANCE.md`. Run `uv run pytest tests/mcp tests/architecture`.
These tests run in the ordinary CI matrix; an in-process modern SDK exchange
is not evidence of network transport or complete MCP protocol conformance.

Each adapter should record:

- supported specification version;
- unsupported optional features;
- test suite version;
- generated fixtures.

OpenAPI 3.2 claims additionally require deterministic generated documents,
structural/conformance fixtures and renderer tests for every documented UI
provider. A UI accepting the version string is not sufficient evidence that it
renders new 3.2 semantics correctly.

### Protocol version pins

Every protocol adapter must name exact specification revisions and test them
against an exact official SDK baseline. A protocol SDK dependency belongs only
to its adapter package; it must not enter `agnara` core or sibling adapters.
SDK support for a revision is necessary but insufficient for an Agnara
conformance claim. Claims require adapter-level fixtures for the implemented
projection, negotiation and error surface.

Protocol exposure registries must reject invalid and duplicate wire names at
startup, preserve declaration order, retain their protocol-neutral capability
definitions, and compile into immutable snapshots. A protocol adapter must
not infer that an arbitrary callable is authorized or registered merely
because it is callable.

Protocol schema projections must consume compiled core schemas rather than
repeat handler input classification. They must exclude protected dependency
and context parameters, preserve property and required-field order, reject
non-JSON fragments at startup, and detach protocol documents from core schema
state. Optional output contracts must not be published before runtime output
validation enforces them.

Protocol discovery must advertise only versions and capabilities actually
served. List results must preserve deterministic compiled order, use explicit
cache hints, handle cursors according to the pinned protocol, and return data
detached from immutable startup state. Authentication bridges must consume
only verifier-approved request context, keep bearer credentials and arbitrary
claims out of application mappers, require explicit actor/subject semantics,
and fail closed with redacted protocol errors. Scope-filtered discovery must
remain request-isolated, private and immediately stale; cache metadata or
discoverability never substitutes for invocation authorization.

Protocol interaction projections must start from canonical adapter-facing
outcomes, validate their complete reviewed detail shape, and serialize only
the minimum caller-safe fields supported by the pinned protocol. MCP form
elicitation uses its restricted flat-schema vocabulary and never carries
credentials, capability internals, arbitrary interaction hints or verifier
diagnostics. Client acceptance or submitted form values remain untrusted input
and must not become confirmation evidence without independent application
verification. An interim projection must not claim MRTR resumption, state
integrity or tool-invocation support that it does not implement.

Protocol resumption must use the mechanism the pinned revision defines rather
than an extension the adapter has not implemented. An optional protocol
extension is never advertised, and never implied by a legacy tool field,
without its own reviewed implementation and conformance evidence. Adapter
state echoed by a client is attacker-controlled until a verified boundary
replaces it, and that boundary must be installed explicitly on the server
tier the adapter actually builds on rather than assumed from a higher-tier
default. Multi-instance deployments require explicitly shared key material;
a process-local convenience key is never a production default. Round-level
integrity, expiry and request binding do not constitute invocation replay
protection, and a resumed round re-evaluates policy and confirmation evidence
exactly as a first round does.

## Benchmark integrity

Never benchmark development mode against optimized competitors.

Comparative HTTP benchmarks must pin competitor versions outside
distributable package dependencies, exercise equivalent successful output,
validate correctness outside every timed sample, rotate scenario order, retain
raw samples and record the included/excluded measurement boundary. Framework,
server and network results must remain distinct. CI checks the benchmark
contract, never a workstation-derived latency threshold.

Record:

- OS;
- CPU;
- Python build;
- free-threaded vs conventional;
- server;
- worker count;
- serializer;
- payload;
- concurrency;
- command;
- commit SHA.

## Security gates

Before any release beyond experimental alpha:

- threat model;
- dependency audit;
- secret scanning;
- CodeQL or equivalent static analysis;
- private vulnerability reporting process;
- security boundary tests.

Documentation/discovery releases additionally require visibility/redaction
tests, CSP and XSS browser tests, external-asset/network assertions, try-it and
OAuth flow tests, and accessibility/responsive smoke tests for each supported
UI. Remote scripts and styles require exact-version URLs, SHA-384 SRI,
anonymous CORS, matching canonical CSP origins and an exact deployment origin
allowlist. Vendored UI manifests, hashes, licenses and wheel contents are
release evidence. Hiding an operation in a UI must never be the authorization
mechanism.

## Free-threading gate

At least one CI lane should eventually run with CPython free-threaded 3.14t where the dependency ecosystem allows it.

Failures must not be hidden by globally re-enabling the GIL without documentation.

## Merge governance gate

A change is not integration-ready merely because local tests pass.

Before merge:

- GitHub Issue exists and acceptance criteria are satisfied;
- PR exists;
- required CI is green;
- architecture checks pass;
- review gate is complete;
- attribution integrity gate is complete;
- unresolved review conversations are resolved;
- backlog/docs are synchronized.

After merge, the Issue must actually be closed. Merging into `develop` does
not close it, because GitHub auto-closes only on the default branch.

A single-agent self-review is not represented as an independent GitHub approval.

Where independent reviewer identities exist, use them for formal approval.

## Changelog and release consistency gate

Every PR records one of these outcomes:

- a release-note-worthy change has a concise entry under `[Unreleased]`; or
- no entry is required and the PR explains why.

Before creating a release tag:

- every first-party `pyproject.toml` contains the exact selected PEP 440
  version;
- the selected version is not `0.0.0`;
- `uv.lock` is refreshed and current;
- `CHANGELOG.md` has a dated section for that exact version and a new
  `[Unreleased]` section;
- comparison links reference the previous and new tags correctly;
- package builds and install/import smoke tests pass;
- the full required CI, review and attribution gates are green;
- the annotated `v<version>` tag targets the exact reviewed `main` commit;
- publishing authorization, license and credentials/trusted publishing are
  present before any registry upload.

Documentation of this checklist is not evidence that release or hotfix
automation has run. Record actual commands, artifacts, hashes and GitHub links
before completing E0B.12.

## Release readiness program

`docs/releases/RELEASE_PLAN.md` defines the progressive path from the published
`0.1.0a2` to `0.1.0`, and `scripts/check_release_readiness.py` measures how far
the current state has come.

That program **supplements** this document and never relaxes it. Where the two
differ, this document wins. In particular the security gates above keep their
own scope: the readiness tool reports the observed state of each item and
refuses to decide whether a given release is still inside the
"beyond experimental alpha" exemption.

A readiness percentage is informational. A release is ready only when every
mandatory gate is satisfied, and satisfied means evidence exists — recorded
against the commit it was produced on, so a green record cannot outlive the
code it described.

```bash
uv run python scripts/check_release_readiness.py
```

## Attribution integrity gate

Before push and again before merge, review attribution as a semantic integrity
check:

- primary authorship matches the actual operating mode;
- each `Co-authored-by` participant materially authored the change;
- each trailer uses an authorized, GitHub-verifiable identity;
- no model/tool/provider label was converted into a guessed identity;
- review-only agents are represented in the review trail unless they also
  contributed implementation;
- non-verifiable agent work is documented in the Issue or PR;
- legitimate trailers survive amend, rebase, commit recreation and squash
  preparation;
- the primary author is not duplicated as a co-author.

After merge, inspect the accepted commit and confirm that its authorship and
trailers match the reviewed squash/merge message.

This gate is a required human/agent review until a trusted, repository-owned
identity registry exists. Do not add brittle automation that treats an
unregistered but legitimate contributor as fabricated, and do not create a
registry populated by guesses merely to automate the check.

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
```

Playwright is version-pinned in the development lock. Without the explicit
environment flag, pytest still collects these tests and reports them skipped;
only the dedicated browser job is evidence that they passed.

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

Each adapter should record:

- supported specification version;
- unsupported optional features;
- test suite version;
- generated fixtures.

OpenAPI 3.2 claims additionally require deterministic generated documents,
structural/conformance fixtures and renderer tests for every documented UI
provider. A UI accepting the version string is not sufficient evidence that it
renders new 3.2 semantics correctly.

## Benchmark integrity

Never benchmark development mode against optimized competitors.

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
UI. Hiding an operation in a UI must never be the authorization mechanism.

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

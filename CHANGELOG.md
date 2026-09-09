# Changelog

Notable changes to Agnara are recorded here. The format is inspired by Keep a
Changelog, and release versions follow the synchronized PEP 440 policy in ADR
0021.

`0.1.0a2` is the first published release. `0.1.0a1` was tagged but never
reached PyPI: its release run failed in artifact validation, so the publish job
never executed. `0.1.0a4` was tagged and *partially* published: the core wheel
reached PyPI and the other thirteen artifacts did not. It is superseded by
`0.1.0a7` and should not be installed; see the recovery sections below. The
`v0.1.0a5` workflow was aborted by publication readiness before its first
upload, so no `0.1.0a5` artifact was published. Every first-party package in
the workspace carries the synchronized version; through `0.1.0a4` only the
`agnara` core distribution had ever been uploaded.

## [Unreleased]

## [0.1.0a7] - 2026-09-08

Publication and security recovery after the immutable `v0.1.0a6` workflow
reached PyPI and failed on its first upload. No A6 artifact was published.

### Security

- Replaced the Scalar bundle's hostname substring assertion with extraction
  and exact comparison of URL hostnames, avoiding incomplete URL checks.
- Stopped the distribution checker CLI from copying untrusted artifact
  diagnostics into CI logs; programmatic callers retain the detailed results.
- Added explicit read-only workflow permissions to agent-coordination CI.

### Changed

- Synchronized the seven distributions and six exact core pins at `0.1.0a7`.
- Publication evidence now records the exact PyPI Project name for each
  Trusted Publisher, requires a confirmed top-level record and rejects
  duplicate project entries.
- Moved Execution Semantics unchanged to `0.1.0a8`; no functional work from
  that horizon is included here ([#344]).

### Fixed

- Recorded that PyPI rejected `agnara-a2a` with `400 Non-user identities
  cannot create new projects`. The distribution metadata and manifest both
  use the canonical dash-separated name; `agnara_a2a` is only the required
  wheel/sdist filename normalization. The Pending Trusted Publisher must be
  recreated for Project name `agnara-a2a` with the documented OIDC tuple.

## [0.1.0a6] - 2026-09-08

> **Publication status: aborted on the first upload.** PyPI rejected
> `agnara-a2a` because no Pending Trusted Publisher matched its canonical
> project name and the workflow identity. No `0.1.0a6` artifact was published.

Publication recovery after the immutable `v0.1.0a5` attempt stopped safely
before upload. This release changes no runtime behavior: it carries the same
framework code with synchronized `0.1.0a6` package metadata and a publication
record that remains fail-closed pending owner confirmation.

### Changed

- Prepared all seven distributions and exact adapter-to-core pins for
  `0.1.0a6`; the publication target remains `UNVERIFIED` until the owner reads
  back every PyPI Trusted Publisher tuple.
- Moved the unchanged Execution Semantics horizon—streaming, execution
  identity and idempotency, and performance budgets—to `0.1.0a7` ([#341]).

## [0.1.0a5] - 2026-09-08

> **Publication status: aborted before upload.** The immutable `v0.1.0a5` tag
> ran the corrected workflow, and publication readiness stopped it before the
> first upload because the Trusted Publisher record remained `UNVERIFIED`.
> No `0.1.0a5` artifact was published and no GitHub Release is claimed.

Publication-recovery implementation carried by the aborted attempt. It keeps
the `0.1.0a4` runtime unchanged and replaces the release system that published
one of fourteen A4 artifacts and reported nothing wrong with the other
thirteen.

### Security

- Publication-readiness diagnostics now redact URL credentials, query data,
  fragments and recognizable secret formats before writing terminal output or
  GitHub Actions annotations. Index errors retain the safe origin, HTTP status,
  project and version context, while control characters and encoded newlines
  cannot inject additional workflow commands.

### Fixed

- `0.1.0a4` was published partially. The upload accepted
  `agnara-0.1.0a4-py3-none-any.whl` and was rejected on the next file,
  `agnara_a2a-0.1.0a4-py3-none-any.whl`, with
  `400 Non-user identities cannot create new projects` — PyPI's answer when no
  pending Trusted Publisher matches the uploaded project name for the
  authenticated OIDC identity. Twine uploads every wheel before any sdist and
  stops on the first failure, so the `agnara` sdist and all twelve sibling
  artifacts were never uploaded, post-release verification never ran, and no
  GitHub Release was created. `v0.1.0a4` and the file already on PyPI are
  historical and are not modified, moved or replaced. Recommended disposition
  for `agnara 0.1.0a4` is a yank after `0.1.0a5` is verified complete.

- The kernel is now published **last**, after every sibling distribution.
  Multi-project uploads are not atomic, so an order exists whether or not
  anyone chooses one, and `0.1.0a4` chose the harmful one: `agnara` announced a
  version whose adapters did not exist, and `pip install agnara==0.1.0a4`
  succeeded into a set that could not be completed. With the kernel last a
  partial upload fails closed — an adapter pins its kernel exactly, so a
  sibling published without it resolves for nobody and the published `agnara`
  version does not move. ADR 0079.

- Each distribution is now uploaded in its own reviewed step rather than by one
  glob over `dist/`. A failure names the distribution it stopped on and leaves
  the rest unattempted, instead of failing somewhere inside a fourteen-file
  batch. `skip-existing` stays off: a file that already exists is a real
  condition to stop on, not noise to suppress.

### Added

- **PUBLISH READY is now a separate claim from CODE READY.**
  `scripts/check_publication_readiness.py` owns everything between a correct
  commit and seven complete distributions on an index: the reviewed set, the
  workspace layout, synchronized versions, exact first-party pins, the
  lockfile, the artifact set, release notes, the dated changelog section, the
  annotated tag, and the external registry configuration. It runs offline in
  CI, and with `--online` in the release workflow both before the first upload
  and after the last one.

- `docs/releases/publication.json` records, per project and per target version,
  that a human read the Trusted Publisher tuple back from PyPI. It is
  `UNVERIFIED` until the owner fills it in, and the release workflow refuses to
  upload while it is. This is the control `0.1.0a4` did not have: the same
  requirement existed then, as a paragraph in a release note.

- A `publication-prerequisites` gate in `scripts/check_release_readiness.py`,
  and a mandatory manual `pypi-trusted-publishers` gate that no automated check
  can ever satisfy.

- `docs/distributions.json` is the single source of truth for the seven
  distributions — names, import packages, console scripts and adapter-owned
  third-party requirements. `scripts/distributions.py` reads it for the release
  tooling and the architecture tests, and prints it for the workflows, so the
  seven names have one definition instead of the six independent copies that
  previously nothing compared. Canonical project names stay dash-separated;
  `_` in a wheel or sdist filename is PEP 427/625 normalization and is not a
  naming defect.

- Post-publication verification is its own job and asserts completeness, not
  just installability: every one of the seven must carry both a wheel and an
  sdist on the index at the released version. `0.1.0a4` would have failed this
  even for the one project it reached.

### Changed

- The GitHub Release is created only after publication *and* post-publication
  verification succeed, as a job that depends on both. In `0.1.0a4` these were
  three steps of one job, so the failed upload also silently cancelled
  verification and the release. A successful GitHub Release can no longer exist
  while PyPI is incomplete.

- Every third-party action on the publication path is pinned to a full commit
  SHA with the human version in a trailing comment: `actions/checkout`,
  `astral-sh/setup-uv`, `actions/upload-artifact`, `actions/download-artifact`,
  `pypa/gh-action-pypi-publish` and `softprops/action-gh-release`. A moving tag
  on a job that holds `id-token: write` is a supply-chain decision, not a
  convenience.

- `0.1.0a5` is a publication-recovery release, so the Execution Semantics
  horizon — streaming, execution identity and idempotency, performance budgets
  — moves intact to `0.1.0a6`. No part of it is started here. ADR 0078.

## [0.1.0a4] - 2026-09-08

> **Publication status: partial, superseded by `0.1.0a5`.** Of the fourteen
> artifacts this release built, exactly one reached PyPI —
> `agnara-0.1.0a4-py3-none-any.whl`. The upload was rejected on the next file
> and stopped, so `agnara 0.1.0a4` has no sdist and none of the six sibling
> distributions was published. Do not install `0.1.0a4`; install `0.1.0a5`.
> The tag, the commit and the uploaded file are historical and unmodified. The
> changes described below are the changes this release contained; they are
> reproduced in `0.1.0a5`, which is the release that publishes them.

### Added

- Required CI now analyzes Python and GitHub Actions with SHA-pinned CodeQL
  actions and job-scoped security-result upload permissions, including during
  release validation. A skipped required job fails the aggregate CI check.
  Repository secret scanning, push protection and Dependabot alerts/security
  updates are enabled; automated updates still require normal PR review.

- A CLI target's attribute may be a dotted path. `agnara inspect`,
  `agnara graph`, `agnara context` and `agnara schema openapi` accept
  `billing.bootstrap:container.app`, and `--dependencies` accepts
  `container.registry`, so an application assembled inside a container or
  returned by a factory no longer has to be re-exported at module level to be
  usable from the command line. Each segment is validated as an identifier
  before anything is imported, and a missing segment is named in the error
  rather than leaving the operator to guess which half of the path was wrong.
  A compile failure with no registry named now also suggests `--dependencies`,
  because core cannot distinguish an unbound dependency from an unsupported
  annotation ([#313]).

- A threat model for the surface `0.1.0a4` publishes. `docs/THREAT_MODEL.md`
  records assets, trust boundaries, attacker-controlled inputs and abuse cases,
  and separates protections that name the test proving them from assumptions
  delegated to ASGI servers, proxies and applications. `tests/security/`
  regresses it: adversarial HTTP and ASGI events, authorization and disclosure
  properties across both transports, and a repository-wide credential scan that
  covers the fixtures, docs and workflows a distribution gate never sees. It is
  scoped to a4 and is not the beta security program; the document ends with
  what the audit did not do. The audit's cross-transport scope finding was
  resolved by the common execution-plan policy implemented for A4-09
  ([#307], [#308], [#309]).

- One exposure model governs every protocol adapter. `agnara.exposure` owns
  neutral identity — adapter kind, project-local surface name, adapter-local
  name — per-surface adapter compilation and a single frozen availability
  registry, and both shipped adapters now compile into it. Before this,
  `agnara-http` compiled a private route registry, `agnara-mcp` froze an
  independent tool table, and `describe_app(..., exposures=...)` accepted a
  third answer written by hand. The third one was not merely redundant, it was
  empty: nothing outside tests ever filled it, so every real application served
  HTTP and MCP traffic while its introspection snapshot reported no exposures
  at all. Snapshots now derive exposures from compiled availability and can
  neither omit nor invent one. An adapter returns its dispatch artifact and its
  records in one value and derives the records from the artifact, so the two
  cannot drift; two named surfaces of one protocol became expressible;
  duplicate identities, unknown capabilities and post-freeze registration fail
  at startup. `Mcp` gains a keyword-only `surface` and `compile_surface()`
  beside the existing `compile()`. Seven new `provisional` exports, no
  third-party dependency, and no kernel change needed for a third adapter.
  ADR 0070 answers RFC 0006 and records the five spike decisions, the threat
  analysis and the rejected alternatives ([#293]).

### Fixed

- HTTP lifespan now closes its owned singleton dependency resources before
  application shutdown, including when no custom lifecycle callback is supplied.

- Release publication now rejects lightweight tags, a checkout different from
  the tag, and tagged commits outside reviewed `main` history, both before
  building and before uploading. Correct MCP serialization/error guidance and
  the documented CLI module invocation for A4 (#332).


- The `agnara-mcp` README passed `plans` to `project_mcp_tools()` and
  `build_mcp_server()` in three examples without ever showing how to build it,
  so the one document a consumer of that distribution reads could not be
  followed to a working MCP surface. Unlike `agnara-http`, this adapter
  compiles no plans of its own, which made the omission the difference between
  composing a server and not. An "Execution plans" section now derives them
  from `FrozenMcpTools.exposures`, states that matching is by capability
  identity rather than order, and names the `McpToolDefinitionError` raised
  when an exposure has no plan. The block is registered in
  `tests/docs/test_documented_examples.py`, so it runs as written on every
  test run rather than being trusted.

- The a3-to-a4 migration guide now distinguishes the development candidate
  from the final release and pins installation commands to the matching core
  and adapter versions. Architecture and API-design documentation now agree
  with the implemented public HTTP and introspection composition surfaces.

- A JSON request body nested beyond the decoder's stack raised `RecursionError`
  out of the HTTP dispatcher. 80 KB was enough -- far inside the 1 MiB default
  limit -- from an unauthenticated client, before any capability ran: the
  dispatcher sent nothing and the ASGI server decided what the client and the
  operator's log received, bypassing the reviewed problem mapping and its
  redaction. A platform-independent nesting ceiling now rejects it with a `400`
  before decoding or capability execution, naming the reason without echoing
  the body. A
  value nested deeper than the interpreter can walk reached the same escape at
  the response boundary and now ends at the existing redacted `500`.
- `_read_body` bounded a request body's total bytes but not the number of ASGI
  events carrying it. An empty chunk moves `max_body_bytes` no closer to its
  limit, so a client sending them with `more_body` set held a worker open
  indefinitely while growing a list without bound. Empty events are now capped.
- `request_timeout` was documented as a per-request deadline. It starts once
  the request is bound, so it bounds capability execution and not how long a
  client may take to send its body; that belongs to the ASGI server or the
  proxy. The documentation now says which ([#308]).

### Changed

- Declared capability scopes now compile into the common execution plan before
  application policies, JSON materialization, validation, dependencies and
  handler effects. MCP no longer owns a transport-specific scope guard, HTTP
  scoped capabilities fail closed as its a4 dispatcher is anonymous, and both
  JSON transports materialize only after policy. MCP also redacts the message
  and details of explicit `internal_failure` results just as HTTP already did.
  Nested HTTP dataclass construction failures now report canonical
  `details.path` instead of pre-runtime `details.location` (ADR 0077, [#307]).

- Public API governance now covers every shipped distribution, not the kernel
  alone. `docs/public-api.json` moves to `schema_version` 3 and classifies 282
  provisional exports across 47 public modules in all seven distributions;
  `agnara-mcp`, `agnara-telemetry` and `agnara-cli` were governed by nothing but
  a count in `docs/MATURITY.md`, and `agnara-http` by a hand-written tuple in one
  test. The readiness gate now resolves each module against the source root of
  the distribution that claims it, refuses a manifest entry that reaches into a
  sibling package, fails when any distribution is missing, and scans every
  package's source in reverse so a new public module fails immediately. The
  reserved `agnara-a2a` and `agnara-events` namespaces classify their empty
  surface, because an empty `__all__` is skipped by the reverse walk and would
  otherwise be the one place a first export could appear ungoverned. Nothing is
  promoted: the alpha line still makes no compatibility promise (ADR 0076).
- `docs/INITIATIVES.md` recorded I9 as `PLANNED` while its own body described
  shipped, enforced machinery. I9 is `IMPLEMENTED` for classification and stays
  open for stability promotion, which the beta and release-candidate gates own.
- RFC 0001's proposed-API sketch is marked as what it is. It shows
  `from agnara import Agnara, Context`, an API that was never built, and the
  import audit found it presented as though it were current. The proposal text
  is unchanged; the reasoning that led away from it is the useful part of the
  record.
- Public API governance now covers every non-private core module that declares
  exports: 218 provisional names across 30 package and leaf modules. The
  readiness gate resolves both `__init__.py` and leaf `.py` modules and scans
  source in reverse, so an unclassified public module fails immediately.
  `ConfirmationPolicy` is also available from `agnara.policy`; genuinely
  private `_frozen` and `_tracking_id` helpers remain private with documented
  public alternatives (ADRs 0074, [#288], [#289]).
- The `0.1.0a4` publication boundary now covers the explicit seven-package
  workspace set instead of building, installing and publishing only `agnara`.
  The release gate inspects all fourteen wheel/sdist artifacts for synchronized
  versions, Python floor, license and README metadata/files, dependencies,
  project metadata, console scripts, package data, safe paths and accidental
  development or credential files. It then resolves only MCP/OpenTelemetry
  dependencies from the index and installs all first-party wheels with
  `--no-index`, proving isolated imports originate in `site-packages` and the
  `agnara` entry point works. The publish job promotes those same files, is
  unreachable from manual dispatch, keeps OIDC confined to a pushed tag and
  explicitly enables metadata verification and Trusted Publishing
  attestations. All six adapter names remain unpublished until the authorized
  release; A2A and events are honest zero-API reserved namespaces, not support
  claims (ADR 0073, [#291]).

- Workspace version transitions are now atomic and repository-owned. The new
  `scripts/set_workspace_version.py` command moves all seven distributions and
  six exact adapter-to-core pins together between `<target>.dev0` development
  state and the public release target, refreshes `uv.lock`, supports a
  no-write check, and rolls back source metadata if lock generation fails.
  Release-readiness and installed-wheel gates now fail on an unbounded,
  ranged, mismatched or marked core requirement. The isolated packaging lane
  closes index access while installing all locally built first-party wheels,
  preventing substitution by a public core ([#286]).
- ADR 0069 answers both questions in RFC 0007 together. During alpha, every
  adapter will require the exact synchronized core version, and `develop` will
  carry the selected current target as `<target>.dev0`; choosing only one
  leaves a demonstrated incompatible-core substitution possible. The decision
  requires one atomic, repository-tooled migration of all project versions,
  six core requirements, `uv.lock`, release checks and installed-artifact
  gates. No package metadata or version changes in this decision-only step
  ([#280]).
- The packaging gate now installs every distribution instead of one. It
  built all seven and installed only `agnara`, so the adapters' third-party
  pins were never resolved by an installer, and the documentation UIs
  `agnara-http` serves from its own package were checked for presence in
  the archive but never for reachability once installed.
  `scripts/check_distributions.py` discovers the expected
  distributions from the workspace layout, then asserts each imports from
  an installed location, that every data file in a source package resolves
  inside the installed one, that versions stay synchronized and that every
  adapter still declares its dependency on the core. The wheel and sdist
  count is derived the same way, so adding a distribution extends the gate
  rather than escaping it ([#278]).
- The public API manifest now governs every public module of the core
  distribution rather than only the top-level one: 123 exports across
  `agnara`, `agnara.capability`, `agnara.core.di`, `agnara.execution`,
  `agnara.introspection`, `agnara.policy` and `agnara.schema`, all
  `provisional`. Two thirds of the documented entry path were ungoverned —
  the README and the quickstart both open by importing `agnara.core.di`
  and `agnara.execution` — so a rename there passed every release gate. A
  test now asserts every exported name actually exists, which neither the
  manifest nor `__all__` can detect on its own. ADR 0074 subsequently extended
  that governance to every exported leaf module and added the missing reverse
  completeness check.
  `docs/public-api.json` moves to `schema_version` 2; no API is renamed,
  re-exported or promoted ([#275]).
- Compiling an `Agnara` project now freezes every mounted `App` registry as
  well as the project's aggregate registry. A mounted app can no longer accept
  declarations that the compiled project could never observe; unmounted apps
  remain open, and shared apps can still be compiled by multiple projects
  because freezing is idempotent. Declarations added after mounting but before
  compilation are included in the compiled project ([#268]).
- **Breaking.** `agnara.introspection.AppDescriptor` is renamed to
  `ApplicationDescriptor`. It describes one compiled application -- a whole
  project -- and after ADR 0011 and ADR 0065 fixed "app" as a bounded context
  it was named for something it is not, and collided with the `AppDescriptor`
  added in #254. Only the Python symbol changed: the field names, the builder
  functions, `INTROSPECTION_VERSION` and the serialized document are all
  unchanged, verified byte-for-byte ([#259]).

### Removed

- `agnara-cli` no longer publishes thirteen implementation helpers. `FileAction`,
  `GenerationError`, `GenerationPlan`, `ManifestApp`, `ManifestError`,
  `ProjectManifest`, `ResolvedTarget`, `TargetError`, `find_manifest`,
  `load_manifest`, `parse_manifest`, `resolve_attribute` and `resolve_target`
  were re-exported from underscore-prefixed modules through `0.1.0a3` without
  ever being documented, used anywhere in the workspace, or designed as an API.
  The distribution is consumed as the `agnara` command; `EXIT_OK`,
  `EXIT_FAILED`, `EXIT_USAGE` and `main` remain, and are what a caller needs to
  run that command in-process. **Migration:** code that needs one of the removed
  names is reading the CLI's implementation and should import the private module
  that defines it — `agnara_cli._generate` for the generation-plan names,
  `agnara_cli._manifest` for the `agnara.toml` names, `agnara_cli._target` for
  the target-resolution names — accepting that a private module carries no
  compatibility promise (ADR 0076).

### Fixed

- HTTP JSON bodies matching a standard-library dataclass schema now
  materialize the declared dataclass recursively before strict core
  validation. Nested dataclasses, containers, tuples, unions and JSON-valued
  enums follow the same compiled schema graph; unknown and missing fields fail
  without exposing constructor errors. Direct core invocation remains strict
  as ADR 0025 requires (ADR 0075, [#296]).

### Added

- Ecosystem interoperability has a contract and a release. Agnara could be
  run and could not be embedded: nothing stated what an external host must do
  to invoke a capability, or who owns lifecycle, routing, dependency
  containers, context, principal, errors and telemetry when two runtimes share
  a process. `docs/INTEROPERABILITY.md` now owns the interoperability contract
  and the integration matrix -- four deployment modes, two directions per
  technology with the meaningless ones discarded rather than left blank,
  fifteen kernel invariants, the anti-coupling test, the ten-step framework
  embedding contract, per-category infrastructure adapter contracts, one
  conformance scenario for every framework, and the historical reference
  strategy. RFC 0008 states fifteen open design questions and deliberately
  answers none, because several depend on I1, I2, I3, I8 and I10. Initiative
  I20 owns the work ([#282]).
- ADR 0068 gives that work a release rather than letting it land in whichever
  one is open. `0.1.0a5` is inserted between `0.1.0a4` and `0.1.0b1`, so
  streaming, execution identity and performance budgets stop being homeless;
  `0.1.0b1` becomes the interoperability and composition beta and gains
  twenty-one mandatory gates covering web, persistence, schema, presentation,
  background execution, observability, protocol composition, embedding,
  side-by-side composition and progressive adoption. Both alphas gain an
  explicit guardrail: neither may declare stable support for an external
  framework, because an integration that hides an insufficient public API
  behind a framework-specific convenience turns the `0.1.0a4` "public APIs are
  sufficient" gate green and deletes the finding it exists to surface
  ([#282]).
- The guardrail is a test rather than a promise. A framework integration
  arrives as a declared dependency before anything imports it, so
  `ECOSYSTEM_INTEGRATIONS` denies web frameworks, ORMs, drivers, migrations,
  caches, brokers, task runtimes, durable execution engines, template engines,
  error reporters and GraphQL/gRPC libraries to every distribution rather than
  only the kernel -- while leaving the protocol SDKs an adapter legitimately
  projects into. The import-level `FORBIDDEN_IN_CORE` denylist gains the same
  technologies ([#282]).
- RFC 0007 states the open question behind D2: what version of the core an
  adapter may accept, and what version `develop` carries between releases.
  Installing one locally built adapter wheel today resolves `agnara` from
  PyPI, whose published `0.1.0a3` satisfies the unbounded requirement while
  lacking a rename `develop` made under that same version, so `agnara
  --version` raises `ImportError`. An exact pin was measured and does not
  fix it. The RFC records the options and their costs and decides nothing
  ([#280]).
- RFC 0006 proposes one compiled exposure lifecycle for HTTP, MCP and future
  adapters. Project composition owns typed declarations; adapters retain their
  protocol-specific runtime artifacts while emitting neutral immutable records
  into a project-wide availability registry. Discovery, publication and
  authorization remain independent decisions ([#271]).
- The 41 top-level `agnara` exports now have an explicit provisional
  classification and an exact machine-readable snapshot. Release readiness
  detects additions, removals, renames, reordered exports, duplicate entries
  and unknown stability labels instead of treating the presence of `__all__`
  as sufficient. The accompanying policy defines pre-1.0 change and future
  stable deprecation expectations ([#270]).
- Generated modular apps expose transport-neutral types and Protocols through
  the explicit `application.contracts` module, and generated projects include
  a static architecture test that allows only that target across apps. Direct
  handler imports remain forbidden because they bypass runtime policy and
  internal capability invocation is still an I8 research decision ([#266]).
- `agnara app-api`, `agnara app-mcp`, `agnara app-agent` and `agnara
  app-worker` are shorthands for `agnara app create --profile <name>`. They
  are the same command with the profile fixed, not a second implementation:
  they accept every other option unchanged, share every refusal, and produce
  byte-identical projects. An alias does not accept `--profile`, since it is
  one ([#250]).
- `agnara app create --profile api` starts an app from a named set of
  exposures: `core`, `api`, `mcp`, `agentic`, `worker` and `full`, mapped as
  `docs/CLI_SPEC.md` specifies, defaulting to `core`. A profile is scaffolding
  only — it resolves to exposures and is never recorded, so `--profile
  agentic` and `--with mcp,a2a` produce identical projects. `--with` adds to a
  profile rather than replacing it ([#248]).
- `agnara app create --with http,mcp` selects which inbound adapters are
  scaffolded, adding one `adapters/inbound/<exposure>.py` each and nothing
  else. The exposure vocabulary is validated, repeats are dropped and the
  order given is preserved. A generated adapter imports only its own app's
  application layer and lists the capabilities it projects in `EXPOSED`: no
  Agnara adapter distribution is published to PyPI and a generated project
  depends on `agnara` alone, so importing one would produce a project that
  cannot be installed. The `minimal` architecture refuses an exposure, because
  it has no adapters package ([#246]).
- `agnara app create --architecture` selects the layout to generate, falling
  back to the project's `[defaults] architecture` in `agnara.toml`. The
  `minimal` architecture is implemented: a package, `module.py`,
  `capabilities.py` and a test, with none of the domain, application or
  adapters packages. It declares the same capabilities as the default template
  and holds their data in the module rather than behind a port, so the choice
  between the two templates is one difference rather than two unrelated
  examples. An architecture that is reserved but has no generator, such as
  `vertical`, is refused with the available alternatives instead of silently
  producing a different layout ([#244]).

### Added

- The introspection snapshot names the bounded contexts an application
  mounts. `ApplicationDescriptor.apps` carries a `BoundedContextDescriptor`
  per app, and `DiscoveryField.APPS` decides whether they are published. An
  app's module is deliberately not projected, because it is source layout
  ([#261]).
- `Agnara.include` refuses a second app claiming a name already mounted,
  raising the new `DuplicateAppError` rather than reporting a capability
  clash. Two apps sharing a name but declaring different capabilities were
  previously accepted silently. `Agnara.apps` exposes the mounted apps as a
  read-only view ([#257]).
- `App` and `AppDescriptor` give a bounded context a runtime identity, and
  `Agnara.include(app)` mounts one on a project. A capability declared on an
  app is namespaced by the app, so it is `payments.get_record` rather than
  `<project>.get_record`, and two apps generated by the scaffolder now compose
  in one project instead of colliding. Declaration is separate from mounting,
  so an app can be imported and tested without a project. `Agnara.capability`
  is unchanged ([#254]).

### Changed

- `agnara app create` generates a `module.py` that declares an `App` and
  mounts it with `app.include(...)`, so generated capability ids are
  `<app>.<name>` rather than `<project>.<name>` ([#254]).
- The generators are now pinned by a golden record of what they produce, and
  the dependency-direction rules for a generated app derive their file set
  from the generated tree instead of a hardcoded list, so they cover both
  architectures and an app with inbound adapters. Generated projects are also
  asserted to use `
` line endings and POSIX paths on every platform. Four
  superseded direction tests are removed rather than duplicated ([#252]).

### Fixed

- Generated apps now use package-relative imports and wrap docstring openings,
  comments and composition examples whose width depends on project or app
  names, so long identifiers pass both Ruff lint and format checks under the
  generated project's configuration ([#255]).
- `agnara app create` wrote `exposures = []` into every `[apps.<name>]` table
  regardless of what was requested, so `agnara apps` reported no exposures for
  an app that had inbound adapters. The resolved exposures are now recorded
  ([#246]).
- `agnara app create` recorded the project's default architecture in the new
  `[apps.<name>]` table while always generating the modular-hexagonal tree. A
  project whose `[defaults] architecture` was `minimal` therefore produced a
  manifest entry its own directory contradicted, and `agnara apps` reported the
  declared value. The declaration and the generated layout now come from one
  resolved decision ([#244]).

## [0.1.0a3] - 2026-09-06

Integration alpha. Only `agnara` is published to PyPI; all seven workspace
distributions share `0.1.0a3`. Adapter functionality below is available from
the repository. This remains experimental and is not production-ready.

### Fixed

- Release readiness accepts a populated, dated target changelog section after
  the release cut, checking synchronized target versions and comparison links.
  A historical release section cannot satisfy a new target ([#237]).

- Telemetry events now report a tracking ID supplied through
  `ExecutionContext(tracking_id=...)`, not only one found in
  `Invocation.metadata`. `agnara-mcp` sets that parameter from the JSON-RPC
  request id, so MCP tool calls previously produced lifecycle events carrying
  `None`. The explicit parameter takes precedence over metadata, and a
  non-string metadata value is dropped rather than stringified into a
  telemetry field. Adapters still export no tracking ID ([#221]).
- Removed unreachable code at the end of `agnara.execution.runtime.invoke`.
  Four statements followed a `try` block whose every branch returned, so they
  could never execute; this is a readability correction with no behavior
  change ([#219]).
- Explorer error responses now prevent storage with `private, no-store` and
  include the same security headers as its pages, preserving authentication
  challenges and method information ([#208]).
- Execution plans now reject missing, non-callable, coroutine and generator
  telemetry callbacks at startup. Direct construction also snapshots the
  hook collection, so later changes to the source list cannot change a
  compiled plan's observers ([#211]).

### Changed

- Enabled GitHub private vulnerability reporting and documented the private
  reporting channel for the experimental-alpha release ([#237]).

- `agnara project create` now reports what it wrote with the same renderer
  `--dry-run` uses, so a preview and a real run cannot describe the same plan
  differently ([#233]).
- An invocation whose compiled plan registers no telemetry hook no longer
  builds lifecycle events. Identity generation, tracking-ID resolution, clock
  reads and event construction are skipped when nothing can observe them,
  which measured roughly 2.9-4.4 microseconds per invocation on one
  workstation. A plan with hooks delivers exactly the same events as before
  ([#227]).
- Capability spans whose outcome is `failure` or `timeout` now also carry the
  stable OpenTelemetry `error.type` attribute, valued with that same outcome
  word. It is not an exception type: exception text is still never exported. A
  `cancellation` carries none. Metric attributes are unchanged, and the GenAI
  and MCP vocabularies are deliberately not emitted ([#225]).
- **Breaking (pre-1.0).** `InvocationStartEvent` and `InvocationTerminalEvent`
  now carry a required `invocation_id` that the execution runtime generates
  once per invocation and repeats on the terminal event. It is the supported
  way to pair the two events: a caller `tracking_id` is optional, repeatable
  and caller-controlled, so it was never a safe key. The field is appended to
  each event, so code constructing one positionally fails with a missing
  argument rather than binding a value to the wrong field; supply the identity
  or construct by keyword. Hooks that only read events are unaffected ([#219]).

### Added

- Added an evidence-based release readiness program:
  `docs/releases/RELEASE_PLAN.md` defines the path from `0.1.0a2` to `0.1.0`,
  `docs/releases/release-status.json` records the
  current state, and `uv run python scripts/check_release_readiness.py`
  evaluates it. Automated gates are recomputed from the repository, evidence
  expires when its commit is no longer `HEAD`, and gates needing human
  judgment are never satisfied by the tool. It supplements `QUALITY_GATES.md`
  and relaxes nothing ([#235]).

- Added `agnara app create`, which generates a bounded context in the
  modular-hexagonal layout and declares it in `agnara.toml`. The manifest is
  appended to, so its comments and ordering survive; an already-declared app,
  an invalid manifest and a missing one are refused before anything is written.
  The generated app runs: its capabilities register, compile and invoke against
  the generated outbound adapter. It does not edit `bootstrap.py`, and prints
  the lines to add instead ([#233]).

- Added `agnara project create`, the first generator. It writes a composition
  root, a manifest, a package layout and tests, from a plan built before
  anything is written: `--dry-run` and `--json` render that same plan, a run
  that would replace an existing file refuses before writing anything and names
  every conflict, `--overwrite` authorizes replacement for one run, and the
  command never prompts. Output is byte-identical for identical inputs. The
  generated project depends on `agnara` alone ([#231]).

- Added the `agnara.toml` project manifest format and its reader. `agnara apps`
  lists the apps a project declares with their architecture and exposures, as
  text or deterministic JSON, without importing any project module.
  `agnara_cli` exports `ProjectManifest`, `ManifestApp`, `ManifestError`,
  `parse_manifest`, `load_manifest` and `find_manifest`. Unknown tables and
  keys are rejected rather than ignored, and an app path may not be absolute or
  escape the project directory. No new dependency: parsing uses `tomllib`
  ([#229]).

- Added `OpenTelemetryTracingHook` in `agnara-telemetry`, which opens one span
  per capability invocation over an application-supplied tracer and ends it on
  the matching terminal event. A nested invocation becomes a child span, while
  invocations in sibling tasks stay unrelated. Only the capability identity and
  a closed outcome vocabulary are recorded; provider, processor, exporter,
  flush and shutdown remain owned by the application ([#219]).

- Authorized the Anthropic Claude agent identity for Git attribution.
  `.github/ai-agent-identities.toml` now registers `claude[bot]`, and AGENTS.md
  states the exact `Co-authored-by: Claude <noreply@anthropic.com>` trailer, so
  the registry covers every agent that has contributed to this repository
  ([#219]).

- Added `OpenTelemetryMetricsHook` in `agnara-telemetry` for terminal invocation
  counts and duration, using an application-supplied meter. The adapter depends
  on the OpenTelemetry API; SDK/exporter setup and shutdown remain owned by
  the application ([#216]).

- Added a main content landmark to every Explorer page and required Chromium
  checks for accessible structure, keyboard navigation, direct links and
  representative mobile rendering ([#209]).

- Added Explorer application, schema and dependency views: navigation is
  project → application → capability, an input's JSON Schema renders as bounded
  nested structure rather than escaped JSON, and each view disappears when its
  field is withheld ([#206]).
- Added the read-only Agnara Explorer: server-rendered HTML over the same
  filtered snapshot, visibility decision and principal resolver the discovery
  endpoint uses, with no JavaScript, stylesheet or external asset, deep links
  on capability identifiers, non-HTTP transport availability, and one `404` for
  both a hidden and an absent capability ([#204]).
- Added executable validation of the architecture metadata and of
  cross-surface snapshot consistency: `ARCHITECTURE.md`'s concept list is
  checked against the model, no descriptor field can be published without a
  named decision, and six surfaces are asserted to describe one application the
  same way for one viewer ([#202]).
- Added `agnara context`, which renders the filtered snapshot as Markdown for a
  model to read. It states in every rendering that seeing a capability is not
  permission to invoke it, and names a withheld field instead of printing its
  declared default ([#200]).
- Added `agnara schema openapi`, which exports the OpenAPI document a
  composition produced rather than projecting a second one. Serialized bytes
  are emitted unchanged, so an export is byte-identical to what an HTTP surface
  serves; `--output` writes a file non-destructively ([#198]).
- Added the authorized HTTP discovery endpoint, serving the same versioned
  introspection document `agnara inspect --json` produces. It takes a principal
  resolver, answers `401` unless anonymous discovery is opted into explicitly,
  filters per request before serialization, and refuses a shared-cacheable
  directive because the document is viewer-specific ([#196]).
- Added `agnara graph`, which draws capability, dependency and provider
  relationships from the same filtered snapshot `agnara inspect` reads. Every
  introspection command now obtains its data from one shared view, so no
  command has a second discovery path ([#194]).
- Added the `agnara` command and `agnara inspect`, which imports a compiled
  application named as `module:attribute` and presents its filtered
  introspection snapshot as text or deterministic JSON. Both modes build one
  snapshot and apply one visibility decision, chosen on the command line
  ([#192]).
- Added discovery visibility and redaction: `filter_snapshot` decides which
  capabilities a principal may discover and which fields are published, as two
  separate decisions with no default publication set, and marks its result so
  an unfiltered snapshot cannot be served by mistake ([#190]).
- Added the protocol-neutral introspection snapshot in `agnara.introspection`:
  frozen descriptors for apps, capabilities, inputs, dependencies, providers,
  policies and adapter-contributed exposures, built from a compiled
  application, with a versioned JSON data form and no path from a snapshot to
  a runtime object ([#188]).
- Added a comparative MCP tool-invocation benchmark against the pinned SDK's
  `MCPServer`, measuring the handler and official-client boundaries separately
  and reporting synchronous and asynchronous tools apart, with the baseline
  recorded in `docs/benchmarks/mcp-tool-invocation.md` ([#186]).
- Added the MCP tool invocation dispatcher: `McpToolInvoker` and
  `build_mcp_server` serve `tools/call` over the same frozen discovery
  snapshot, enforcing each capability's declared scopes with core's
  `ScopePolicy` before any effect, projecting canonical outcomes as tool
  results, refusing task-augmented and resumed calls as protocol errors, and
  propagating cancellation instead of answering it ([#185]).
- Added `project_mcp_result` for detached JSON success content, canonical tool
  errors without internal details and existing interaction-required projection,
  with explicit rejection of unsupported output values ([#183]).
- Added bounded MCP SDK conformance coverage for discovery, malformed
  pagination, unsupported calls and concurrent request identity/cache isolation,
  with an explicit coverage matrix and exclusions ([#181]).

## [0.1.0a2] - 2026-09-04

First release actually published to PyPI. Same source surface as the tagged
`0.1.0a1`; this version exists because the `0.1.0a1` release run never reached
the publish job and a tag is never moved or reused.

Published to PyPI: `agnara` only. `agnara-http`, `agnara-mcp`, `agnara-cli`,
`agnara-a2a`, `agnara-events` and `agnara-telemetry` share the version but are
not uploaded, so the HTTP, OpenAPI, MCP and CLI surfaces are reachable from a
repository checkout rather than from `pip install agnara`.

### Fixed

- Made the release pipeline's out-of-workspace smoke test deterministic. It
  drove `uv venv` without an interpreter request, so the runner's CPython 3.12
  was selected and the `requires-python >= 3.14` wheel could not be installed,
  failing `Validate built artifacts` before anything could be published. The
  step now creates the environment with an explicit `--python 3.14`, installs
  and runs through that environment's interpreter instead of `uv run`, requires
  exactly one wheel in `dist/`, and asserts the interpreter version, the
  version reported by the installed distribution and that `agnara` resolved
  from `site-packages` rather than from the checkout. The post-publish
  verification step was made deterministic the same way, since a failure there
  would prevent the GitHub Release from being created.

## [0.1.0a1] - 2026-09-04

First public alpha: an architectural proof that Agnara installs and runs as a
real Python distribution. The public API is unstable and this release is not
production-ready.

Tagged but never published. The release run for `v0.1.0a1` failed in
`Validate built artifacts`, so no distribution was uploaded to PyPI and the
GitHub Release was never created. Everything recorded below shipped to PyPI
under `0.1.0a2` instead.

### Added

- Defined the MCP Task and multi-round-trip boundary: MRTR as the only
  resumption mechanism on the pinned revision, the Tasks extension neither
  implemented nor advertised, explicit request-state boundary installation
  on the lowlevel server tier, and confirmation evidence kept separate from
  client-echoed round state (ADR 0042).
- Added deterministic projection of canonical interaction-required
  confirmation outcomes to official MCP `InputRequiredResult` form
  elicitations, with strict canonical-detail validation, minimal safe
  serialization and explicit separation from evidence verification and MRTR
  resumption ([#172]).
- Added a request-scoped MCP authorization bridge from official SDK verified
  identity context to protocol-neutral principals, with credential-free
  explicit identity mapping, fail-closed redacted errors, isolated static
  scope filtering, and private immediately stale discovery results ([#170]).
- Added an official SDK MCP discovery boundary for frozen projected tools,
  including pinned `server/discover` capability advertisement, deterministic
  detached `tools/list` results, conservative private cache hints, and explicit
  invalid-cursor handling ([#168]).
- Added projection from compiled capability inputs to official MCP SDK `Tool`
  definitions, with closed object schemas, protected-parameter exclusion,
  deterministic required fields, detached JSON-safe schema data, and ignored
  isolated pytest basetemp directories used by repository verification
  ([#166]).
- Added deterministic MCP tool exposure registration through
  `Mcp(app).tool(capability)`, including explicit wire-name overrides,
  startup collision checks, capability ownership validation, and immutable
  compiled snapshots ([#164]).
- Pinned the first MCP adapter baseline to specification `2026-07-28` and the
  official Python SDK `2.1.1`, with an adapter-owned version contract,
  dependency-boundary tests and explicit deferral of unfinished protocol and
  conformance surfaces ([#162]).
- Added a reproducible in-process ASGI benchmark comparing Agnara HTTP with a
  direct reference, Starlette 1.6.0, FastAPI 0.141.1 and Litestar 2.24.0 using
  deterministic rotating samples, correctness checks, raw/environment/version
  evidence and no CI timing threshold; ADR 0041 retains the dependency-free
  direct ASGI boundary ([#159]).
- Enforced the documentation asset policy with immutable exact-version remote
  resource metadata, SHA-384 SRI and anonymous-CORS validation, exact HTML/CSP
  correspondence, canonical deployment origin allowlists, and repository-wide
  vendored hash/license/packaging checks; pinned local assets and no UI remain
  zero-network baselines ([#157]).
- Added a required Playwright 1.62.0/Chromium documentation-browser gate for
  Swagger UI, ReDoc and Scalar covering emitted CSP/security headers, XSS and
  undeclared-network blocking, mobile/keyboard smoke behavior, credential
  storage, disabled routes, OAuth redirect boundaries and per-UI try-it; no
  unconditional documentation default is selected ([#155]).
- Added pinned Scalar API Reference 1.67.0 local and opt-in CDN providers with
  verified licensed assets and SRI, explicit telemetry/plugin/agent/font
  boundaries, independently disabled try-it and documented partial OpenAPI
  3.2/accessibility support; the documentation default remains deferred until
  shared browser evidence exists ([#153]).
- Added pinned ReDoc CE 2.5.3 local and opt-in CDN documentation providers,
  including verified licensed assets, SRI, untrusted-spec sanitization and an
  explicit blob-worker CSP requirement; ReDoc truthfully refuses canonical
  OpenAPI 3.2 and try-it instead of silently degrading either ([#151]).
- Added pinned Swagger UI 5.32.14 documentation providers: the production
  baseline serves verified licensed assets locally, while a separate
  exact-version CDN provider requires explicit remote-asset permission and
  uses SRI; online validation, credential persistence and try-it are disabled
  by default, and known OpenAPI 3.2 gaps are declared ([#149]).
- Added an immutable HTTP publication plan where schema serving, each
  documentation UI, Explorer and per-UI try-it are selected independently;
  UIs without a schema endpoint receive document bytes instead of an
  unserved URL ([#147]).
- Added compiled HTTP surface routes for already-produced schema,
  documentation and Explorer artifacts: paths are explicit and static,
  compilation order is deterministic, collisions reserve the whole path
  against capability routes, and unmatched requests delegate unchanged to
  capability dispatch ([#145]).
- Added the replaceable documentation-provider contract: a provider receives
  an already-filtered OpenAPI document and never the compiled registry, must
  name the OpenAPI versions it was tested against and the features it does not
  support, becomes unavailable with a diagnostic rather than rendering a
  version it does not support, and needs both its own declaration and
  deployment permission before requiring an external origin ([#141]).
- Established a dependency-free internal ASGI 3 HTTP boundary that preserves
  raw adapter inputs and rejects unsupported protocols explicitly ([#107]).
- Added a deterministic two-phase HTTP route registry with fail-fast template
  collision detection and immutable compiled trie matching ([#109]).
- Added compiled explicit HTTP path/query/header/JSON-body binding with strict
  wire decoding, scalar conversion, bounded chunked bodies, and shared core
  schema validation ([#113]).
- Added deterministic non-streaming ASGI success responses with compact UTF-8
  JSON, dataclass and enum projection, correct `HEAD`/`204` behavior, and
  fail-before-start validation ([#115]).
- Added RFC 9457 failure responses with an exhaustive, reviewed
  `FailureCode`-to-status table, occurrence-independent problem titles,
  optional compiled problem-type URIs, collision-free nested failure details,
  `internal_failure` redaction, and a prebuilt last-resort internal problem
  response ([#117]).
- Added transport-level RFC 9457 problems for failures that precede a
  capability: classified binding failures, `404`, `405` with a required
  `Allow` header, `413` and `415`, sharing one problem-type namespace with
  capability failures ([#129]).
- Added compiled HTTP exposures and the end-to-end request path: startup
  validation and an immutable route-to-plan registry, then match, bind,
  invoke and serialize, with `HEAD` served from `GET`, `root_path` stripping,
  no response on a client disconnect, and a query-free problem `instance`
  ([#131]).
- Added dependency-free deterministic OpenAPI 3.2 projection from explicitly
  publishable compiled HTTP exposures, reusing compiled input schemas and
  filtering hidden operations before document assembly ([#135]).
- Added structured execution telemetry hooks (E4.8).
- Defined Policy, PolicyResult interface and added policies tuple to CapabilityDefinition.
- Defined Principal and AnonymousPrincipal for policy evaluation.
- Added immutable granted scopes to principals and a transport-neutral
  `ScopePolicy` for deterministic all-required-scope evaluation ([#90]).
- Defined the protocol-neutral confirmation boundary: verified evidence,
  interaction-required outcomes, replay binding, and pre-handler enforcement
  sequencing ([#94]).
- Implemented verifier-backed confirmation policies, immutable interaction
  requests, explicit evidence on execution contexts, and pre-handler canonical
  outcome mapping ([#96]).
- Defined protocol-neutral delegation semantics with explicit actor/subject
  separation, monotonic authority attenuation, bounded verified chains and
  confirmation binding ([#101]).
- Python 3.14 workspace with seven explicit package boundaries and
  cross-platform quality gates.
- Protocol-neutral `CapabilityId` and `CapabilityDefinition` value types with
  effects, risk, confirmation and idempotency metadata.
- Issue/branch/PR/review governance, branch rulesets and evidence-based
  AI-agent attribution.
- Synchronized pre-1.0 package versioning and a curated changelog/release
  workflow ([#16]).
- Capability-first architecture for generated OpenAPI, replaceable HTTP
  documentation providers and protocol-neutral Agnara Explorer introspection.
- `Agnara` composition root and the `@app.capability` decorator, usable bare
  or with metadata. Ids default to `<app>.<function>` with an explicit
  override, descriptions default to the docstring summary, and the
  decorated function is returned unchanged ([#21]).
- `scopes` on `CapabilityDefinition`, declarative permission labels a
  policy engine may require ([#21]).
- Schema port: `SchemaAdapter` and `TypeSchema` protocols, a JSON Schema
  export contract, and `StandardSchemaAdapter`, a strict standard-library
  reference implementation covering primitives ([#27]).
- `SchemaError` and `ValidationError`, the latter carrying a path to the
  offending value so adapters can render it per protocol ([#27]).
- Recursive standard-library schemas for typed lists, string-keyed
  dictionaries, fixed and variadic tuples, unions, literals and enums, with
  strict nested validation and deterministic JSON Schema fragments ([#30]).
- Strict dataclass instance schemas with recursively compiled fields,
  deterministic nested validation paths, default-aware required properties
  and compile-time diagnostics for unsupported directional or recursive
  forms ([#32]).
- An isolated, executable msgspec schema-adapter prototype covering strict
  conversion, JSON Schema generation and protocol-neutral error translation,
  with limitations recorded for the later adapter comparison ([#34]).
- An isolated, executable Pydantic schema-adapter prototype covering strict
  conversion, JSON Schema generation and protocol-neutral error translation,
  with limitations recorded for the later adapter comparison ([#38]).
- `CapabilityRegistry` and `FrozenCapabilityRegistry`: deterministic
  registration order, duplicate-id rejection, a freeze step that yields an
  immutable thread-safe view, lookup by id or dotted string, and
  introspection by namespace and declared effect ([#19]).
- Immutable `ExecutionPlan` startup compilation, which snapshots each
  capability's direct DI requirements after validating the complete provider
  graph ([#62]).
- Compiled protocol-neutral capability input schemas with deterministic
  required/unknown-input failures and validated values on the invocation path
  ([#111]).
- Transport-neutral direct invocation of compiled plans with explicit context
  injection, DI ownership, sync/async handlers and deterministic resource
  cleanup ([#65]).
- Optional monotonic invocation deadlines covering dependency resolution and
  handler execution, with timeout cleanup and remaining-time introspection
  ([#69]).
- Immutable protocol-neutral `Success`, `Failure`, and `FailureCode` outcomes,
  plus an `invoke_result` boundary that preserves direct-call ergonomics,
  redacts unexpected exceptions, and propagates cancellation ([#71]).

### Changed

- Contributors on the maintainer Windows workstation can now run the complete
  five-command quality gate locally. The `E0.13` record no longer claims that
  Ruff and `ty` are unrunnable there; CI stays the authoritative
  cross-platform record ([#120]).
- Direct invocation explicitly propagates task cancellation while cleaning up
  resources entered before cancellation, including during dependency
  construction ([#67]).
- Agent-assisted commits now resolve authorized public identities through a
  provider-neutral registry. Materially authored Codex changes use the
  verified `openai-codex[bot]` GitHub identity, while fixed global hooks and
  unverified identities remain forbidden ([#36]).
- `CapabilityDefinition.declare()` carries the authoring-shaped argument
  types, so the documented `effects={...}, risk="high"` calls typecheck
  without suppression while the attributes keep their narrow types ([#24]).

- Core frozen value types retain slots while using one internal construction
  rule for deterministic mutation failures.

### Fixed

- Pinned CPython 3.14 in every `release.yml` job and made a wrong
  interpreter fail loudly. The artifact-validation job built its clean-room
  environment on whatever Python the runner offered, so the first tagged run
  could not install its own `>=3.14` wheel, and the publish job's
  post-release check carried the same defect where it would have failed
  after upload.

- HTTP dispatch now strips `root_path` only at a complete mount-path segment,
  preventing a mount such as `/api` from capturing a textual prefix such as
  `/apiary` ([#133]).
- Every `CHANGELOG.md` reference link resolves again. Nine had lost or never
  received a definition and rendered as literal text; governance tests now
  reject an undefined reference, an unreferenced definition, a duplicate, and
  a definition whose URL does not match its own number ([#125]).
- Restored the em-dashes, arrows and box-drawing characters that a lossy
  cp1252 write had replaced with literal question marks across `README.md`,
  `BACKLOG.md`, `CONTRIBUTING.md`, one core module docstring and four test
  modules. Every diagram in the README is readable again, and a
  repository-integrity test now fails on reintroduction ([#123]).
- The multi-agent coordination CLI no longer aborts with `UnicodeEncodeError`
  on a narrow console codec. Output framing is ASCII, and GitHub-sourced
  titles, worker names and scopes degrade to replacement characters instead of
  killing the command ([#119]).
- Removed unresolved merge markers from the changelog and added a governance
  regression check that prevents their reintroduction ([#87]).
- Unknown assignment or deletion on frozen slotted core values now raises
  `FrozenInstanceError` instead of CPython 3.14's confusing internal
  `TypeError` ([#3]).

[#244]: https://github.com/Blandskron/agnara/issues/244
[#246]: https://github.com/Blandskron/agnara/issues/246
[#248]: https://github.com/Blandskron/agnara/issues/248
[#250]: https://github.com/Blandskron/agnara/issues/250
[#252]: https://github.com/Blandskron/agnara/issues/252
[#254]: https://github.com/Blandskron/agnara/issues/254
[#257]: https://github.com/Blandskron/agnara/issues/257
[#259]: https://github.com/Blandskron/agnara/issues/259
[#261]: https://github.com/Blandskron/agnara/issues/261
[Unreleased]: https://github.com/Blandskron/agnara/compare/v0.1.0a7...develop
[0.1.0a7]: https://github.com/Blandskron/agnara/compare/v0.1.0a6...v0.1.0a7
[0.1.0a6]: https://github.com/Blandskron/agnara/compare/v0.1.0a5...v0.1.0a6
[0.1.0a5]: https://github.com/Blandskron/agnara/compare/v0.1.0a4...v0.1.0a5
[0.1.0a4]: https://github.com/Blandskron/agnara/compare/v0.1.0a3...v0.1.0a4
[0.1.0a3]: https://github.com/Blandskron/agnara/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/Blandskron/agnara/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/Blandskron/agnara/releases/tag/v0.1.0a1
[#3]: https://github.com/Blandskron/agnara/issues/3
[#16]: https://github.com/Blandskron/agnara/issues/16
[#19]: https://github.com/Blandskron/agnara/issues/19
[#21]: https://github.com/Blandskron/agnara/issues/21
[#24]: https://github.com/Blandskron/agnara/issues/24
[#27]: https://github.com/Blandskron/agnara/issues/27
[#30]: https://github.com/Blandskron/agnara/issues/30
[#32]: https://github.com/Blandskron/agnara/issues/32
[#34]: https://github.com/Blandskron/agnara/issues/34
[#36]: https://github.com/Blandskron/agnara/issues/36
[#38]: https://github.com/Blandskron/agnara/issues/38
[#62]: https://github.com/Blandskron/agnara/issues/62
[#65]: https://github.com/Blandskron/agnara/issues/65
[#67]: https://github.com/Blandskron/agnara/issues/67
[#69]: https://github.com/Blandskron/agnara/issues/69
[#71]: https://github.com/Blandskron/agnara/issues/71
[#87]: https://github.com/Blandskron/agnara/issues/87
[#90]: https://github.com/Blandskron/agnara/issues/90
[#94]: https://github.com/Blandskron/agnara/issues/94
[#96]: https://github.com/Blandskron/agnara/issues/96
[#101]: https://github.com/Blandskron/agnara/issues/101
[#107]: https://github.com/Blandskron/agnara/issues/107
[#109]: https://github.com/Blandskron/agnara/issues/109
[#111]: https://github.com/Blandskron/agnara/issues/111
[#113]: https://github.com/Blandskron/agnara/issues/113
[#115]: https://github.com/Blandskron/agnara/issues/115
[#117]: https://github.com/Blandskron/agnara/issues/117
[#119]: https://github.com/Blandskron/agnara/issues/119
[#120]: https://github.com/Blandskron/agnara/issues/120
[#129]: https://github.com/Blandskron/agnara/issues/129
[#131]: https://github.com/Blandskron/agnara/issues/131
[#141]: https://github.com/Blandskron/agnara/issues/141
[#145]: https://github.com/Blandskron/agnara/issues/145
[#147]: https://github.com/Blandskron/agnara/issues/147
[#149]: https://github.com/Blandskron/agnara/issues/149
[#151]: https://github.com/Blandskron/agnara/issues/151
[#153]: https://github.com/Blandskron/agnara/issues/153
[#155]: https://github.com/Blandskron/agnara/issues/155
[#157]: https://github.com/Blandskron/agnara/issues/157
[#159]: https://github.com/Blandskron/agnara/issues/159
[#162]: https://github.com/Blandskron/agnara/issues/162
[#164]: https://github.com/Blandskron/agnara/issues/164
[#166]: https://github.com/Blandskron/agnara/issues/166
[#168]: https://github.com/Blandskron/agnara/issues/168
[#170]: https://github.com/Blandskron/agnara/issues/170
[#172]: https://github.com/Blandskron/agnara/issues/172
[#123]: https://github.com/Blandskron/agnara/issues/123
[#125]: https://github.com/Blandskron/agnara/issues/125
[#133]: https://github.com/Blandskron/agnara/issues/133
[#135]: https://github.com/Blandskron/agnara/issues/135
[#181]: https://github.com/Blandskron/agnara/issues/181
[#183]: https://github.com/Blandskron/agnara/issues/183
[#185]: https://github.com/Blandskron/agnara/issues/185
[#186]: https://github.com/Blandskron/agnara/issues/186
[#188]: https://github.com/Blandskron/agnara/issues/188
[#190]: https://github.com/Blandskron/agnara/issues/190
[#192]: https://github.com/Blandskron/agnara/issues/192
[#194]: https://github.com/Blandskron/agnara/issues/194
[#196]: https://github.com/Blandskron/agnara/issues/196
[#198]: https://github.com/Blandskron/agnara/issues/198
[#200]: https://github.com/Blandskron/agnara/issues/200
[#202]: https://github.com/Blandskron/agnara/issues/202
[#204]: https://github.com/Blandskron/agnara/issues/204
[#206]: https://github.com/Blandskron/agnara/issues/206
[#208]: https://github.com/Blandskron/agnara/issues/208
[#209]: https://github.com/Blandskron/agnara/issues/209
[#211]: https://github.com/Blandskron/agnara/issues/211
[#216]: https://github.com/Blandskron/agnara/issues/216
[#219]: https://github.com/Blandskron/agnara/issues/219
[#221]: https://github.com/Blandskron/agnara/issues/221
[#225]: https://github.com/Blandskron/agnara/issues/225
[#227]: https://github.com/Blandskron/agnara/issues/227
[#229]: https://github.com/Blandskron/agnara/issues/229
[#231]: https://github.com/Blandskron/agnara/issues/231
[#233]: https://github.com/Blandskron/agnara/issues/233
[#235]: https://github.com/Blandskron/agnara/issues/235

[#237]: https://github.com/Blandskron/agnara/issues/237
[#255]: https://github.com/Blandskron/agnara/issues/255
[#266]: https://github.com/Blandskron/agnara/issues/266
[#268]: https://github.com/Blandskron/agnara/issues/268
[#270]: https://github.com/Blandskron/agnara/issues/270
[#271]: https://github.com/Blandskron/agnara/issues/271
[#275]: https://github.com/Blandskron/agnara/issues/275
[#278]: https://github.com/Blandskron/agnara/issues/278
[#280]: https://github.com/Blandskron/agnara/issues/280
[#282]: https://github.com/Blandskron/agnara/issues/282
[#286]: https://github.com/Blandskron/agnara/issues/286
[#309]: https://github.com/Blandskron/agnara/issues/309
[#308]: https://github.com/Blandskron/agnara/issues/308
[#293]: https://github.com/Blandskron/agnara/issues/293
[#288]: https://github.com/Blandskron/agnara/issues/288
[#289]: https://github.com/Blandskron/agnara/issues/289
[#296]: https://github.com/Blandskron/agnara/issues/296
[#291]: https://github.com/Blandskron/agnara/issues/291
[#313]: https://github.com/Blandskron/agnara/issues/313
[#307]: https://github.com/Blandskron/agnara/issues/307
[#341]: https://github.com/Blandskron/agnara/issues/341
[#344]: https://github.com/Blandskron/agnara/issues/344

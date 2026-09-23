# Security

## Security philosophy

Agnara treats security as part of the capability execution model, not as transport middleware alone.

## Reporting vulnerabilities

Report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/Blandskron/agnara/security/advisories/new).
A 2026-09-20 GitHub API readback confirmed the channel is enabled for this
repository. That observes the setting at one point in time; it is not a
response-time commitment, and it must be re-read during release preflight.

Do not request vulnerability details through public issues.

## Threat model

`docs/THREAT_MODEL.md` is the current threat-boundary analysis for the
`1.0.0` candidate. It covers direct capability execution, HTTP/ASGI and SSE,
MCP, embedded and side-by-side hosts, schema and persistence seams,
idempotency, nested composition, telemetry, the local CLI and release
publication. It separates controls proved by this repository from deployment
and application responsibilities.

It is evidence for the I10 release gate, not a production-security
certification. Read its residual risks and unverified deployment assumptions
before citing it. In particular, Agnara does not provide a general HTTP
authentication product, a durable idempotency store, a telemetry exporter or
application-policy review.

## Security boundaries

Agnara must explicitly distinguish:

- authentication;
- authorization;
- delegation;
- capability risk metadata;
- human confirmation;
- transport security;
- application business invariants.

No single decorator should claim to solve all of these.

### What the kernel accepts as an identity

Agnara authenticates nobody. A composition root — an adapter, an embedding
host, or a direct caller — verifies a credential and hands the kernel the
result. That result is a `Principal`, and it is the entire vocabulary:

| Field | Meaning | Rule |
| --- | --- | --- |
| `identity` | Stable non-empty string naming the verified actor | Compared, never parsed for authority |
| `scopes` | The permission labels the verifier granted | The only grant channel |
| `metadata` | Opaque facts a policy may read | Never authority by itself |

Four consequences follow, and each is enforced rather than advised:

- **Credentials stay outside.** `principal` must be a `Principal`. A raw JWT,
  claims mapping, access token or framework session object is refused at
  construction even when it is duck-type compatible with scope evaluation.
  Credential material therefore never needs to reach a handler or telemetry.
- **Scopes are the only grant.** Nothing in `metadata` grants authority, under
  any name — `scopes`, `scp`, `roles`, `permissions` or otherwise.
- **Authority is fixed for the execution.** `principal`,
  `confirmation_evidence` and `idempotency` cannot be reassigned once an
  execution exists. A running capability is not its own authorization
  authority.
- **Absence fails closed.** No verified identity resolves to
  `AnonymousPrincipal`, which holds no scopes, so every scoped capability
  refuses it. A capability that declares no scope declares no requirement and
  is not treated as secret.

There is no `subject`, actor/subject split, grant chain or attenuation to
configure. RFC 0005 delegation is Draft and deliberately unimplemented, so a
nested child receives a detached copy of the caller's own actor and its own
policies are re-evaluated against it. Invocation metadata naming a subject or
a delegation is inert data, never verified authority.

`tests/security/test_authority_boundary.py` holds the regression evidence,
including the confused-deputy case where a caller may run a privileged parent
but lacks the child's scope.

## Default posture

- deny when a required policy cannot be evaluated;
- fail closed on authorization errors;
- never log secrets by default;
- never include raw credentials in traces;
- explicit opt-in for dangerous debug payload capture;
- deterministic policy ordering;
- security-sensitive startup misconfiguration fails fast.

## Agent-specific threats

Threat model must include:

- confused deputy;
- over-broad delegated authority;
- prompt/tool injection crossing trust boundaries;
- tool name/schema spoofing;
- automated destructive invocation;
- replay of non-idempotent operations;
- cross-tenant context leakage;
- malicious metadata;
- unbounded tool recursion;
- approval bypass;
- SSRF through generic HTTP capabilities.

Agnara cannot prevent all application-level agent attacks, but its APIs should make safe composition possible.

## Supply chain

Core should minimize dependencies.

All protocol adapters should pin or bound critical protocol dependencies and record supported versions.

### Repository controls and alert triage

GitHub secret scanning, push protection, Dependabot alerts and Dependabot
security updates are enabled for this repository. Read back repository
settings during release preflight; their state is external to Git history.
`docs/releases/release-status.json` names the optional controls that remain
unavailable or disabled. Dependency update PRs follow the normal review and required-check
workflow and are never automatically merged by this configuration.

Required CI analyzes Python and GitHub Actions using SHA-pinned CodeQL
actions. Only the analysis job receives `security-events: write`; it does not
receive publication credentials or execute an application build. Its result
is uploaded to GitHub code scanning. Successful analysis means the tool ran,
not that every alert is resolved. Review open alerts and their analyzed commit
before release; record fixes or justified dispositions privately where the
finding is exploitable. Do not close or suppress alerts merely to get green CI.

The locked runtime audit is a release gate rather than an instruction. The
`dependency-audit` job runs before anything is built, and `build` depends on
it, so a release cannot reach the human approval step with the audit
unperformed:

```powershell
uv export --locked --all-packages --no-dev --no-emit-workspace `
  --no-hashes --format requirements.txt --output-file runtime-requirements.txt
uvx --from pip-audit==2.10.1 pip-audit `
  -r runtime-requirements.txt --strict --format json --output pip-audit.json
```

It audits the locked *runtime* graph. The development group -- test, fixture
and tooling packages -- is excluded because no consumer installs it; a
vulnerability there is a contributor concern, not a shipped one.

A zero-result audit is evidence only for the vulnerability database and
lockfile observed at execution time, so it expires: dependency alerts on the
default branch do not prove that an unreleased `develop` lockfile is clean.
Record the result against the candidate SHA in
`docs/releases/release-status.json`. Secret-scanning alerts must be handled in the private security UI;
never copy credential values into Issues, PRs or build logs.

### Artifact inventory and provenance

Three mechanisms cover three different questions, and none of them answers
another's:

| Question | Mechanism | Where |
| --- | --- | --- |
| What is in the candidate? | CycloneDX 1.6 SBOM | `scripts/generate_sbom.py`, published as the `agnara-sbom` artifact |
| Are these the bytes that were built? | SHA-256 digest chain | `SHA256SUMS`, re-checked by every job that touches the bundle |
| Who built and published them? | PEP 740 attestations | `pypa/gh-action-pypi-publish` under the workflow's OIDC identity |

The SBOM describes the seven built files with their real digests plus the
locked runtime graph -- not the environment that happened to produce it, which
is the usual way an SBOM becomes decorative. It is deterministic: the
timestamp comes from the release commit through `SOURCE_DATE_EPOCH` and the
serial number is derived from the document's content, so two SBOMs of
identical inputs are byte-identical and a difference between them means
something. `scripts/check_sbom.py` verifies the document against the built
files independently of the generator.

Signing is not implemented here and is not invented here. Attestations are
produced by the ecosystem's own mechanism, keyless through Sigstore, using the
short-lived OIDC identity the publishing job presents. Agnara holds no signing
key, and no key or token belongs in this repository or in a build log.

### Verifying Trusted Publishing at the real release

Publication runs in protected environments, so parts of this can only be
confirmed during an authorized release. Before approving one, and again after
it completes:

1. **Before dispatch.** `scripts/check_release_preconditions.py` refuses to
   proceed unless the protected environment exists and the recorded Trusted
   Publisher tuple matches the identity this workflow will present. The
   `publish-preflight` job then reads the public index to confirm that earlier
   phases are complete at this version and that this phase's projects carry no
   file of it -- the state `skip-existing: true` would have concealed.
2. **At the approval gate.** Confirm in the environment's own settings that
   the required reviewers are the intended people, and that the job requesting
   approval is the phase you meant to authorize.
3. **After each phase.** The `verify-bootstrap-*` and `verify-published` jobs
   read the index back. Additionally confirm on PyPI that each uploaded file
   carries its attestation and that the publisher shown is this repository's
   workflow, not a token.

None of step 3 can be established by inspecting this repository. Until an
authorized release runs, the live publisher configuration is `NEEDS CI` and is
recorded that way rather than assumed.

## Documentation and discovery surfaces

OpenAPI, capability introspection and human documentation UIs are publication
surfaces, not harmless development decoration.

Implementations must:

- apply visibility, redaction and authorization before serialization;
- keep schema access, human UI access and interactive invocation independently
  configurable;
- exclude private capabilities, secrets, credential examples, runtime
  dependency values and sensitive policy internals by default;
- treat descriptions, examples and external references as untrusted input;
- send try-it requests through the normal authentication, policy,
  confirmation and execution path;
- never embed OAuth client secrets or persistent credentials in generated
  browser content;
- prefer pinned self-hosted assets and require explicit opt-in for CDNs;
- document and test CSP, XSS, framing, cache, referrer and outbound network
  behavior for every supported UI provider.

Hiding an operation in Swagger UI, ReDoc, Agnara Explorer or any other
navigation surface is not authorization.

See RFC 0003 and ADR 0018.

## Security claims

Do not use phrases such as "secure by default" in release marketing unless behavior is documented precisely.

Prefer:

> "Agnara provides security-aware capability metadata and enforceable policy hooks."

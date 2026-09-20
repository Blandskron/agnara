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

For dependencies, re-run the locked runtime audit on the final candidate:

```powershell
uv export --locked --all-packages --no-dev --no-emit-workspace `
  --no-hashes --format requirements.txt --output-file runtime-requirements.txt
uvx --from pip-audit==2.10.1 pip-audit `
  -r runtime-requirements.txt --format json --output pip-audit.json
```

Run it from the exact release commit, after the version and changelog cut and
before tagging. A zero-result audit is evidence only for the vulnerability
database and lockfile observed at execution time, so it expires: dependency
alerts on the default branch do not prove that an unreleased `develop`
lockfile is clean. Record the result against the candidate SHA in
`docs/releases/release-status.json`. Secret-scanning alerts must be handled in the private security UI;
never copy credential values into Issues, PRs or build logs.

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

# Security

## Security philosophy

Agnara treats security as part of the capability execution model, not as transport middleware alone.

## Reporting vulnerabilities

Report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/Blandskron/agnara/security/advisories/new).
The channel was enabled and verified for the `0.1.0a3` release preparation.

Do not request vulnerability details through public issues.

## Threat model

`docs/THREAT_MODEL.md` records the analysis for the surface `0.1.0a4`
publishes: assets, trust boundaries, attacker-controlled inputs, the
protections each of which names the test that proves it, the findings this
audit produced, and the assumptions delegated to ASGI servers, proxies and
applications.

It is scoped to a4 and is not the beta security program (`I10`). Read what it
says it did not do before citing it.

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
The a4 closure record names optional controls that remain unavailable or
disabled. Dependency update PRs follow the normal review and required-check
workflow and are never automatically merged by this configuration.

Required CI analyzes Python and GitHub Actions using SHA-pinned CodeQL
actions. Only the analysis job receives `security-events: write`; it does not
receive publication credentials or execute an application build. Its result
is uploaded to GitHub code scanning. Successful analysis means the tool ran,
not that every alert is resolved. Review open alerts and their analyzed commit
before release; record fixes or justified dispositions privately where the
finding is exploitable. Do not close or suppress alerts merely to get green CI.

For dependencies, repeat the locked runtime `pip-audit` procedure in
`the release closure document` on the final candidate. Dependency alerts
on the default branch do not prove that an unreleased `develop` lockfile is
clean. Secret-scanning alerts must be handled in the private security UI;
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

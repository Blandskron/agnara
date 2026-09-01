# Security

## Security philosophy

Agnara treats security as part of the capability execution model, not as transport middleware alone.

## Reporting vulnerabilities

Before public release, configure GitHub Security Advisories or another private reporting channel.

Do not request vulnerability details through public issues.

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

## Security claims

Do not use phrases such as "secure by default" in release marketing unless behavior is documented precisely.

Prefer:

> "Agnara provides security-aware capability metadata and enforceable policy hooks."

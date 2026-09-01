# ADR 0017 — Distribution and Import Names

- Status: Proposed

## Context

`ARCHITECTURE.md` section 3 names seven packages (`agnara-core`,
`agnara-http`, `agnara-mcp`, `agnara-a2a`, `agnara-events`,
`agnara-telemetry`, `agnara-cli`) but does not state the Python import
names that back those distributions.

The golden API in `docs/API_DESIGN.md` requires:

```python
from agnara import Agnara
```

That constrains the choice, because a package that exposes a name from its
own `__init__.py` cannot simultaneously be a PEP 420 implicit namespace
package shared by several distributions.

## Options considered

### A. PEP 420 namespace `agnara.*` for every distribution

`agnara-core` would ship `agnara/core/`, `agnara-http` would ship
`agnara/http/`, and so on, with no top-level `agnara/__init__.py`.

Rejected: it breaks the documented `from agnara import Agnara`, forcing
`from agnara.core import Agnara` instead. Namespace packages also make
import errors and editor tooling noticeably harder to reason about, which
conflicts with P16.

### B. `agnara-core` owns the regular package `agnara`; adapters use distinct top-level packages

```text
agnara-core       -> agnara
agnara-http       -> agnara_http
agnara-mcp        -> agnara_mcp
agnara-a2a        -> agnara_a2a
agnara-events     -> agnara_events
agnara-telemetry  -> agnara_telemetry
agnara-cli        -> agnara_cli
```

### C. A single distribution with optional extras

Rejected: it makes the dependency direction unenforceable at the packaging
level, which is precisely what ADR 0003 requires CI to enforce.

## Decision

Option B.

`agnara-core` ships the regular package `agnara`. Every adapter ships its
own top-level import package named after its distribution with underscores.

## Rationale

- preserves the documented golden API exactly;
- one distribution owns one import root, so architecture tests can map an
  import to a package boundary by its top-level name alone;
- adapters can be installed, versioned and released independently;
- no namespace-package failure modes.

## Consequences

- adapter imports read `import agnara_http`, not `import agnara.http`;
- `agnara-core` must never grow a submodule that an adapter is expected to
  provide, because the import root is not shared;
- if a shared namespace later becomes clearly better, migrating requires a
  superseding ADR and a deprecation path, since import paths are public API.

## Reversibility

Moderate. Re-exporting adapters under an `agnara.*` namespace later is
possible, but removing the top-level names afterwards would be a breaking
change.

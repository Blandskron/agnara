# ADR 0096 — Read-only static CLI doctor

- Status: Proposed
- Tracking: GitHub Issue #672
- Related: ADR 0059, ADR 0076

## Context

The CLI specification lists project diagnostics, including manifest/runtime
divergence, graph cycles and protocol configuration. Checking those by
importing a bootstrap module can construct resources or run application code.
Manifest intent and installed package metadata cannot prove runtime health.

## Decision

The first implemented boundary is `agnara doctor [--project DIR] [--json]`.
It searches the selected directory and ancestors like `agnara apps`, reads
the existing strict manifest and performs only these checks:

- the executing interpreter meets Python >=3.14;
- the manifest is present, readable and valid;
- declared app directories exist inside the project after path resolution;
- `agnara`, `agnara-cli` and declared HTTP/MCP distribution metadata exist
  with non-empty version strings matching the installed kernel version;
- declared A2A exposures fail with an explanation that adapter metadata checks
  are not implemented by this diagnostic; they do not imply the provisional
  adapter has no runtime;
- Events exposures fail as a reserved namespace without an implemented event
  runtime; Tasks exposures fail because no task runtime is implemented.

The latter checks do not inspect installed adapter metadata. Installing a
distribution does not make an unchecked exposure pass. These messages preserve
the failure status while distinguishing diagnostic coverage from framework
implementation status; they do not enable provisional A2A metadata checks.

No application module, adapter or SDK is imported. No source file is read
to infer registration or architecture. No dependency is installed, project
file written or repair attempted. The existing free-form manifest `python`
string is reported without interpreting it as a version constraint.

The report always identifies unchecked runtime registration, dependency
cycles, protocol configuration, architecture rules and the project's Python
constraint. A passing result means only that the listed static checks passed.
It does not certify protocol support, startup, authentication or production
readiness. A supported adapter's version metadata does not prove its imports
or complete dependency graph are usable.

## Output and exit codes

Text output lists stable check identifiers, pass/fail status and a message.
`--json` emits `format: agnara.doctor`, `format_version: 1`, `project`,
`checks`, `status` and `unchecked`. `project` is null when no valid manifest
was read; otherwise it contains the declared name and Python string. Checks
have `id`, `status` and `message`, in deterministic evaluation order. No
timestamps, generated identities or environment dumps are included.

The report goes to stdout. Exit 0 means every performed check passed; exit 1
means at least one failed, including a missing or invalid manifest. Argument
errors retain argparse's exit 2 and stderr behavior. Unexpected programming
errors still propagate rather than being reported as project diagnostics.

A private CLI command-result value carries output and exit code. Existing
handlers returning text/bytes/None retain their behavior; the four governed
Python exports are unchanged.

## Alternatives and remaining work

Importing a runtime target by default would make a diagnostic command execute
arbitrary project startup. A runtime mode needs an explicit target, ownership
and output contract in separate work. A complete architecture analyzer also
needs its own bounded contract; the generated test remains the existing
architecture check. A third-party PEP 440 parser or another manifest format
is unnecessary for this first boundary.

This proposal implements the reversible static boundary while maintainer
review is pending. It does not mark the broader doctor specification complete
or promote this record to Accepted.

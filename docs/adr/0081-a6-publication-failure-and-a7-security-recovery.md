# ADR 0081: A6 publication failure and A7 security recovery

- Status: Accepted
- Date: 2026-09-08
- Release: `0.1.0a7`

## Context

The immutable `v0.1.0a6` tag passed repository publication readiness and
entered the PyPI publish job. The first upload was
`agnara_a2a-0.1.0a6-py3-none-any.whl`. Its Core Metadata project name is
`agnara-a2a`, but PyPI returned `400 Non-user identities cannot create new
projects` before accepting any file.

The underscore in the filename is required distribution filename
normalization under the wheel and sdist specifications. It does not change the
canonical project name. PyPI's response means that no Pending Trusted
Publisher matched both project `agnara-a2a` and the authenticated GitHub OIDC
identity at upload time. Public APIs cannot reveal which private Pending
Trusted Publisher field was wrong.

Three CodeQL findings were also open on `main`: incomplete URL substring
checking in Scalar bundle evidence, possible clear-text logging of untrusted
artifact diagnostics, and a workflow without explicit permissions.

## Decision

`0.1.0a7` is a publication and security recovery release. It changes no
framework runtime behavior. It:

- fixes the three CodeQL causes without suppressions;
- requires publication evidence to record the exact PyPI Project name as well
  as the shared Trusted Publisher tuple;
- resets every publisher confirmation for a fresh owner readback after the A6
  failure; and
- keeps the kernel-last, fail-closed publication order.

The owner must delete any mismatched `agnara-a2a` pending entry and recreate it
with Project name `agnara-a2a`, provider GitHub Actions, owner `Blandskron`,
repository `agnara`, workflow `release.yml`, and environment `pypi`. The same
exact project-name readback is required for the other six entries before A7.

Execution Semantics moves intact from `0.1.0a7` to `0.1.0a8`. I2, I3 and I14
lose no scope, and no implementation from that horizon enters this recovery.

## Consequences

- `v0.1.0a6` remains immutable and is documented as an aborted publication.
- A7 remains fail-closed until new human evidence is recorded.
- The repository cannot prove private PyPI state; it can make the evidence
  precise enough that a reviewer must read and record the exact project field.
- No token, manual upload or `skip-existing` workaround is introduced.


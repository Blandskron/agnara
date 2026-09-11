# Changelog

## [Unreleased]

Work in this section contributes to the first stable `1.0.0` release. Entries
describe user- and contributor-visible changes only.

- Redact unexpected capability exception messages and tracebacks from default
  runtime logs while retaining the capability identifier for correlation.
- Add the protocol-neutral streaming kernel contract decided by ADR 0084.
  A capability declares `streaming=True` and yields its units from an async
  generator; `agnara.execution.open_stream` returns an owned, one-shot
  `CapabilityStream` with pull-based backpressure and no kernel buffer,
  evaluates policy and validates input before the first unit, closes the
  producer before releasing the invocation scope, and reports how it ended
  through `StreamTerminal`. A failure after output raises `StreamInterrupted`
  carrying a redacted canonical `Failure` and the number of units already
  emitted, instead of a result that implies nothing was produced.
- Refuse a streaming capability at `invoke` and `invoke_result`, and refuse an
  async generator handler that was never declared streaming at compile time.
- Add `InvocationTerminalEvent.units`: the unit count for a streaming
  invocation, `None` for a complete-result one.

## [0.1.0a8] - 2026-09-09

`0.1.0a8` is retained only as evidence that the repository can build, verify
and publish its synchronized distribution set through a reviewed,
dispatch-driven workflow. It is not a supported compatibility baseline and is
not followed by further pre-release publications.

[Unreleased]: https://github.com/Blandskron/agnara/compare/v0.1.0a8...develop
[0.1.0a8]: https://github.com/Blandskron/agnara/compare/v0.1.0a8...v0.1.0a8

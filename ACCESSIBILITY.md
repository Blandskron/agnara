# Agnara Accessibility Statement

Last reviewed: 2026-10-04.

## Commitment and scope

We want people with disabilities to be able to read Agnara's documentation,
use its developer tools and participate in the project. Accessibility barriers
are product and contributor-workflow defects, and we welcome reports from
people using assistive technology.

For web interfaces maintained by Agnara, our improvement goal is
[Web Content Accessibility Guidelines (WCAG) 2.2 Level AA](https://www.w3.org/TR/WCAG22/).
This is a goal, not a claim that Agnara currently conforms to every criterion.
The statement covers repository documentation, the CLI, Agnara Explorer and
the integration of optional HTTP documentation interfaces. Applications built
with Agnara remain responsible for their own interfaces and content.

## Environments and evidence

The framework requires Python 3.14 or newer. The ordinary CI suite runs on
Linux, macOS and Windows; those results establish framework test evidence,
not accessibility validation for every operating system or terminal.

The dedicated browser CI job uses pinned Playwright with Chromium. Explorer
checks cover heading structure, page language, named links and landmarks,
the browser accessibility tree, keyboard navigation, direct links and reloads.
Representative views are checked at widths of 390 and 1280 CSS pixels and a
height of 844 pixels. These are bounded regression fixtures, not a complete
mobile, browser or assistive-technology support matrix.

See the [Explorer browser tests](tests/http/test_explorer_browser.py),
[documentation browser tests](tests/http/test_documentation_browser.py) and
[quality gates](QUALITY_GATES.md) for the exact checks. Tests skipped during a
normal local run are not evidence that browser checks passed; the dedicated
CI job runs them explicitly.

## Known limitations and alternatives

- Browser accessibility-tree checks are not sessions with a screen reader.
  No complete audit with NVDA, JAWS, VoiceOver or other assistive technology
  is recorded, and no project-wide WCAG certification is claimed.
- Firefox, Safari, browser zoom combinations, alternative input devices and
  terminal/screen-reader combinations do not have comprehensive accessibility
  coverage in the current CI matrix.
- Swagger UI, Scalar and ReDoc are optional third-party renderers. Integration
  checks do not establish the accessibility of every upstream interaction,
  including forms, authentication flows or complex generated schemas.
- CLI commands offer text output, and selected commands support `--json`.
  These can be useful alternatives to browser interfaces; the options and
  limitations are documented in the [CLI specification](docs/CLI_SPEC.md).
- Where a deployment permits it, an authorized OpenAPI document or a filtered
  introspection snapshot can be consumed by other tools. Documentation HTML
  can be disabled independently. These alternatives retain the deployment's
  visibility and authorization requirements; see
  [HTTP composition](docs/HTTP_COMPOSITION.md) and
  [introspection](docs/INTROSPECTION.md).

GitHub hosts the repository's community interfaces and controls their
accessibility separately. Agnara does not claim to certify GitHub or a user's
editor, terminal or deployment.

## Report an accessibility barrier

Use the [accessibility issue form](https://github.com/Blandskron/agnara/issues/new?template=accessibility.yml).
If that form is a barrier, if you prefer a private report or if personal
details are involved, email
[contacto@blandskron.com](mailto:contacto@blandskron.com). A short description
of the task you could not complete is enough to begin; a screenshot or video
is not required, and you do not need to disclose a diagnosis or disability.

When available, include the page or command, expected and observed behavior,
reproduction steps, Agnara version, operating system, browser or terminal,
assistive technology and any workaround. Do not include secrets, credentials
or unnecessary personal information in public reports. Vulnerabilities should
use the private channel in [SECURITY.md](SECURITY.md).

The maintainer will prioritize barriers that prevent completing a task,
request clarification when needed and track fixes or workarounds in the
repository. We welcome voluntary feedback on whether a proposed fix resolves
the barrier. Response and resolution times depend on maintainer capacity;
there is no guaranteed service deadline.

## Improving accessibility

Changes to documentation and interfaces should preserve descriptive links,
logical headings, meaningful text alternatives and keyboard usability. Status
and errors should be understandable without relying only on color. New visual
media should include suitable descriptions, captions or transcripts.

Contributors should run the relevant existing browser checks for UI changes,
record any manual keyboard or assistive-technology checks they performed and
state remaining coverage gaps. Do not describe an automated check as a manual
screen-reader test. The [contributing guide](CONTRIBUTING.md) explains the
normal review process. We will update this statement when verified evidence,
known limitations or reporting channels change.

This statement follows the structure recommended by the
[Open Source accessibility guide](https://opensource.guide/accessibility-best-practices-for-your-project/)
and [W3C guidance on accessibility statements](https://www.w3.org/WAI/planning/statements/).

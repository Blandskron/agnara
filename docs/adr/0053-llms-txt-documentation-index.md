# ADR 0053 — llms.txt as an Optional Documentation Index

- Status: Proposed
- Date: 2026-09-05
- Tracking: GitHub Issue #210 (E8.12)

## Context

E8.12 asks whether Agnara should generate `llms.txt`. The current implemented
surfaces already separate three audiences: versioned introspection describes
the compiled application, protocol adapters project their own contracts, and
`agnara context` renders a filtered snapshot for an operator to give an agent.
None authorizes invocation. See [ADR 0051](0051-generated-agent-context.md).

The dated [primary-source research](../REFERENCE_RESEARCH.md#llmstxt)
establishes a separate use case: helping a reader find documentation pages.
Publication by documentation vendors is observable; automatic consumption by
every agent and better search rankings do not follow from publication.

## Decision

Do not add an automatic `/llms.txt` route, a new context-output format, or an
`llms-full.txt` export to the runtime in this change. Retain the existing
filtered snapshot and `agnara context` interfaces. This is a reversible
decision about current implementation scope, not a prohibition on an
application independently publishing documentation.

An optional documentation index belongs to the documentation site's build
and publication layer. It should link to reviewed documentation for a named
release, not enumerate whatever capabilities happen to be registered in the
server hosting the website. Agnara currently has no documentation-site
publication manifest defining that versioned page set; inventing one URL per
capability would promise pages and contracts that do not exist.

The index, if introduced, must remain removable without changing compilation,
discovery or invocation. It must not require a core dependency or a second
capability registry. Its presence grants no permission; its absence denies
none. Each linked resource retains its own publication and access decisions.

## Options considered

| Option | Fit | Decision |
| --- | --- | --- |
| Rename `agnara context` output to `llms.txt` | Conflates selected runtime metadata with a site's documentation index | Reject as a framework format claim |
| Generate a runtime route for every application | Requires URL ownership, viewer-specific publication and another served surface without an identified consumer | Defer |
| Generate a small index during documentation builds | Has an explicit page set, version and publication owner | Preferred future scope |
| Generate one full documentation dump | Adds size, duplication and freshness costs without a demonstrated need | Defer separately |

An operator can choose any output filename for `agnara context`; doing so
does not turn that file into a new supported Agnara format. No filename
restriction is added.

## Conditions for a future implementation

Start a separate executable Issue when there is a deployed documentation site,
an owned versioned page manifest, and a named consumer that can be tested.
That Issue must specify the base URL, path, supported proposal revision,
generation command, ordering, size limit and stale-version handling.

Use explicit public documentation inputs. Do not crawl arbitrary URLs, import
application modules, resolve schema references, or follow runtime exposure
names to manufacture content. Credentials, signed URLs, local filesystem
paths and viewer-specific context exports are not publication inputs. Treat
linked text as content, never as instructions that can widen authorization.

Validation must cover deterministic output from the same manifest, live or
locally served link targets under the configured base path, deliberate
version selection, exclusion of private pages and metadata, and independent
disablement. If a future design serves personalized indexes, its Issue must
also specify authentication, pre-serialization filtering and cache isolation;
public documentation generation cannot silently evolve into that service.

Evaluate utility with fixed documentation questions and a named client,
comparing answers and retrieved pages with and without the index. Record
failures as well as successes. Fetching a file proves reachability, not that
the client discovered it independently, used it correctly or saved tokens.

## Evidence and limits

This change delivers research and a proposed decision only. It adds no
generator, hosted endpoint, dependency or compatibility claim. Existing
context tests remain the evidence for the existing context command. The
research sources are dated observations and must be checked again before
implementation. Maintainer acceptance and repository integration remain
distinct from completing this local research.

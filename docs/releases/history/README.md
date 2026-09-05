# Release history — maturity snapshots

Two kinds of document describe a release, and they answer different questions.

| Location | Audience | Question it answers |
| --- | --- | --- |
| `docs/releases/v<version>.md` | whoever installs the package | What is this release, what does it contain, how do I use it? |
| `docs/releases/history/<version>.md` | whoever audits the project later | What did this release *prove*, on what evidence, and what did it still not prove? |

The first is the existing repository convention and stays exactly as it is. The
second is added by the release readiness program in
[`../RELEASE_PLAN.md`](../RELEASE_PLAN.md).

A snapshot is written **after** a release is published, never before, and
records:

- what the release proved;
- which gates were satisfied, and the evidence for each;
- the architectural state at that point;
- the reference applications used, where applicable;
- known limitations;
- release date, Git tag, commit SHA and published PyPI version.

Taken together these turn the repository's history into evidence of how Agnara
matured, rather than a list of version numbers.

No snapshot exists yet: `0.1.0a1` and `0.1.0a2` predate this program, and their
release notes remain the record for them.

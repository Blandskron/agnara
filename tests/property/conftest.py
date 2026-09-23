"""Deterministic, bounded settings for the property and fuzz lanes.

Two constraints shape everything in this directory.

**CI must be reproducible.** A lane that explores different inputs on every
run reports failures nobody can reproduce and turns a red build into a
guessing game. ``derandomize=True`` makes Hypothesis derive its inputs from
the test itself, so a given commit explores the same inputs on every machine
and every run. A failure here is always reproducible from the commit alone.

**CI must not be held open.** These lanes run inside the ordinary test matrix,
next to everything else, so their cost is a hard budget rather than a
preference. Example counts are small, every strategy is explicitly bounded,
and a per-example deadline turns an accidental quadratic into one failed test
instead of a stalled job.

The cost of both choices is honest and worth stating: a derandomized lane with
a small budget is a *regression* net, not a search. It re-proves known
properties cheaply on every commit. It is not a substitute for a long
randomized campaign or a real fuzzing corpus, and this repository does not
claim either -- see ``docs/THREAT_MODEL.md`` section 11.
"""

from __future__ import annotations

from hypothesis import HealthCheck, Verbosity, settings

#: Per-example wall-clock ceiling. Generous enough that ordinary scheduling
#: noise on a loaded CI runner does not fail a test, tight enough that a
#: pathological input is reported rather than waited on.
DEADLINE_MS = 2000

settings.register_profile(
    "agnara",
    max_examples=150,
    derandomize=True,
    deadline=DEADLINE_MS,
    print_blob=True,
    # A derandomized lane cannot replay a database entry from another machine,
    # and committing one would be a second source of truth beside the explicit
    # ``@example`` regressions. Discovered failures are pinned as code instead.
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
    verbosity=Verbosity.normal,
)

#: Reserved for the parser lanes, where each example is cheap and coverage of
#: byte-level shapes matters more than depth per example.
settings.register_profile(
    "agnara-fuzz",
    parent=settings.get_profile("agnara"),
    max_examples=400,
)

settings.load_profile("agnara")

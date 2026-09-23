"""Algebraic properties of startup registration and request matching.

The router is the first thing an attacker-controlled request reaches, and it
is combinatorial in exactly the way `QUALITY_GATES.md` names: a trie over
static and parameter segments, keyed by method. Hand-picked cases prove the
routes an author thought of; these prove the shape of the function.

The contract under test has two halves that must not be confused:

* a **template** is authored, so a malformed one is a definition error and
  raising is correct;
* a **request** is attacker-controlled, so no input may raise. It matches or
  it does not.

``_request_segments`` already states that split for paths. F-1 and F-2 below
are the two places the method side of it was missing.
"""

from __future__ import annotations

import string

from hypothesis import example, given
from hypothesis import strategies as st

from agnara_http._routing import (
    _FrozenRouteRegistry,
    _RouteDefinitionError,
    _RouteRegistry,
)

#: RFC 9110 token characters, which is what the router accepts as a method.
TOKEN_CHARS = string.ascii_letters + string.digits + "!#$%&'*+-.^_`|~"

methods = st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])

#: Bounded deliberately: the trie's behaviour does not change past a handful
#: of segments, and an unbounded strategy would make the lane a cost centre.
static_segment = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-_", min_size=1, max_size=8
)
parameter_name = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8).filter(
    lambda name: name.isidentifier()
)


@st.composite
def templates(draw: st.DrawFn) -> tuple[str, tuple[str, ...]]:
    """A valid route template plus the parameter names it declares."""
    count = draw(st.integers(min_value=0, max_value=4))
    segments: list[str] = []
    names: list[str] = []
    for _ in range(count):
        if draw(st.booleans()):
            name = draw(parameter_name)
            if name in names:
                continue
            names.append(name)
            segments.append("{" + name + "}")
        else:
            segments.append(draw(static_segment))
    return "/" + "/".join(segments), tuple(names)


def registry_with(*routes: tuple[str, str]) -> _FrozenRouteRegistry[str]:
    registry: _RouteRegistry[str] = _RouteRegistry()
    for method, template in routes:
        registry.register(method, template, f"{method} {template}")
    return registry.freeze()


# ---------------------------------------------------------------------------
# Totality: a request may never raise
# ---------------------------------------------------------------------------


@given(
    method=st.text(max_size=12),
    path=st.text(max_size=40),
)
# F-1: a method that is not an RFC 9110 token escaped as _RouteDefinitionError,
# carrying the attacker's own bytes in the message. The dispatcher sent
# nothing, so the ASGI server decided the response and the operator's log.
@example(method="BAD METHOD", path="/p")
@example(method="GET\x00", path="/p")
@example(method="GET\r\nX-Injected: y", path="/p")
@example(method="", path="/p")
@example(method="ÉTÉ", path="/p")
# Targets an ASGI server may legitimately pass through unchanged.
@example(method="OPTIONS", path="*")
@example(method="GET", path="http://elsewhere.example/p")
@example(method="GET", path="")
def test_matching_a_request_never_raises(method: str, path: str) -> None:
    """Any pair of strings is answerable. Unroutable is a result, not an error."""
    frozen = registry_with(("GET", "/p"), ("POST", "/p"), ("GET", "/p/{id}"))

    # Not raising is the property. The assertions only pin down the shape of
    # the two answers the router is allowed to give.
    match = frozen.match(method, path)
    assert match is None or match.route.method in {"GET", "POST"}

    allowed = frozen.allowed_methods(path)
    assert isinstance(allowed, tuple)
    assert set(allowed) <= {"GET", "POST"}


@given(method=st.text(alphabet=TOKEN_CHARS, min_size=1, max_size=12))
def test_only_the_registered_method_matches_its_path(method: str) -> None:
    """A well-formed token nobody registered is an ordinary miss."""
    frozen = registry_with(("GET", "/p"))

    assert (frozen.match(method, "/p") is not None) == (method == "GET")


# ---------------------------------------------------------------------------
# Method identity
# ---------------------------------------------------------------------------


@given(method=methods)
# F-2: request methods were uppercased before lookup, so `post` routed as
# POST. RFC 9110 section 9.1 makes the method token case-sensitive, and a
# proxy that denies `POST /admin` case-sensitively would have been bypassed.
@example(method="POST")
def test_a_request_method_is_matched_case_sensitively(method: str) -> None:
    frozen = registry_with((method, "/p"))

    assert frozen.match(method, "/p") is not None
    for variant in {method.lower(), method.capitalize(), method.swapcase()} - {method}:
        assert frozen.match(variant, "/p") is None, variant


@given(template=templates())
def test_registration_still_normalizes_an_authored_method(
    template: tuple[str, tuple[str, ...]],
) -> None:
    """Authoring stays forgiving: `http.post(...)` and `POST` are one route."""
    path, _ = template
    registry: _RouteRegistry[str] = _RouteRegistry()
    registry.register("post", path, "target")
    frozen = registry.freeze()

    assert next(iter(frozen)).method == "POST"
    if "{" not in path:
        assert frozen.match("POST", path) is not None
        assert frozen.match("post", path) is None


# ---------------------------------------------------------------------------
# Trie behaviour
# ---------------------------------------------------------------------------


@given(template=templates(), method=methods)
def test_a_static_template_matches_its_own_literal_path(
    template: tuple[str, tuple[str, ...]], method: str
) -> None:
    path, names = template
    if names:
        return
    frozen = registry_with((method, path))

    match = frozen.match(method, path)
    assert match is not None
    assert match.route.path_template == path
    assert dict(match.path_parameters) == {}


@given(
    prefix=static_segment,
    literal=static_segment,
    method=methods,
)
def test_a_static_segment_always_wins_over_a_parameter(
    prefix: str, literal: str, method: str
) -> None:
    """Precedence must not depend on registration order."""
    static_template = f"/{prefix}/{literal}"
    parameter_template = f"/{prefix}/{{captured}}"

    for order in ((static_template, parameter_template), (parameter_template, static_template)):
        frozen = registry_with(*((method, template) for template in order))
        match = frozen.match(method, f"/{prefix}/{literal}")
        assert match is not None
        assert match.route.path_template == static_template
        assert dict(match.path_parameters) == {}


@given(prefix=static_segment, captured=static_segment, method=methods)
def test_a_parameter_captures_exactly_its_segment(prefix: str, captured: str, method: str) -> None:
    frozen = registry_with((method, f"/{prefix}/{{value}}"))

    match = frozen.match(method, f"/{prefix}/{captured}")
    assert match is not None
    assert dict(match.path_parameters) == {"value": captured}


@given(prefix=static_segment, method=methods)
def test_an_empty_segment_never_satisfies_a_parameter(prefix: str, method: str) -> None:
    """`/a//` must not bind an empty string to a declared parameter."""
    frozen = registry_with((method, f"/{prefix}/{{value}}"))

    assert frozen.match(method, f"/{prefix}/") is None


# ---------------------------------------------------------------------------
# allowed_methods agrees with match
# ---------------------------------------------------------------------------


@given(template=templates(), chosen=st.lists(methods, min_size=1, max_size=4, unique=True))
def test_allowed_methods_is_exactly_the_set_that_matches(
    template: tuple[str, tuple[str, ...]], chosen: list[str]
) -> None:
    path, names = template
    if names:
        return
    frozen = registry_with(*((method, path) for method in chosen))

    allowed = frozen.allowed_methods(path)
    assert set(allowed) == {method for method in chosen if frozen.match(method, path) is not None}
    assert len(allowed) == len(set(allowed))


# ---------------------------------------------------------------------------
# Authored mistakes still raise
# ---------------------------------------------------------------------------


@given(
    method=st.text(max_size=8).filter(
        lambda value: not value or any(char not in TOKEN_CHARS for char in value)
    )
)
def test_an_authored_method_that_is_not_a_token_is_a_definition_error(method: str) -> None:
    registry: _RouteRegistry[str] = _RouteRegistry()
    try:
        registry.register(method, "/p", "target")
    except _RouteDefinitionError:
        return
    raise AssertionError(f"registration accepted a non-token method: {method!r}")


@given(template=templates())
def test_registering_the_same_shape_twice_is_refused(
    template: tuple[str, tuple[str, ...]],
) -> None:
    path, _ = template
    registry: _RouteRegistry[str] = _RouteRegistry()
    registry.register("GET", path, "first")
    try:
        registry.register("GET", path, "second")
    except _RouteDefinitionError:
        return
    raise AssertionError(f"duplicate template accepted: {path!r}")

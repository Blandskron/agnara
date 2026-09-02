import threading
from collections.abc import Mapping
from typing import Any

import pytest

from agnara_http._routing import (
    _DuplicateRouteError,
    _FrozenNode,
    _FrozenRouteRegistry,
    _match_node,
    _Route,
    _RouteDefinitionError,
    _RouteRegistry,
    _RouteRegistryFrozenError,
)


class TestRegistration:
    def test_registers_and_normalizes_method(self) -> None:
        target = object()
        route = _RouteRegistry[object]().register("get", "/users/{user_id}", target)

        assert route.method == "GET"
        assert route.path_template == "/users/{user_id}"
        assert route.target is target

    def test_preserves_registration_order(self) -> None:
        registry = _RouteRegistry[str]()
        first = registry.register("POST", "/users", "create")
        second = registry.register("GET", "/users/{user_id}", "get")

        assert list(registry) == [first, second]
        assert list(registry.freeze()) == [first, second]

    @pytest.mark.parametrize("method", ["", "GET USER", "GÉT", "GET\n"])
    def test_rejects_invalid_method_token(self, method: str) -> None:
        with pytest.raises(_RouteDefinitionError, match="invalid HTTP method token"):
            _RouteRegistry[object]().register(method, "/", object())

    def test_rejects_non_string_method(self) -> None:
        with pytest.raises(_RouteDefinitionError, match="HTTP method must be a string"):
            _RouteRegistry[object]().register(42, "/", object())  # ty: ignore

    @pytest.mark.parametrize("path", ["", "users", "users/{user_id}"])
    def test_rejects_path_without_leading_slash(self, path: str) -> None:
        with pytest.raises(_RouteDefinitionError, match="must start with"):
            _RouteRegistry[object]().register("GET", path, object())

    def test_rejects_non_string_path(self) -> None:
        with pytest.raises(_RouteDefinitionError, match="route path must be a string"):
            _RouteRegistry[object]().register("GET", object(), object())  # ty: ignore

    @pytest.mark.parametrize("segment", ["{}", "{not-valid}", "{class}", "{123}", "{{id}}"])
    def test_rejects_invalid_parameter_name(self, segment: str) -> None:
        with pytest.raises(_RouteDefinitionError, match="non-keyword Python identifier"):
            _RouteRegistry[object]().register("GET", f"/users/{segment}", object())

    @pytest.mark.parametrize("segment", ["prefix-{id}", "{id}-suffix", "id}"])
    def test_rejects_parameter_that_is_not_a_complete_segment(self, segment: str) -> None:
        with pytest.raises(_RouteDefinitionError, match="complete path segment"):
            _RouteRegistry[object]().register("GET", f"/users/{segment}", object())

    def test_rejects_repeated_parameter_name(self) -> None:
        with pytest.raises(_RouteDefinitionError, match="appears more than once"):
            _RouteRegistry[object]().register("GET", "/{item}/{item}", object())


class TestCollisions:
    def test_rejects_duplicate_method_and_template(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}", "first")

        with pytest.raises(_DuplicateRouteError, match="conflicts with"):
            registry.register("get", "/users/{user_id}", "second")

    def test_rejects_structural_collision_with_renamed_parameter(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}/orders/{order_id}", "first")

        with pytest.raises(
            _DuplicateRouteError,
            match=r"/users/\{user_id\}/orders/\{order_id\}",
        ):
            registry.register("GET", "/users/{account}/orders/{order}", "second")

    def test_allows_the_same_template_for_different_methods(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}", "read")
        registry.register("DELETE", "/users/{user_id}", "delete")
        assert len(registry) == 2

    def test_allows_static_and_parameter_alternatives(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/current", "current")
        registry.register("GET", "/users/{user_id}", "by_id")
        assert len(registry) == 2


class TestFreezing:
    def test_freeze_returns_compiled_registry_and_closes_registration(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/", "root")

        frozen = registry.freeze()

        assert isinstance(frozen, _FrozenRouteRegistry)
        assert registry.is_frozen
        with pytest.raises(_RouteRegistryFrozenError, match="after route freeze"):
            registry.register("GET", "/other", "other")

    def test_freeze_is_idempotent(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/", "root")
        assert registry.freeze() is registry.freeze()

    def test_snapshot_is_detached_from_startup_collection(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/", "root")
        frozen = registry.freeze()

        registry._routes.append(registry._routes[0])

        assert len(frozen) == 1

    def test_empty_registry_can_be_frozen(self) -> None:
        frozen = _RouteRegistry[object]().freeze()
        assert len(frozen) == 0
        assert frozen.match("GET", "/") is None

    def test_frozen_registry_has_no_registration_surface(self) -> None:
        frozen = _RouteRegistry[object]().freeze()
        assert not hasattr(frozen, "register")

    def test_compiled_method_index_cannot_be_mutated(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users", "users")
        frozen = registry.freeze()

        roots: Any = frozen._roots
        static_children: Any = roots["GET"].static
        with pytest.raises(TypeError):
            roots["POST"] = roots["GET"]
        with pytest.raises(TypeError):
            static_children["other"] = roots["GET"]

    def test_repr_reports_size_and_phase(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/", "root")
        assert "1 routes, open" in repr(registry)
        registry.freeze()
        assert "1 routes, frozen" in repr(registry)
        assert "1 routes" in repr(registry.freeze())


class TestMatching:
    def test_matches_root_and_normalizes_lookup_method(self) -> None:
        frozen = _RouteRegistry[str]()
        route = frozen.register("GET", "/", "root")
        match = frozen.freeze().match("get", "/")

        assert match is not None
        assert match.route is route
        assert match.route.target == "root"
        assert match.path_parameters == {}

    def test_captures_multiple_path_parameters(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}/orders/{order_id}", "order")

        match = registry.freeze().match("GET", "/users/u-123/orders/o-456")

        assert match is not None
        assert match.route.target == "order"
        assert match.path_parameters == {"user_id": "u-123", "order_id": "o-456"}

    def test_capture_mapping_is_immutable(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}", "user")
        match = registry.freeze().match("GET", "/users/u-123")
        assert match is not None

        parameters: Any = match.path_parameters
        assert isinstance(parameters, Mapping)
        with pytest.raises(TypeError):
            parameters["user_id"] = "changed"

    def test_static_route_wins_over_parameter_route_regardless_of_order(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}", "parameter")
        registry.register("GET", "/users/current", "static")

        match = registry.freeze().match("GET", "/users/current")

        assert match is not None
        assert match.route.target == "static"
        assert match.path_parameters == {}

    def test_falls_back_to_parameter_when_static_branch_cannot_complete(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/files/static/download", "static")
        registry.register("GET", "/files/{folder}/metadata", "parameter")

        match = registry.freeze().match("GET", "/files/static/metadata")

        assert match is not None
        assert match.route.target == "parameter"
        assert match.path_parameters == {"folder": "static"}

    def test_trailing_slash_is_significant(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users", "without")
        registry.register("GET", "/users/", "with")
        frozen = registry.freeze()

        without = frozen.match("GET", "/users")
        with_slash = frozen.match("GET", "/users/")

        assert without is not None and without.route.target == "without"
        assert with_slash is not None and with_slash.route.target == "with"

    def test_parameter_does_not_capture_empty_segment(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}", "user")
        assert registry.freeze().match("GET", "/users/") is None

    def test_deep_untrusted_path_does_not_depend_on_python_recursion(self) -> None:
        segments = tuple(f"segment-{index}" for index in range(2_000))
        route = _Route("GET", "/deep", "deep", segments, ())
        node = _FrozenNode(static={}, parameter=None, route=route)
        for segment in reversed(segments):
            node = _FrozenNode(static={segment: node}, parameter=None, route=None)

        assert _match_node(node, segments) == (route, ())

    @pytest.mark.parametrize(
        ("method", "path"),
        [("POST", "/users/u-123"), ("GET", "/missing"), ("GET", "/users/u-123/extra")],
    )
    def test_missing_route_returns_none(self, method: str, path: str) -> None:
        registry = _RouteRegistry[str]()
        registry.register("GET", "/users/{user_id}", "user")
        assert registry.freeze().match(method, path) is None

    def test_allowed_methods_follow_first_registration_order(self) -> None:
        registry = _RouteRegistry[str]()
        registry.register("PATCH", "/users/{user_id}", "patch")
        registry.register("GET", "/users/{user_id}", "get")
        registry.register("DELETE", "/users/current", "delete-current")
        frozen = registry.freeze()

        assert frozen.allowed_methods("/users/u-123") == ("PATCH", "GET")
        assert frozen.allowed_methods("/users/current") == ("PATCH", "GET", "DELETE")
        assert frozen.allowed_methods("/missing") == ()


class TestConcurrency:
    def test_concurrent_unique_registration_loses_nothing(self) -> None:
        registry = _RouteRegistry[int]()
        barrier = threading.Barrier(8)
        errors: list[Exception] = []

        def worker(offset: int) -> None:
            barrier.wait()
            for index in range(offset, 200, 8):
                try:
                    registry.register("GET", f"/items/{index}", index)
                except Exception as error:
                    errors.append(error)

        threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        frozen = registry.freeze()
        assert errors == []
        assert len(frozen) == 200
        for index in range(200):
            match = frozen.match("GET", f"/items/{index}")
            assert match is not None and match.route.target == index

    def test_racing_duplicates_have_exactly_one_winner(self) -> None:
        registry = _RouteRegistry[int]()
        barrier = threading.Barrier(8)
        outcomes: list[str] = []
        outcomes_lock = threading.Lock()

        def worker(index: int) -> None:
            barrier.wait()
            try:
                registry.register("GET", "/items/{item_id}", index)
                outcome = "registered"
            except _DuplicateRouteError:
                outcome = "rejected"
            with outcomes_lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert outcomes.count("registered") == 1
        assert outcomes.count("rejected") == 7
        assert len(registry) == 1

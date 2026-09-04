"""E7.2 MCP tool exposure projection."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agnara import Agnara, CapabilityDefinition
from agnara_mcp import FrozenMcpTools, Mcp, McpToolDefinitionError, McpToolExposure


def test_golden_api_projects_a_declared_callable_with_stable_identity() -> None:
    app = Agnara("users")

    @app.capability(description="Get one user")
    def get_user(user_id: str) -> str:
        return user_id

    mcp = Mcp(app)
    exposure = mcp.tool(get_user)
    tools = mcp.compile()

    assert isinstance(exposure, McpToolExposure)
    assert exposure.name == "users.get_user"
    assert exposure.definition is app.capabilities["users.get_user"]
    assert exposure.definition.description == "Get one user"
    assert isinstance(tools, FrozenMcpTools)
    assert tools["users.get_user"] is exposure


def test_explicit_name_override_preserves_registration_order() -> None:
    app = Agnara("users")

    @app.capability
    def first() -> None: ...

    @app.capability
    def second() -> None: ...

    mcp = Mcp(app)
    first_exposure = mcp.tool(first, name="users-first")
    second_exposure = mcp.tool(second)

    assert mcp.compile().exposures == (first_exposure, second_exposure)
    assert tuple(mcp.compile()) == ("users-first", "users.second")


def test_definition_form_selects_one_of_multiple_declarations() -> None:
    app = Agnara("users")

    def shared() -> None: ...

    app.capability(name="first")(shared)
    app.capability(name="second")(shared)
    mcp = Mcp(app)

    with pytest.raises(McpToolDefinitionError, match="multiple capabilities"):
        mcp.tool(shared)

    selected: CapabilityDefinition = app.capabilities["users.second"]
    assert mcp.tool(selected).definition is selected


@pytest.mark.parametrize("name", ["", "space name", "tool/route", "ñame", "x" * 129])
def test_invalid_mcp_names_fail_at_registration(name: str) -> None:
    app = Agnara("users")

    @app.capability
    def get_user() -> None: ...

    with pytest.raises(McpToolDefinitionError, match="1 to 128 ASCII"):
        Mcp(app).tool(get_user, name=name)


def test_unicode_capability_identity_requires_an_explicit_wire_name() -> None:
    app = Agnara("usuarios")

    @app.capability(name="obtener_ñandú")
    def get_user() -> None: ...

    mcp = Mcp(app)
    with pytest.raises(McpToolDefinitionError, match="ASCII"):
        mcp.tool(get_user)
    assert mcp.tool(get_user, name="usuarios.get_user").name == "usuarios.get_user"


def test_unknown_callable_and_foreign_definition_are_rejected() -> None:
    app = Agnara("users")
    foreign = Agnara("foreign")

    def unknown() -> None: ...

    @foreign.capability
    def capability() -> None: ...

    with pytest.raises(McpToolDefinitionError, match="not declared"):
        Mcp(app).tool(unknown)
    with pytest.raises(McpToolDefinitionError, match="not declared"):
        Mcp(app).tool(foreign.capabilities["foreign.capability"])


def test_duplicate_name_and_registration_after_compile_fail() -> None:
    app = Agnara("users")

    @app.capability
    def first() -> None: ...

    @app.capability
    def second() -> None: ...

    mcp = Mcp(app)
    mcp.tool(first, name="shared")
    with pytest.raises(McpToolDefinitionError, match=r"already exposes users\.first"):
        mcp.tool(second, name="shared")

    snapshot = mcp.compile()
    assert mcp.compile() is snapshot
    with pytest.raises(McpToolDefinitionError, match="after MCP compilation"):
        mcp.tool(second)


def test_compiled_snapshot_and_exposures_are_immutable() -> None:
    app = Agnara("users")

    @app.capability
    def get_user() -> None: ...

    exposure = Mcp(app).tool(get_user)
    with pytest.raises(FrozenInstanceError):
        exposure.name = "changed"  # ty: ignore[invalid-assignment]

    mcp = Mcp(app)
    mcp.tool(get_user)
    tools = mcp.compile()
    with pytest.raises(TypeError):
        tools._by_name["changed"] = exposure  # ty: ignore[invalid-assignment]


def test_constructor_and_target_type_errors_are_actionable() -> None:
    with pytest.raises(TypeError, match="Agnara application"):
        Mcp(object())  # ty: ignore[invalid-argument-type]

    app = Agnara("users")
    with pytest.raises(McpToolDefinitionError, match="callable or CapabilityDefinition"):
        Mcp(app).tool(42)  # ty: ignore[invalid-argument-type]


def test_repr_reports_application_count_and_state() -> None:
    app = Agnara("users")

    @app.capability
    def get_user() -> None: ...

    mcp = Mcp(app)
    assert repr(mcp) == "Mcp('users', 0 tools, open)"
    mcp.tool(get_user)
    tools = mcp.compile()
    assert repr(mcp) == "Mcp('users', 1 tools, compiled)"
    assert repr(tools) == "FrozenMcpTools(1 tools)"

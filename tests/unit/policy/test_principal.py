import pytest

from agnara._frozen import FrozenInstanceError
from agnara.policy.principal import AnonymousPrincipal, Principal


def test_principal_immutability():
    principal = Principal(identity="user_123", metadata={"role": "admin"})

    assert principal.identity == "user_123"
    assert principal.metadata == {"role": "admin"}

    with pytest.raises(FrozenInstanceError):
        principal.identity = "user_456"  # type: ignore


def test_anonymous_principal():
    principal = AnonymousPrincipal()
    assert principal.identity == "anonymous"
    assert principal.metadata == {}
    assert principal.scopes == frozenset()


def test_principal_copies_granted_scopes() -> None:
    source = {"users:read"}
    principal = Principal("user_123", scopes=source)
    source.add("users:write")

    assert principal.scopes == frozenset({"users:read"})


def test_anonymous_principal_never_grants_scopes() -> None:
    principal = AnonymousPrincipal(metadata={"source": "public"})

    assert principal.identity == "anonymous"
    assert principal.scopes == frozenset()

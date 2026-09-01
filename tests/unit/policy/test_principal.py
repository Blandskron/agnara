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

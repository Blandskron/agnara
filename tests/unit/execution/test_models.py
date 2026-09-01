import pytest

from agnara.capability.identity import CapabilityId
from agnara.core.di.registry import DIRegistry
from agnara.core.di.resolver import DIContainer
from agnara.errors import DefinitionError
from agnara.execution.context import ExecutionContext
from agnara.execution.invocation import Invocation


def test_invocation_construction():
    cap_id = CapabilityId("test", "cap")
    payload = {"foo": "bar"}
    metadata = {"trace": "123"}

    inv = Invocation(capability_id=cap_id, payload=payload, metadata=metadata)
    assert inv.capability_id == cap_id
    assert inv.payload == payload
    assert inv.metadata == metadata


def test_invocation_validates_capability_id():
    with pytest.raises(DefinitionError, match="capability_id must be a CapabilityId"):
        Invocation(capability_id="test.cap", payload={}, metadata={})  # type: ignore


def test_invocation_validates_payload():
    cap_id = CapabilityId("test", "cap")
    with pytest.raises(DefinitionError, match="payload must be a dictionary"):
        Invocation(capability_id=cap_id, payload="not-a-dict", metadata={})  # type: ignore


def test_execution_context_state():
    cap_id = CapabilityId("test", "cap")
    inv = Invocation(capability_id=cap_id, payload={}, metadata={})

    registry = DIRegistry()
    container = DIContainer(registry)

    ctx = ExecutionContext(invocation=inv, di_container=container, tracking_id="xyz-123")
    assert ctx.invocation is inv
    assert ctx.di_container is container
    assert ctx.tracking_id == "xyz-123"
    assert ctx.state == {}

    ctx.state["auth"] = True
    assert ctx.state["auth"] is True

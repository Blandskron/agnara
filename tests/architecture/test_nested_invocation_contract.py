"""Guard the accepted composition boundary and its documented exclusions.

ADR 0093 settled semantics before implementation. These checks keep the
important refusals visible: no ambient runtime, inherited authority or
invocation scope, and no silent extension into streams or cross-application
invocation.
"""

from tests.architecture.boundaries import WORKSPACE_ROOT

ADR = WORKSPACE_ROOT / "docs" / "adr" / "0093-nested-capability-invocation-contract.md"
INITIATIVES = WORKSPACE_ROOT / "docs" / "INITIATIVES.md"
MATURITY = WORKSPACE_ROOT / "docs" / "MATURITY.md"
THREAT_MODEL = WORKSPACE_ROOT / "docs" / "THREAT_MODEL.md"


def test_the_nested_invocation_decision_is_accepted_and_limits_implementation_scope() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "- Status: Accepted" in text
    assert "This record decides that contract only." in text
    assert "Cross-application composition is deliberately refused" in text
    assert "complete-result semantics only" in text


def test_the_contract_requires_independent_child_authorization_and_scope_isolation() -> None:
    text = ADR.read_text(encoding="utf-8")

    for required in (
        "fresh `ExecutionContext`",
        "Scopes are recomputed by the target policy",
        "Confirmation evidence never propagates implicitly",
        "parent\ninvocation-scoped dependency instances",
        "An idempotency selector is not inherited",
        "It rejects an identity already in that chain",
    ):
        assert required in text


def test_authoritative_status_documents_describe_the_implemented_narrow_boundary() -> None:
    assert "ADR 0093's same-compiled-application complete-result boundary is implemented" in (
        INITIATIVES.read_text(encoding="utf-8")
    )
    expected_maturity = (
        "| Capability-to-capability composition | `IMPLEMENTED` for same-snapshot "
        "complete results |"
    )
    assert expected_maturity in MATURITY.read_text(encoding="utf-8")
    threat_model = THREAT_MODEL.read_text(encoding="utf-8")
    assert "ADR 0093's implemented same-snapshot nested boundary" in threat_model
    assert "`CapabilityRuntime` keeps private immutable ancestry per child" in threat_model

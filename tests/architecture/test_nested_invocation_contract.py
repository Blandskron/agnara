"""Guard the accepted composition decision until a runtime implements it.

ADR 0093 deliberately settles semantics before exposing a convenience API.
These checks keep the important refusals visible to later implementation work:
no ambient runtime, no inherited authority or invocation scope, and no silent
extension into streams or cross-application invocation.
"""

from tests.architecture.boundaries import WORKSPACE_ROOT

ADR = WORKSPACE_ROOT / "docs" / "adr" / "0093-nested-capability-invocation-contract.md"
INITIATIVES = WORKSPACE_ROOT / "docs" / "INITIATIVES.md"
MATURITY = WORKSPACE_ROOT / "docs" / "MATURITY.md"
THREAT_MODEL = WORKSPACE_ROOT / "docs" / "THREAT_MODEL.md"


def test_the_nested_invocation_decision_is_accepted_and_deliberately_unimplemented() -> None:
    text = ADR.read_text(encoding="utf-8")

    assert "- Status: Accepted" in text
    assert "This record decides that contract only." in text
    assert "It adds no public symbol, runtime\nimplementation" in text
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


def test_authoritative_status_documents_describe_design_not_runtime_support() -> None:
    assert "ADR 0093 defines the nested-invocation contract; no runtime exists." in (
        INITIATIVES.read_text(encoding="utf-8")
    )
    assert "| Capability-to-capability composition | `DESIGNED` |" in MATURITY.read_text(
        encoding="utf-8"
    )
    threat_model = THREAT_MODEL.read_text(encoding="utf-8")
    assert "ADR 0093 designs a nested-call boundary" in threat_model
    assert "Designed, not implemented. ADR 0093 requires immutable" in threat_model

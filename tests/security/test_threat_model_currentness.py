"""Keep the historical 1.0 threat model scoped and visible to maintainers."""

from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SECURITY = WORKSPACE_ROOT / "SECURITY.md"
THREAT_MODEL = WORKSPACE_ROOT / "docs" / "THREAT_MODEL.md"


def test_security_entrypoint_names_the_historical_candidate_scope() -> None:
    text = SECURITY.read_text(encoding="utf-8")

    assert "records the 1.0.0 candidate threat-boundary analysis" in text
    assert "Revalidate it against the next release candidate" in text
    assert "not a production-security\ncertification" in text
    assert "general HTTP\nauthentication product" in text


def test_threat_model_covers_current_runtime_and_host_boundaries() -> None:
    text = THREAT_MODEL.read_text(encoding="utf-8")

    for required in (
        "# Threat Model — 1.0 Candidate",
        "**B5 — direct and embedded execution.**",
        "**B6 — schema and persistence.**",
        "**B7 — observability.**",
        "**B8 — local tooling and release.**",
        "A caller cannot choose the runtime execution identity",
        "A streaming invocation refuses an idempotency selector",
        "## 10. Adversarial review for 1.0.0",
        "no continuous or\ncoverage-guided fuzzing campaign",
        "no penetration test,\nno load or denial-of-service testing",
    ):
        assert required in text

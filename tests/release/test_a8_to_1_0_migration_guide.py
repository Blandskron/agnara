"""The A8-to-1.0 guide is a public release deliverable, not a stale note."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "MIGRATION_A8_TO_1_0.md"


def test_the_migration_guide_covers_the_frozen_1_0_boundaries() -> None:
    guide = GUIDE.read_text(encoding="utf-8")

    for required in (
        "agnara.di",
        "IntrospectionSnapshot.applications",
        "IdempotencyInvocation",
        "CapabilityRuntime",
        "CapabilityInvoker",
        "StreamTerminal",
        "StreamInterrupted",
        "Http.sse",
        "Principal",
        "agnara_http",
        "docs/public-api.json",
        "test_integrated_dogfooding.py",
    ):
        assert required in guide


def test_active_examples_and_guides_do_not_prescribe_pre_1_0_installs() -> None:
    paths = (
        ROOT / "examples" / "quickstart.py",
        ROOT / "examples" / "http_service.py",
        ROOT / "docs" / "HTTP_COMPOSITION.md",
        ROOT / "docs" / "MIGRATION_A8_TO_1_0.md",
    )

    for path in paths:
        assert "pip install agnara==0.1.0a" not in path.read_text(encoding="utf-8"), path

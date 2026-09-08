"""The release workflow publishes exactly the reviewed distribution set."""

from __future__ import annotations

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT

WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "release.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_builds_and_validates_the_complete_workspace() -> None:
    workflow = _text()

    assert "uv build --all-packages --out-dir dist/" in workflow
    assert "scripts/check_distributions.py" in workflow
    assert "--dist dist/" in workflow
    assert "--expected-version" in workflow
    assert "uv build --package agnara" not in workflow


def test_release_install_cannot_substitute_a_public_first_party_package() -> None:
    workflow = _text()

    third_party = workflow.index('"mcp==2.1.1" "opentelemetry-api>=1.44,<2"')
    first_party = workflow.index('--no-index --find-links "$GITHUB_WORKSPACE/dist"')
    installed_gate = workflow.index("--require-installed")

    assert third_party < first_party < installed_gate
    assert '"${#wheels[@]}" -ne 7' in workflow
    assert '"$SMOKE_PYTHON" -I' in workflow


def test_only_a_pushed_version_tag_can_publish() -> None:
    workflow = _text()

    assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in workflow
    assert "id-token: write" in workflow
    assert "attestations: true" in workflow
    assert "verify-metadata: true" in workflow
    assert "print-hash: true" in workflow


def test_post_release_verification_names_every_distribution() -> None:
    workflow = _text()

    for distribution in DISTRIBUTIONS:
        assert f'"{distribution}==$TAG_VERSION"' in workflow


def test_release_actions_are_pinned_to_exact_versions() -> None:
    actions = [
        line.split("uses:", 1)[1].strip()
        for line in _text().splitlines()
        if "uses:" in line and "./.github/" not in line
    ]
    assert actions
    for action in actions:
        _, _, version = action.partition("@")
        assert version.count(".") >= 2 or len(version) == 40, action


def test_reusable_quality_gate_can_upload_security_results_without_publication_rights() -> None:
    validation = _text().split("  validate:\n", 1)[1].split("  build:\n", 1)[0]
    assert "      contents: read\n      security-events: write" in validation
    assert "id-token:" not in validation
    assert "contents: write" not in validation
    assert "secrets:" not in validation
    assert "uses: ./.github/workflows/ci.yml" in validation

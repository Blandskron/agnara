"""The moving development image must stay isolated from stable publication."""

from __future__ import annotations

import re
from typing import Any

import yaml

from tests.architecture.boundaries import WORKSPACE_ROOT

WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "container-edge.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(_text())


def _triggers() -> dict[str, Any]:
    # PyYAML's YAML 1.1 loader treats the bare `on` key as True.
    return next(value for key, value in _workflow().items() if key in ("on", True))


def _jobs() -> dict[str, dict[str, Any]]:
    return _workflow()["jobs"]


def _needs(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs", [])
    return {needs} if isinstance(needs, str) else set(needs)


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job.get("steps", [])


def _step_index(job: dict[str, Any], name: str) -> int:
    return next(index for index, step in enumerate(_steps(job)) if step.get("name") == name)


def test_edge_workflow_is_dispatchable_or_automatic_only_for_develop() -> None:
    triggers = _triggers()

    assert set(triggers) == {"workflow_dispatch", "push"}
    assert triggers["push"] == {"branches": ["develop"]}


def test_edge_refusal_happens_before_ci_or_registry_authority() -> None:
    jobs = _jobs()
    preconditions = jobs["preconditions"]

    assert preconditions["permissions"] == {"contents": "read"}
    step = preconditions["steps"][0]
    command = step["run"]
    assert step["env"] == {
        "ACTUAL_REF": "${{ github.ref }}",
        "EXPECTED_REF": "refs/heads/develop",
    }
    assert "refs/heads/develop" in command
    assert "exit 1" in command
    assert _needs(jobs["validate"]) == {"preconditions"}
    assert _needs(jobs["publish"]) == {"preconditions", "validate"}


def test_edge_reuses_ci_and_serializes_moving_tag_updates() -> None:
    jobs = _jobs()

    assert jobs["validate"]["uses"] == "./.github/workflows/ci.yml"
    assert jobs["validate"]["permissions"] == {
        "contents": "read",
        "security-events": "write",
    }
    assert _workflow()["concurrency"] == {
        "group": "container-edge",
        "cancel-in-progress": True,
    }


def test_smoke_succeeds_before_any_registry_login_or_multiarch_push() -> None:
    publish = _jobs()["publish"]

    local_build = _step_index(publish, "Build edge image for smoke test")
    local_smoke = _step_index(publish, "Smoke test edge image before registry login")
    ghcr_login = _step_index(publish, "Log in to GHCR")
    dockerhub_login = _step_index(publish, "Log in to Docker Hub")
    multiarch_push = _step_index(publish, "Build, publish and attest the edge image")

    assert local_build < local_smoke < ghcr_login < multiarch_push
    assert local_smoke < dockerhub_login < multiarch_push
    assert "agnara:edge-smoke" in _steps(publish)[local_build]["run"]
    assert 'OCI_VERSION="edge"' in _steps(publish)[local_build]["run"]


def test_only_edge_is_published_to_both_registries_with_attestations() -> None:
    publish = _jobs()["publish"]
    build = next(step for step in _steps(publish) if step.get("id") == "publish")

    assert publish["permissions"] == {
        "contents": "read",
        "packages": "write",
        "attestations": "write",
        "id-token": "write",
    }
    assert build["uses"] == "docker/build-push-action@0a97817b6ade9f46837855d676c4cca3a2471fc9"
    assert build["with"]["platforms"] == "linux/amd64,linux/arm64"
    assert build["with"]["push"] is True
    # A container repository name must be lowercase. `github.repository_owner`
    # preserves the account's case, so interpolating it directly produced
    # `ghcr.io/Blandskron/agnara:edge` and buildx refused the tag before any
    # push: "invalid tag ... repository name must be lowercase". Every edge
    # publish from `develop` failed that way. The owner is therefore lowercased
    # into a step output first, and this asserts the resulting property rather
    # than one spelling, so the next author cannot reintroduce the raw value.
    tags = build["with"]["tags"].splitlines()
    assert len(tags) == 2
    ghcr_tag, dockerhub_tag = tags
    assert dockerhub_tag == "docker.io/blandskron/agnara:edge"
    assert ghcr_tag.startswith("ghcr.io/")
    assert ghcr_tag.endswith("/agnara:edge")
    assert "github.repository_owner" not in ghcr_tag, (
        "the raw owner preserves case; a container repository name must be lowercase"
    )
    assert build["with"]["sbom"] is True
    assert build["with"]["provenance"] == "mode=max"
    assert "OCI_REVISION=${{ github.sha }}" in build["with"]["build-args"]
    assert (
        "org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}"
        in build["with"]["labels"]
    )
    assert "org.opencontainers.image.version=edge" in build["with"]["labels"]


def test_registry_credentials_are_secret_backed_and_post_push_smoke_is_real() -> None:
    publish = _jobs()["publish"]
    dockerhub_login = _steps(publish)[_step_index(publish, "Log in to Docker Hub")]
    verify = _steps(publish)[_step_index(publish, "Pull both registries and smoke test Docker Hub")]

    assert dockerhub_login["with"] == {
        "username": "${{ secrets.DOCKERHUB_USERNAME }}",
        "password": "${{ secrets.DOCKERHUB_TOKEN }}",
    }
    # Same lowercase rule as the publish tag: `GITHUB_REPOSITORY_OWNER` carries
    # the account's case, so pulling through it would fail even once the push
    # succeeded. What matters is that both registries are really pulled back.
    assert re.search(r'docker pull "ghcr\.io/\$\{\w+\}/agnara:edge"', verify["run"])
    assert "GITHUB_REPOSITORY_OWNER" not in verify["run"], (
        "the raw owner preserves case; pull the lowercased owner instead"
    )
    assert re.search(r'docker pull "?docker\.io/blandskron/agnara:edge"?', verify["run"])
    assert "container_smoke.py docker.io/blandskron/agnara:edge" in verify["run"]
    assert "steps.publish.outputs.digest" in _text()


def test_edge_workflow_cannot_publish_a_release_or_move_latest() -> None:
    workflow = _text()

    for forbidden in ("pypa/", "twine", "git tag", "gh release", ":latest"):
        assert forbidden not in workflow

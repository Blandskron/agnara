"""The release workflow cannot create a tag before publication has been verified.

`0.1.0a4` through `0.1.0a7` each burned a version because the tag was the
trigger: it existed before the first gate ran. These tests hold the shape that
makes that impossible now -- a dispatch from `main`, every gate, a protected
environment, the uploads, the index confirming the files, and only then the
tag and the GitHub Release -- across the three bootstrap phases PyPI's limit
of three pending publishers imposes, and they hold the parts of the old
pipeline that were right: the complete reviewed set, the clean-room install,
the kernel-last upload order and post-publication completeness.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import yaml

from tests.architecture.boundaries import DISTRIBUTIONS, WORKSPACE_ROOT

WORKFLOW = WORKSPACE_ROOT / ".github" / "workflows" / "release.yml"
STATUS = WORKSPACE_ROOT / "docs" / "releases" / "release-status.json"

TAG_JOB = "tag"
GATE_JOB = "publish"
PHASE_UPLOADS = {
    "bootstrap-1": ["publish-a2a", "publish-cli", "publish-events"],
    "bootstrap-2": ["publish-http", "publish-mcp", "publish-telemetry"],
    "final": ["publish-core"],
}
PHASE_VERIFICATION = {
    "bootstrap-1": "verify-bootstrap-1",
    "bootstrap-2": "verify-bootstrap-2",
    "final": "verify-published",
}
UPLOAD_JOBS = [job for jobs in PHASE_UPLOADS.values() for job in jobs]
GATES_BEFORE_PUBLICATION = {
    "validate",
    "preconditions",
    "build",
    "test-artifact",
    "publish-preflight",
}
GATES_BEFORE_THE_TAG = GATES_BEFORE_PUBLICATION | {GATE_JOB, "publish-core", "verify-published"}
UNCONDITIONAL_JOBS = GATES_BEFORE_PUBLICATION | {GATE_JOB}


def _phase_condition(phase: str) -> str:
    return f"${{{{ inputs.phase == '{phase}' }}}}"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(_text())


def _jobs() -> dict[str, dict[str, Any]]:
    return _workflow()["jobs"]


def _triggers() -> dict[str, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True; accept either spelling.
    return next(value for key, value in _workflow().items() if key in ("on", True))


def _job(name: str, until: str | None = None) -> str:
    """One job's YAML body, so a text assertion cannot pass on a different job."""
    body = _text().split(f"  {name}:\n", 1)[1]
    return body.split(f"  {until}:\n", 1)[0] if until else body


def _following(name: str) -> str | None:
    names = list(_jobs())
    index = names.index(name)
    return names[index + 1] if index + 1 < len(names) else None


def _needs(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs", [])
    return {needs} if isinstance(needs, str) else set(needs)


def _transitive_needs(name: str) -> set[str]:
    jobs = _jobs()
    seen: set[str] = set()
    frontier = _needs(jobs[name])
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier |= _needs(jobs[current])
    return seen


def _run_steps(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)]


def _jobs_running(command: str) -> list[str]:
    return [name for name, job in _jobs().items() if any(command in run for run in _run_steps(job))]


def _phase_of(job: dict[str, Any]) -> str | None:
    """The phase a job's `if:` selects, or None for an unconditional job."""
    condition = job.get("if")
    if condition is None:
        return None
    for phase in PHASE_UPLOADS:
        if condition == _phase_condition(phase):
            return phase
    raise AssertionError(f"unexpected condition {condition!r}")


def _jobs_that_run(phase: str, failed: str | None = None) -> set[str]:
    """Simulate GitHub's rules for one dispatch: a job runs when its `if:` selects
    this phase (or it has none) and every job it needs ran and succeeded.

    Those rules hold only while no job carries a status function (`always()`,
    `failure()`, ...) that could override them, which another test asserts.
    """
    jobs = _jobs()
    running: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, job in jobs.items():
            if name in running or name == failed:
                continue
            selected = _phase_of(job) in (None, phase)
            if selected and _needs(job) <= running:
                running.add(name)
                changed = True
    return running


# ---------------------------------------------------------------------------
# How a release starts
# ---------------------------------------------------------------------------


def test_a_release_is_dispatched_and_never_triggered_by_a_pushed_tag() -> None:
    """The trigger that burned four versions no longer exists."""
    triggers = _triggers()

    assert set(triggers) == {"workflow_dispatch"}
    assert triggers["workflow_dispatch"]["inputs"]["version"]["required"] is True
    assert "refs/tags/" not in _text().split("jobs:", 1)[0]


def test_the_phase_is_a_required_choice_of_exactly_the_three_bootstrap_phases() -> None:
    phase = _triggers()["workflow_dispatch"]["inputs"]["phase"]

    assert phase["required"] is True
    assert phase["type"] == "choice"
    assert phase["options"] == list(PHASE_UPLOADS)


def test_a_release_run_cannot_be_cancelled_or_raced_by_another() -> None:
    concurrency = _workflow()["concurrency"]

    assert concurrency == {"group": "release", "cancel-in-progress": False}


def test_the_dispatched_inputs_reach_shell_steps_only_through_the_environment() -> None:
    """An expression interpolated into a `run:` is a script injection waiting for input.

    The dispatched version and phase, and everything derived from them, reach
    a shell only as `$RELEASE_VERSION` and `$RELEASE_PHASE`; no `run:` step
    interpolates any `${{ }}`.
    """
    env = _workflow()["env"]
    assert env["RELEASE_VERSION"] == "${{ inputs.version }}"
    assert env["RELEASE_PHASE"] == "${{ inputs.phase }}"
    for name, job in _jobs().items():
        for run in _run_steps(job):
            assert "${{" not in run, name
            assert "inputs." not in run, name


# ---------------------------------------------------------------------------
# What must hold before anything is built
# ---------------------------------------------------------------------------


def test_preconditions_guard_the_branch_the_head_the_tag_the_phase_and_the_human_gate() -> None:
    body = _job("preconditions", "build")

    assert "scripts/check_release_preconditions.py" in body
    assert "--require-protected-environment pypi" in body
    assert 'set_workspace_version.py release "$RELEASE_VERSION" --check' in body
    assert "uv lock --check" in body
    assert "check_publication_readiness.py" in body
    assert '--phase "$RELEASE_PHASE" --oidc-identity' in body
    assert "fetch-depth: 0" in body


def test_preconditions_are_rechecked_before_the_human_gate_and_after_it() -> None:
    """Time passes while the gates run; `main` may move and a tag may appear."""
    rechecked = _jobs_running("scripts/check_release_preconditions.py")

    assert rechecked == ["preconditions", "publish-preflight", GATE_JOB, *UPLOAD_JOBS, TAG_JOB]
    for name in ("preconditions", "publish-preflight", GATE_JOB, *UPLOAD_JOBS):
        assert "--require-protected-environment pypi" in _job(name, _following(name)), name
    # After publication the index already holds the release, so the tag job
    # requires the dispatched commit and an absent tag, but not a still `main`.
    assert "--after-publication" in _job(TAG_JOB, "github-release")


# ---------------------------------------------------------------------------
# Phases: the only conditions in the workflow select one
# ---------------------------------------------------------------------------


def test_the_only_conditions_select_a_phase_and_every_gate_is_unconditional() -> None:
    jobs = _jobs()

    for name in UNCONDITIONAL_JOBS:
        assert "if" not in jobs[name], f"{name} must run in every phase"
    for phase, uploads in PHASE_UPLOADS.items():
        for name in [*uploads, PHASE_VERIFICATION[phase]]:
            assert jobs[name]["if"] == _phase_condition(phase), name
    for name in (TAG_JOB, "github-release"):
        assert jobs[name]["if"] == _phase_condition("final"), name
    for name, job in jobs.items():
        _phase_of(job)  # raises on any other shape of condition
        assert "continue-on-error" not in job, name
        for step in job.get("steps", []):
            assert "continue-on-error" not in step, name
    for expression in ("always()", "failure()", "cancelled()", "success()"):
        assert expression not in _text(), expression


def test_bootstrap_1_publishes_exactly_a2a_cli_and_events_and_verifies_them() -> None:
    running = _jobs_that_run("bootstrap-1")

    assert running == UNCONDITIONAL_JOBS | {*PHASE_UPLOADS["bootstrap-1"], "verify-bootstrap-1"}
    assert TAG_JOB not in running
    assert "github-release" not in running
    assert not any("git tag" in run for name in running for run in _run_steps(_jobs()[name]))


def test_bootstrap_2_publishes_exactly_http_mcp_and_telemetry_and_verifies_the_adapters() -> None:
    running = _jobs_that_run("bootstrap-2")

    assert running == UNCONDITIONAL_JOBS | {*PHASE_UPLOADS["bootstrap-2"], "verify-bootstrap-2"}
    assert not running & set(PHASE_UPLOADS["bootstrap-1"]), "bootstrap-1 is never re-published"
    assert TAG_JOB not in running
    assert "github-release" not in running


def test_the_final_phase_publishes_only_the_kernel_then_verifies_tags_and_announces() -> None:
    running = _jobs_that_run("final")

    assert running == UNCONDITIONAL_JOBS | {
        "publish-core",
        "verify-published",
        TAG_JOB,
        "github-release",
    }
    assert not running & set(PHASE_UPLOADS["bootstrap-1"] + PHASE_UPLOADS["bootstrap-2"])


def test_every_phase_verifies_its_publication_with_the_phase_aware_check() -> None:
    for phase, verification in PHASE_VERIFICATION.items():
        body = _job(verification, _following(verification))
        assert '--phase "$RELEASE_PHASE" --online --require-published' in body, phase
        assert _needs(_jobs()[verification]) == {"preconditions", PHASE_UPLOADS[phase][-1]}
    # A bootstrap phase cannot install: the adapters pin a kernel that is not
    # on the index yet. Only the final verification installs the published set.
    for phase in ("bootstrap-1", "bootstrap-2"):
        assert "uv pip install" not in _job(
            PHASE_VERIFICATION[phase], _following(PHASE_VERIFICATION[phase])
        )
    assert 'uv pip install --python "$RELEASE_PYTHON" "${pinned[@]}"' in _job(
        "verify-published", TAG_JOB
    )


def test_each_upload_job_belongs_to_exactly_one_phase_in_publication_order() -> None:
    jobs = _jobs()
    for phase, uploads in PHASE_UPLOADS.items():
        previous = GATE_JOB
        for name in uploads:
            job = jobs[name]
            suffix = name.removeprefix("publish-")
            project = "agnara" if suffix == "core" else "agnara-" + suffix
            environment = "pypi-" + suffix
            assert _phase_of(job) == phase
            assert _needs(job) == {"preconditions", previous}
            assert name not in _transitive_needs(name), "release graph must be acyclic"
            assert _transitive_needs(name) >= GATES_BEFORE_PUBLICATION | {GATE_JOB}
            assert "uses" not in job, "Trusted Publishing must stay in release.yml"
            assert job["environment"]["name"] == environment
            assert job["env"] == {"PUBLISH_PROJECT": project, "PUBLISH_ENVIRONMENT": environment}
            uploads_steps = [
                step for step in job["steps"] if str(step.get("uses", "")).startswith("pypa/")
            ]
            assert len(uploads_steps) == 1
            assert uploads_steps[0]["with"]["packages-dir"] == "staged/" + project
            runs = "\n".join(_run_steps(job))
            assert '--project "$PUBLISH_PROJECT" --environment "$PUBLISH_ENVIRONMENT"' in runs
            assert '--phase "$RELEASE_PHASE" --dist dist/ --oidc-identity' in runs
            assert 'cp "dist/${stem}-${RELEASE_VERSION}-py3-none-any.whl"' in runs
            assert 'cp "dist/${stem}-${RELEASE_VERSION}.tar.gz"' in runs
            assert "--online" not in runs, "an upload must not fail on files earlier jobs created"
            previous = name


# ---------------------------------------------------------------------------
# The order: publish, verify, then tag, then announce
# ---------------------------------------------------------------------------


def test_the_human_gate_is_the_upload_and_only_the_upload() -> None:
    jobs = _jobs()
    gated = [name for name, job in jobs.items() if isinstance(job.get("environment"), dict)]

    assert gated == [GATE_JOB, *UPLOAD_JOBS]
    assert jobs[GATE_JOB]["environment"]["name"] == "pypi"
    assert _transitive_needs(GATE_JOB) >= GATES_BEFORE_PUBLICATION
    assert jobs[GATE_JOB]["permissions"] == {"contents": "read"}
    for name in UPLOAD_JOBS:
        assert jobs[name]["permissions"] == {"id-token": "write", "contents": "read"}


def test_publication_happens_before_the_tag() -> None:
    """No tag exists while the uploads run: no publishing job can create one
    and the tag job cannot start until the kernel has been published."""
    jobs = _jobs()

    assert {GATE_JOB, "publish-core"} <= _transitive_needs(TAG_JOB)
    assert TAG_JOB not in _transitive_needs(GATE_JOB)
    for name in (GATE_JOB, *UPLOAD_JOBS):
        assert not any("git tag" in run for run in _run_steps(jobs[name])), name
        assert "--tag" not in _job(name, _following(name)), name


def test_verification_happens_before_the_tag() -> None:
    """Completeness on the index -- wheel and sdist for all seven -- is what the tag records."""
    jobs = _jobs()

    assert "verify-published" in _needs(jobs[TAG_JOB])
    assert "publish-core" in _needs(jobs["verify-published"])
    assert "--online --require-published" in _job("verify-published", TAG_JOB)
    assert TAG_JOB not in _transitive_needs("verify-published")


def test_the_tag_depends_on_verification_success_and_exists_only_in_the_final_phase() -> None:
    jobs = _jobs()

    assert _transitive_needs(TAG_JOB) >= GATES_BEFORE_THE_TAG
    assert _phase_of(jobs[TAG_JOB]) == "final"
    assert _phase_of(jobs["github-release"]) == "final"
    for phase in ("bootstrap-1", "bootstrap-2"):
        assert TAG_JOB not in _jobs_that_run(phase), phase


def test_a_failed_upload_or_verification_leaves_no_tag() -> None:
    """The critical rule, read off the dependency graph for every phase: if the
    gate, any upload or any verification fails, neither `tag` nor
    `github-release` runs, and nothing that runs can create a tag."""
    for phase, uploads in PHASE_UPLOADS.items():
        for failed in (GATE_JOB, *uploads, PHASE_VERIFICATION[phase]):
            running = _jobs_that_run(phase, failed=failed)
            assert TAG_JOB not in running, (phase, failed)
            assert "github-release" not in running, (phase, failed)
            assert not any(
                "git tag" in run for name in running for run in _run_steps(_jobs()[name])
            ), (phase, failed)


def test_only_the_tag_job_creates_the_tag() -> None:
    """One job tags, it holds nothing but `contents: write`, and nothing else pushes."""
    jobs = _jobs()

    assert _jobs_running("git tag ") == [TAG_JOB]
    assert _jobs_running("git push") == [TAG_JOB]
    assert jobs[TAG_JOB]["permissions"] == {"contents": "write"}
    assert "environment" not in jobs[TAG_JOB], "the tag is a consequence, not a decision"
    assert "id-token" not in jobs[TAG_JOB]["permissions"]


def test_the_tag_is_created_after_the_recheck_and_verified_after_creation() -> None:
    steps = [step.get("run", "") for step in _jobs()[TAG_JOB]["steps"]]
    recheck = next(i for i, run in enumerate(steps) if "check_release_preconditions.py" in run)
    tagging = next(i for i, run in enumerate(steps) if "git tag " in run)
    verification = next(i for i, run in enumerate(steps) if "check_release_tag.py" in run)

    assert recheck < tagging < verification
    assert 'git tag -a "$tag" "$GITHUB_SHA"' in steps[tagging]
    assert 'git push origin "refs/tags/${tag}"' in steps[tagging]


def test_the_tag_is_annotated_and_names_the_dispatched_commit() -> None:
    body = _job(TAG_JOB, "github-release")

    assert "git tag -a" in body
    assert '"$GITHUB_SHA"' in body
    assert "github-actions[bot]" in body
    assert "fetch-depth: 0" in body


def test_the_github_release_depends_on_the_tag() -> None:
    jobs = _jobs()
    needs = _needs(jobs["github-release"])

    assert {TAG_JOB, "verify-published", "publish-core"} <= needs
    checkout = jobs["github-release"]["steps"][0]
    assert checkout["with"]["ref"] == f"${{{{ needs.{TAG_JOB}.outputs.tag }}}}"
    release_step = jobs["github-release"]["steps"][-1]
    assert release_step["with"]["tag_name"] == f"${{{{ needs.{TAG_JOB}.outputs.tag }}}}"
    assert release_step["with"]["body_path"].startswith("docs/releases/")
    assert "contents: write" in _job("github-release")


def test_the_current_target_is_not_tagged_ahead_of_the_workflow() -> None:
    """The tag for the release being prepared is created by the workflow, or not at all."""
    document = json.loads(STATUS.read_text(encoding="utf-8"))
    target = document["current_target"]
    listed = subprocess.run(
        ["git", "tag", "--list", f"v{target}"],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    if listed:
        # The tag may legitimately exist once the release has been published
        # and the record moved on; then the status file must say so.
        assert document["previous_release"] == target, (
            f"v{target} exists but release-status.json still prepares {target}; a tag must be "
            "created only by the release run after verified publication, never ahead of it"
        )


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


def test_every_upload_revalidates_the_bundle_before_uploading() -> None:
    for name in UPLOAD_JOBS:
        body = _job(name, _following(name))
        recheck = body.index("scripts/check_release_preconditions.py")
        download = body.index("actions/download-artifact@")
        bundle = body.index("--dist dist/ --oidc-identity")
        upload = body.index("pypa/gh-action-pypi-publish@")

        assert recheck < download < bundle < upload, name


def test_publish_readiness_is_checked_at_every_state_of_the_release() -> None:
    """Before the build, against the built set, against the index, against the
    downloaded bundle, and after publication where the claim is completeness --
    always for the dispatched phase."""
    for job, until, expected in (
        ("preconditions", "build", '--phase "$RELEASE_PHASE" --oidc-identity'),
        ("build", "test-artifact", '--phase "$RELEASE_PHASE" --dist dist/'),
        ("publish-preflight", GATE_JOB, '--phase "$RELEASE_PHASE" --online --oidc-identity'),
        ("publish-a2a", "publish-cli", '--phase "$RELEASE_PHASE" --dist dist/ --oidc-identity'),
        (
            "verify-bootstrap-1",
            "publish-http",
            '--phase "$RELEASE_PHASE" --online --require-published',
        ),
        ("verify-published", TAG_JOB, '--phase "$RELEASE_PHASE" --online --require-published'),
    ):
        body = _job(job, until)
        assert "scripts/check_publication_readiness.py" in body, job
        assert expected in body, job


def test_publication_steps_name_canonical_projects_never_normalized_filenames() -> None:
    """`staged/agnara-a2a`, never `staged/agnara_a2a`: the directory is the project."""
    published = [
        step["with"]["packages-dir"].removeprefix("staged/")
        for name in UPLOAD_JOBS
        for step in _jobs()[name]["steps"]
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish")
    ]

    assert sorted(published) == sorted(DISTRIBUTIONS)
    assert all("_" not in name for name in published)


def test_the_workflow_never_edits_the_publication_record() -> None:
    """A run that could write `publication.json` could certify itself."""
    for name, job in _jobs().items():
        for run in _run_steps(job):
            assert "publication.json" not in run, name


def test_post_release_verification_covers_every_distribution() -> None:
    """Completeness on the index, then a real install of the published set.

    `0.1.0a4` published a wheel with no sdist. Installing it would have
    succeeded, so verification asserts what is on the index as well as what can
    be installed from it.
    """
    verification = _job("verify-published", TAG_JOB)

    assert "--online --require-published" in verification
    assert 'manifest --pinned "$version"' in verification
    assert 'uv pip install --python "$RELEASE_PYTHON" "${pinned[@]}"' in verification
    assert "manifest --import-names" in verification
    # Derived, so a new distribution is covered without editing this file.
    assert not any(f"{distribution}==" in verification for distribution in DISTRIBUTIONS)


# ---------------------------------------------------------------------------
# What the old pipeline got right, kept
# ---------------------------------------------------------------------------


def test_release_builds_and_validates_the_complete_workspace() -> None:
    workflow = _text()

    assert "uv build --all-packages --out-dir dist/" in workflow
    assert "scripts/check_distributions.py" in workflow
    assert "--dist dist/" in workflow
    assert "--expected-version" in workflow
    assert "uv build --package agnara" not in workflow


def test_release_install_cannot_substitute_a_public_first_party_package() -> None:
    """Third-party first, then the candidate wheels with the index closed.

    Which third-party requirements those are is read from
    `docs/distributions.json` rather than repeated here, so an adapter that
    gains a dependency cannot leave a stale copy behind in the workflow.
    """
    workflow = _text()

    third_party = workflow.index('uv pip install --python "$SMOKE_PYTHON" "${third_party[@]}"')
    first_party = workflow.index('--no-index --find-links "$GITHUB_WORKSPACE/dist"')
    installed_gate = workflow.index("--require-installed")

    assert third_party < first_party < installed_gate
    assert '"${#wheels[@]}" -ne "$expected_count"' in workflow
    assert 'expected_count="$(manifest --count)"' in workflow
    assert '"$SMOKE_PYTHON" -I' in workflow


def test_publication_is_attested_and_metadata_verified() -> None:
    workflow = _text()

    assert "id-token: write" in workflow
    assert "attestations: true" in workflow
    assert "verify-metadata: true" in workflow
    assert "print-hash: true" in workflow
    for name in UPLOAD_JOBS:
        for step in _jobs()[name]["steps"]:
            assert "skip-existing" not in (step.get("with") or {})


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
    validation = _job("validate", "preconditions")
    assert "      contents: read\n      security-events: write" in validation
    assert "id-token:" not in validation
    assert "contents: write" not in validation
    assert "secrets:" not in validation
    assert "uses: ./.github/workflows/ci.yml" in validation

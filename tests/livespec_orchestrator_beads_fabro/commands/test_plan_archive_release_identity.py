"""The archive gate's release-identity rule, against a REAL tagged repository.

Binds the third assertion of `bd-ib-wbdgil` and the plan-record clause of
`SPECIFICATION/contracts.md` (v115): "where a release applies to the plan's work
— the governed repository carries at least one release tag — a `captured` record
taken against an unreleased tree is not evidence ... and the archive gate MUST
reject a record that states `release: none` for such a repository, or names a
release tag the repository does not carry, naming the missing release identity."

WHY THIS IS DRIVEN THROUGH `archive_thread` AND NOT THE PURE LEG. The pure
decision is exercised by `test_plan_proof_leg`, which hands it a tag set
directly. What that cannot show is that the GATE reads the repository's own tags:
a build that passed an empty set would satisfy every case over there, admit
every `release: none` record here, and look identical from the leg's side. So the
plan lives in a real `git init` repository and the tag is created with `git tag`.

EVERY CASE CARRIES THE ARCHIVE THAT SUCCEEDS. A gate that rejected every record
would satisfy both refusals on its own, and would make the ratified remedy —
republish naming the release exercised — unreachable. The admitted case is the
same plan, the same assertion and the same publisher, differing only in the
release tag the record names.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_leg import (
    NOT_EVIDENCE_NO_RELEASE,
    NOT_EVIDENCE_UNKNOWN_RELEASE,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_tags import (
    repository_release_tags,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    PlanArchiveRefusedError,
    archive_thread,
    create_thread,
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_SLUG = "release-identity-thread"
_ASSERTION = "The released build runs in a real operator session."
_TAG = "v0.167.0"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


def _released_repository(*, repo: Path) -> None:
    """A real repository carrying one release tag — the clause's own condition."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(cwd=repo, args=["init", "--quiet"])
    _git(cwd=repo, args=["config", "user.email", "fixture@example.invalid"])
    _git(cwd=repo, args=["config", "user.name", "Fixture"])
    _ = (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(cwd=repo, args=["add", "README.md"])
    _git(cwd=repo, args=["commit", "--quiet", "--no-verify", "-m", "chore: fixture"])
    _git(cwd=repo, args=["tag", _TAG])
    # The precondition, measured rather than assumed: a gate reading an empty set
    # would admit every record below and this module would prove nothing.
    assert repository_release_tags(project_root=repo) == frozenset({_TAG})


def _record(*, epic_id: str, verdict: str, identity: str, release: str | None) -> None:
    _fake().add_comment(
        issue_id=epic_id,
        body=render_proof_record(
            title=PLAN_PROOF_RECORD_TITLE,
            verdict=verdict,
            identity=f"session {identity}",
            timestamp="2026-10-05T01:00:00Z",
            build=BuildIdentity(release_tag=release, installed_build=None, commit="c0ffee1"),
            assertions=(
                RecordAssertion(
                    text=_ASSERTION,
                    proof_mode=PROOF_MODE_HOST_CAPTURED,
                    governing_scenario=None,
                    steps=("Install the released build.", "Run it in a real session."),
                    proof="$ delivered --version\n0.167.0",
                    reproduced=None if verdict == VERDICT_CAPTURED else True,
                ),
            ),
        ),
    )


def _plan_ready_to_archive(*, repo: Path) -> str:
    """A plan whose child and completeness legs pass, so only proof is left."""
    created = create_thread(
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        title="Release identity thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-05T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the released build has been run in a real session.",
            assertions=(_ASSERTION,),
        ),
    )
    record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="review-evidence-1",
        reviewer_identity="fresh-independent-reviewer",
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="Every requirement carrier under the plan is covered.",
        now="2026-10-05T00:30:00Z",
    )
    return created["epic_id"]


def _archive(*, repo: Path, epic_id: str) -> dict[str, str]:
    return archive_thread(
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        epic_id=epic_id,
        completeness_review_comment_id="review-evidence-1",
    )


@pytest.mark.parametrize(
    ("release", "reason"),
    [
        (None, NOT_EVIDENCE_NO_RELEASE),
        ("v9.9.9", NOT_EVIDENCE_UNKNOWN_RELEASE),
    ],
    ids=["states-release-none", "names-an-unknown-tag"],
)
def test_the_gate_rejects_a_record_whose_release_identity_the_repository_denies(
    tmp_path: Path, release: str | None, reason: str
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "released"
    _released_repository(repo=repo)
    epic_id = _plan_ready_to_archive(repo=repo)
    _record(epic_id=epic_id, verdict=VERDICT_CAPTURED, identity="capturing", release=release)
    _record(epic_id=epic_id, verdict=VERDICT_VERIFIED, identity="replaying", release=release)

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(repo=repo, epic_id=epic_id)

    message = str(refused.value)
    # Both halves: the assertion that went unproved, and WHY the record that was
    # published for it was not evidence. Without the second half an operator who
    # did publish cannot see that their record was read and refused.
    assert _ASSERTION in message
    assert reason in message
    assert (repo / "plan" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"


def test_the_gate_admits_a_record_naming_the_release_the_repository_carries(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "released"
    _released_repository(repo=repo)
    epic_id = _plan_ready_to_archive(repo=repo)
    _record(epic_id=epic_id, verdict=VERDICT_CAPTURED, identity="capturing", release=_TAG)
    _record(epic_id=epic_id, verdict=VERDICT_VERIFIED, identity="replaying", release=_TAG)

    result = _archive(repo=repo, epic_id=epic_id)

    assert result["archive_path"] == f"plan/archive/{_SLUG}"
    assert _fake().show_issue(issue_id=epic_id)["status"] == "closed"

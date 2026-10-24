"""Scenario 55 — plan archive commissions a missing completeness review.

Exercises the real archive entry point against the hermetic ledger client.  The
first archive attempt has no evidence, so it must commission the supplied
reviewer and leave both the plan directory and epic untouched.  A later durable
record explicitly declines to attest every research requirement, including a
deferral, and is likewise insufficient.  Only an independent, current record
that attests the complete requirement set authorizes the archive.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
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
from livespec_orchestrator_beads_fabro.commands._plan_archive import archive_thread
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
)
from livespec_orchestrator_beads_fabro.commands._plan_archive_review import (
    ArchiveCompletenessReviewRequest,
    CompletenessReviewLauncher,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    governed_repository_argv,
)
from livespec_orchestrator_beads_fabro.commands.plan import create_thread
from livespec_orchestrator_beads_fabro.types import StoreConfig

_SLUG = "scenario-55-completeness-review"
_ASSERTION = "The archive happens only after a complete independent review."
_ARCHIVING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "scenario-55-archiver"}
_REVIEWING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "scenario-55-reviewer"}


@pytest.fixture(autouse=True)
def hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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


def _plan(*, project_root: Path) -> str:
    created = create_thread(
        project_root=project_root,
        config=_config(),
        slug=_SLUG,
        title="Scenario 55 completeness review",
        research_filename="requirements.md",
        research_text=(
            "Requirement: independently review every research requirement.\n"
            "Deferral: defer the remote audit until the carrier is available.\n"
        ),
        now="2026-10-24T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when archive follows a complete independent review.",
            assertions=(_ASSERTION,),
        ),
    )
    _seed_plan_proof(epic_id=created["epic_id"])
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-scenario55-child",
            issue_type="task",
            title="Complete the review carrier",
            description="The sole plan child is disposed before archive.",
            assignee=None,
            created_at="2026-10-24T00:10:00Z",
            parent_id=created["epic_id"],
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )
    _fake().close_issue(issue_id="bd-ib-scenario55-child", reason="completed")
    return created["epic_id"]


def _seed_plan_proof(*, epic_id: str) -> None:
    for verdict, identity, reproduced in (
        (VERDICT_CAPTURED, "session scenario-55-capture", None),
        (VERDICT_VERIFIED, "session scenario-55-replay", True),
    ):
        _fake().add_comment(
            issue_id=epic_id,
            body=render_proof_record(
                title=PLAN_PROOF_RECORD_TITLE,
                verdict=verdict,
                identity=identity,
                timestamp="2026-10-24T01:00:00Z",
                build=BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
                assertions=(
                    RecordAssertion(
                        text=_ASSERTION,
                        proof_mode=PROOF_MODE_HOST_CAPTURED,
                        governing_scenario=None,
                        steps=("Run the archive operation after review.",),
                        proof="$ archive --check\nready",
                        reproduced=reproduced,
                    ),
                ),
            ),
        )


def _archive(
    *,
    project_root: Path,
    epic_id: str,
    evidence_id: str | None,
    review_launcher: CompletenessReviewLauncher | None = None,
) -> dict[str, str]:
    return archive_thread(
        project_root=project_root,
        config=_config(),
        slug=_SLUG,
        epic_id=epic_id,
        completeness_review_comment_id=evidence_id,
        review_launcher=review_launcher,
        env=_ARCHIVING_SESSION_ENV,
        runner=_UnreleasedForge(),
    )


class _UnreleasedForge:
    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        if argv == governed_repository_argv():
            return CommandResult(exit_code=0, stdout="thewoolleyman/livespec", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def test_scenario55_archive_commissions_and_requires_complete_durable_review(
    tmp_path: Path,
) -> None:
    epic_id = _plan(project_root=tmp_path)
    commissioned: list[ArchiveCompletenessReviewRequest] = []

    def launch_fresh_reviewer(*, request: ArchiveCompletenessReviewRequest) -> str | None:
        commissioned.append(request)
        return None

    with pytest.raises(PlanArchiveRefusedError, match="completeness-review evidence"):
        _ = _archive(
            project_root=tmp_path,
            epic_id=epic_id,
            evidence_id=None,
            review_launcher=launch_fresh_reviewer,
        )

    assert len(commissioned) == 1
    assert commissioned[0].child_ids == ("bd-ib-scenario55-child",)
    assert commissioned[0].research_paths == (f"plan/{_SLUG}/research/requirements.md",)
    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert not (tmp_path / "plan" / "archive" / _SLUG).exists()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"

    record_completeness_review_evidence(
        config=_config(),
        epic_id=epic_id,
        evidence_id="review-missing-deferral",
        reviewed_child_ids=("bd-ib-scenario55-child",),
        separate_reviewer=True,
        attests_complete_requirement_coverage=False,
        body=(
            "The primary requirement has a carrier, but the deferred remote audit "
            "does not; this review does not attest complete coverage."
        ),
        now="2026-10-24T02:00:00Z",
        env=_REVIEWING_SESSION_ENV,
    )

    with pytest.raises(PlanArchiveRefusedError, match="completeness-review evidence"):
        _ = _archive(
            project_root=tmp_path,
            epic_id=epic_id,
            evidence_id="review-missing-deferral",
        )

    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"

    record_completeness_review_evidence(
        config=_config(),
        epic_id=epic_id,
        evidence_id="review-covers-all-requirements",
        reviewed_child_ids=("bd-ib-scenario55-child",),
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="Every research requirement and the deferred remote audit have ledger carriers.",
        now="2026-10-24T02:10:00Z",
        env=_REVIEWING_SESSION_ENV,
    )

    archived = _archive(
        project_root=tmp_path,
        epic_id=epic_id,
        evidence_id="review-covers-all-requirements",
    )

    assert archived["archive_path"] == f"plan/archive/{_SLUG}"
    assert not (tmp_path / "plan" / _SLUG).exists()
    assert (tmp_path / "plan" / "archive" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] == "closed"

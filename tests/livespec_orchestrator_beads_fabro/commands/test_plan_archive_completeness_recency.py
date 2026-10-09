"""The completeness leg's scope binding: evidence covers the child set it NAMED.

Work-item `bd-ib-0pf5`. Until this landed, the leg field-matched an evidence
comment's id, its reviewer identity and its two self-declared booleans, and
nothing else — so a comment of ANY age satisfied the archive gate forever.

Measured on plan epic `bd-ib-l3nptz` on 2026-08-22, by execution rather than by
source reading: evidence recorded 2026-08-17 still validated five days later,
against the live store, on the shipped code path, after children `.10` through
`.16` plus a sibling epic had landed — work spanning four repositories and
roughly a dozen merged pull requests, none of which its reviewer ever saw. The
archive that would have passed on it was averted by a session recognising the
trap and declining to ride evidence it could legitimately have passed, not by the
gate. A control whose correct result depends entirely on nobody exercising the
option it leaves open is not a control.

EVERY CASE HERE IS DRIVEN THROUGH THE PLAN PACKAGE'S OWN ARCHIVE ENTRY POINT
against the fake ledger store, because the defect was in what the GATE accepts
rather than in any one predicate: a test grading the parse alone would pass
against the very build the defect was measured on. The pure decisions behind it
have their own edge coverage in `test_plan_completeness_recency.py`.
"""

from __future__ import annotations

import importlib
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
    CompletenessReviewEvidenceFields,
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands.plan import create_thread
from livespec_orchestrator_beads_fabro.types import StoreConfig

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_RECENCY_MODULE = "livespec_orchestrator_beads_fabro.commands._plan_completeness_recency"
# The two parties to the leg, each expressed as the session that computes its own
# identity — there is no field a caller can put a name in.
_ARCHIVING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "archiving-session"}
_REVIEWING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "reviewing-session"}
_SLUG = "recency-thread"
_ASSERTION = "The operator drives the delivered command and sees it work."


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
    """A fresh plan whose proof leg is already satisfied, so only this leg decides."""
    reset_fake_singleton()
    created = create_thread(
        project_root=project_root,
        config=_config(),
        slug=_SLUG,
        title="Recency thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-08T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=(_ASSERTION,),
        ),
    )
    _seed_plan_proof(epic_id=created["epic_id"])
    return created["epic_id"]


def _child(*, epic_id: str, child_id: str, created_at: str) -> None:
    """One disposed plan child, linked by the `parent-child` edge the gate reads."""
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=child_id,
            issue_type="task",
            title="child",
            description="child work",
            assignee=None,
            created_at=created_at,
            parent_id=epic_id,
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )
    _fake().close_issue(issue_id=child_id, reason="completed")


def _seed_plan_proof(*, epic_id: str) -> None:
    """The captured/verified plan record pair the archive proof leg needs.

    Rendered through the PRODUCTION renderer rather than hand-written, because the
    proof gate reads the same bytes the posting primitive publishes.
    """
    for verdict, identity, reproduced in (
        (VERDICT_CAPTURED, "session capturing-session", None),
        (VERDICT_VERIFIED, "session replaying-session", True),
    ):
        _fake().add_comment(
            issue_id=epic_id,
            body=render_proof_record(
                title=PLAN_PROOF_RECORD_TITLE,
                verdict=verdict,
                identity=identity,
                timestamp="2026-10-08T01:00:00Z",
                build=BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
                assertions=(
                    RecordAssertion(
                        text=_ASSERTION,
                        proof_mode=PROOF_MODE_HOST_CAPTURED,
                        governing_scenario=None,
                        steps=("Run the delivered command on the operator host.",),
                        proof="$ delivered --version\n0.1.0",
                        reproduced=reproduced,
                    ),
                ),
            ),
        )


def _record_evidence(
    *,
    epic_id: str,
    evidence_id: str,
    reviewed_child_ids: tuple[str, ...],
    now: str,
) -> None:
    record_completeness_review_evidence(
        config=_config(),
        epic_id=epic_id,
        evidence_id=evidence_id,
        env=_REVIEWING_SESSION_ENV,
        reviewed_child_ids=reviewed_child_ids,
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="All research requirements and deferrals have ledger carriers.",
        now=now,
    )


def _legacy_evidence(*, epic_id: str, evidence_id: str, now: str) -> None:
    """Evidence in the format that shipped BEFORE the scope binding existed.

    This is the `bd-ib-l3nptz` comment's own shape: fully attesting, independently
    authored, well-formed — and naming no scope at all, which is why the shipped
    gate could not tell it apart from a review of the plan in front of it.
    """
    _fake().seed_comment(
        issue_id=epic_id,
        text=(
            "plan-completeness-review-evidence\n"
            f"evidence-id: {evidence_id}\n"
            "reviewer-identity: reviewing-session\n"
            "separate-reviewer: true\n"
            "attests-complete-requirement-coverage: true\n"
            f"timestamp: {now}\n\n"
            "All research requirements and deferrals have ledger carriers."
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
    )


def test_evidence_is_accepted_only_when_it_names_the_epics_current_child_set(
    tmp_path: Path,
) -> None:
    """The record NAMES the scope it reviewed, and acceptance requires that scope.

    The payload-grammar assertion is the load-bearing half, and it is the reason
    the fix is not simply a stricter predicate: an evidence record that names no
    child set cannot be compared against anything, so no amount of grading at
    archive time can tell a review of THIS plan from a review of an earlier one.
    The writer has to record what it covered before the reader can check it.

    The pair is what discriminates. Both comments below are independent, fully
    attesting and well-formed; they differ in nothing but whether they name the
    one child the epic currently carries. Against the shipped build both are
    accepted, because the scope is a field it never read.
    """
    module_path = _COMMANDS / "_plan_completeness_recency.py"

    assert module_path.is_file()

    recency = importlib.import_module(_RECENCY_MODULE)
    assert "stale_evidence_report" in recency.__all__
    assert "reviewed_child_ids" in CompletenessReviewEvidenceFields.__annotations__

    epic_id = _plan(project_root=tmp_path)
    _child(epic_id=epic_id, child_id="bd-ib-recency-a", created_at="2026-10-08T00:10:00Z")
    _legacy_evidence(epic_id=epic_id, evidence_id="legacy-review", now="2026-10-08T02:00:00Z")
    _record_evidence(
        epic_id=epic_id,
        evidence_id="scoped-review",
        reviewed_child_ids=("bd-ib-recency-a",),
        now="2026-10-08T02:00:00Z",
    )

    with pytest.raises(PlanArchiveRefusedError):
        _ = _archive(project_root=tmp_path, epic_id=epic_id, evidence_id="legacy-review")

    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"

    accepted = _archive(project_root=tmp_path, epic_id=epic_id, evidence_id="scoped-review")

    assert accepted["archive_path"] == f"plan/archive/{_SLUG}"
    assert _fake().show_issue(issue_id=epic_id)["status"] == "closed"


def test_a_stale_scope_is_reported_as_stale_and_names_what_changed(tmp_path: Path) -> None:
    """The refusal NAMES each child added and each child removed since the review.

    A generic "evidence is required" here is actively harmful, and that is why
    this is a separate refusal rather than stricter grading: the evidence IS on
    the timeline, independently authored and fully attesting, so its reader goes
    hunting for a record that is already there. Worse, the reader cannot tell
    whether the remedy is to review work nobody has reviewed or to re-read a plan
    whose carriers moved — so a reviewer re-issues the same record and the
    refusal becomes a retry loop.

    Both directions are present in one setup because they are different
    omissions. `bd-ib-recency-c` is work that landed after the attestation;
    `bd-ib-recency-a` is a carrier the attestation counted that the plan no
    longer has.
    """
    epic_id = _plan(project_root=tmp_path)
    _child(epic_id=epic_id, child_id="bd-ib-recency-b", created_at="2026-10-08T00:10:00Z")
    _child(epic_id=epic_id, child_id="bd-ib-recency-c", created_at="2026-10-08T00:20:00Z")
    _record_evidence(
        epic_id=epic_id,
        evidence_id="drifted-review",
        reviewed_child_ids=("bd-ib-recency-a", "bd-ib-recency-b"),
        now="2026-10-08T02:00:00Z",
    )

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(project_root=tmp_path, epic_id=epic_id, evidence_id="drifted-review")

    message = str(refused.value)
    assert "drifted-review" in message
    assert "stale" in message
    added, _, removed = message.partition("removed")
    assert "bd-ib-recency-c" in added
    assert "bd-ib-recency-a" in removed
    # The child the review DID cover is not named: a refusal that listed the whole
    # current set would read as though the review had covered none of it.
    assert "bd-ib-recency-b" not in message
    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"


def test_evidence_predating_a_childs_status_change_is_stale_with_the_child_and_instant(
    tmp_path: Path,
) -> None:
    """The set can match exactly and the review still not cover the plan.

    This is the arm the set comparison structurally CANNOT catch, and it is why
    the leg needs a second measurement rather than a stricter first one. The
    membership here is precisely what the record names, so the set test passes —
    yet the child's own record places its earliest status transition three hours
    AFTER the attestation was written, which means the reviewer cannot have read
    it whatever its scope list says.

    That matters because the scope list is SELF-DECLARED, exactly like the two
    attestations beside it. A set comparison on its own is therefore defeated by
    a record that simply names the right ids; the ledger's own instants are the
    part its author does not control.

    The refusal NAMES the child and the instant rather than reporting staleness
    in the abstract: a reviewer told only that its record is out of date has to
    diff the whole plan to find out which child moved underneath it.
    """
    epic_id = _plan(project_root=tmp_path)
    _child(epic_id=epic_id, child_id="bd-ib-recency-e", created_at="2026-10-08T05:00:00Z")
    _record_evidence(
        epic_id=epic_id,
        evidence_id="predating-review",
        reviewed_child_ids=("bd-ib-recency-e",),
        now="2026-10-08T02:00:00Z",
    )

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(project_root=tmp_path, epic_id=epic_id, evidence_id="predating-review")

    message = str(refused.value)
    assert "predating-review" in message
    assert "bd-ib-recency-e" in message
    assert "2026-10-08T05:00:00Z" in message
    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"


def test_a_wholly_stale_timeline_commissions_a_fresh_review_before_it_refuses(
    tmp_path: Path,
) -> None:
    """Stale evidence is handled like MISSING evidence, not like a dead end.

    The ratified clause says an archive attempt whose ledger timeline carries no
    VALID independent evidence must commission a fresh independent reviewer, and
    evidence that no longer covers the plan is not valid evidence. A leg that
    refused on sight would leave every stale plan waiting on a human to notice
    the gap — which is the thing commissioning exists to retire — and a plan
    archived once and reopened reaches exactly this state by default.

    The brief that reviewer is handed is asserted too, because a commission that
    named the OLD scope would send it to re-perform the same stale review: the
    set in the request is the set the grade compares against, read once.

    Refusing AFTER commissioning is what makes both halves observable in one run.
    The reviewer here records nothing — the common case, since a review takes
    longer than the archive attempt that asked for it — so the refusal still has
    to carry the stale account rather than falling back to "evidence is
    required", and the plan must be exactly as it was.
    """
    epic_id = _plan(project_root=tmp_path)
    _child(epic_id=epic_id, child_id="bd-ib-recency-f", created_at="2026-10-08T00:10:00Z")
    _record_evidence(
        epic_id=epic_id,
        evidence_id="stale-review",
        reviewed_child_ids=(),
        now="2026-10-08T02:00:00Z",
    )
    commissioned: list[ArchiveCompletenessReviewRequest] = []

    def launch_review(*, request: ArchiveCompletenessReviewRequest) -> str | None:
        commissioned.append(request)
        return None

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(
            project_root=tmp_path,
            epic_id=epic_id,
            evidence_id="stale-review",
            review_launcher=launch_review,
        )

    assert len(commissioned) == 1
    assert commissioned[0].child_ids == ("bd-ib-recency-f",)
    message = str(refused.value)
    assert "stale-review" in message
    assert "stale" in message
    assert "bd-ib-recency-f" in message
    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"


def test_evidence_postdating_every_reported_status_change_archives_as_it_did_before(
    tmp_path: Path,
) -> None:
    """EVERY child's latest status change — and a child reporting none has none.

    The refusing arm and the accepting arm run against ONE plan and differ only
    in when the review was written, which is what makes the pair evidence about
    the recency comparison rather than about the fixture.

    `bd-ib-recency-i` is the discriminating member: its record reports no
    readable status instant at all, the `omitempty`-sparse shape of a column
    nobody wrote. The instant leg cannot date its latest change, so it must not
    be what the refusal names while a child that demonstrably DID change late
    sits beside it — and it must not block the archive once every change the
    ledger actually reports is covered, or a plan carrying one such member could
    never be archived at all. The set leg still binds it unconditionally: it is
    named in both records, and dropping it would be reported as a removal.

    The accepting arm is the control for the whole item. Every refusal above
    costs a fresh review, so a leg that refused evidence it should accept would
    be the same defect pointed the other way — and this one proves the archive
    still completes: the directory moves, nothing remains at `plan/<slug>/`, and
    the epic closes.
    """
    epic_id = _plan(project_root=tmp_path)
    _child(epic_id=epic_id, child_id="bd-ib-recency-g", created_at="2026-10-08T00:10:00Z")
    _child(epic_id=epic_id, child_id="bd-ib-recency-h", created_at="2026-10-08T09:00:00Z")
    _child(epic_id=epic_id, child_id="bd-ib-recency-i", created_at="")
    reviewed = ("bd-ib-recency-g", "bd-ib-recency-h", "bd-ib-recency-i")
    _record_evidence(
        epic_id=epic_id,
        evidence_id="partial-postdate",
        reviewed_child_ids=reviewed,
        now="2026-10-08T02:00:00Z",
    )
    _record_evidence(
        epic_id=epic_id,
        evidence_id="full-postdate",
        reviewed_child_ids=reviewed,
        now="2026-10-08T10:00:00Z",
    )

    with pytest.raises(PlanArchiveRefusedError) as refused:
        _ = _archive(project_root=tmp_path, epic_id=epic_id, evidence_id="partial-postdate")

    message = str(refused.value)
    assert "bd-ib-recency-h" in message
    assert "2026-10-08T09:00:00Z" in message

    accepted = _archive(project_root=tmp_path, epic_id=epic_id, evidence_id="full-postdate")

    assert accepted["archive_path"] == f"plan/archive/{_SLUG}"
    assert not (tmp_path / "plan" / _SLUG).exists()
    assert _fake().show_issue(issue_id=epic_id)["status"] == "closed"

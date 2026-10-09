"""Plan operation package-command coverage."""

from __future__ import annotations

import importlib
from datetime import datetime
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
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
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PLAN_ASSERTION = "The operator drives the delivered command and sees it work."
# The archiving session's own environment, supplied explicitly so each archive
# grades against a known identity rather than against whatever session happens
# to be running pytest.
_ARCHIVING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "archiving-session"}
# The reviewing session's own environment. The evidence record's reviewer
# identity is COMPUTED from it — there is no field a caller can name one in —
# so a reviewer distinct from the archiver is expressed as a distinct session.
_REVIEWING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "reviewing-session"}


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


def _parse_utc_timestamp(*, value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _draft(*, issue_id: str, parent_id: str | None) -> IssueDraft:
    return IssueDraft(
        issue_id=issue_id,
        issue_type="task",
        title="child",
        description="child work",
        assignee=None,
        created_at="2026-08-11T00:00:00Z",
        parent_id=parent_id,
        metadata={"rank": "a1"},
        labels=["origin:freeform"],
    )


def _seed_plan_proof(*, epic_id: str) -> None:
    """Publish the captured/verified plan record pair the archive proof leg needs.

    Rendered through the PRODUCTION renderer rather than hand-written, because the
    gate reads the same bytes the posting primitive publishes: a hand-formatted
    body that happened to parse would make these archives pass against a reader
    no real record can satisfy. The two identities differ, which is what makes the
    `verified` record an independent replay rather than a self-verified one.
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
                timestamp="2026-10-05T01:00:00Z",
                build=BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
                assertions=(
                    RecordAssertion(
                        text=_PLAN_ASSERTION,
                        proof_mode=PROOF_MODE_HOST_CAPTURED,
                        governing_scenario=None,
                        steps=("Run the delivered command on the operator host.",),
                        proof="$ delivered --version\n0.1.0",
                        reproduced=reproduced,
                    ),
                ),
            ),
        )


def test_plan_command_module_exists() -> None:
    module_path = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "plan.py"
    )
    assert module_path.is_file()
    module = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    assert hasattr(module, "create_thread")


def test_create_writes_research_and_one_epic_anchor_only(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    result = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="harness-smoke",
        title="Harness smoke planning",
        research_filename="initial.md",
        research_text="# Findings\n\nResearch only.\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    assert result["research_path"] == "plan/harness-smoke/research/initial.md"
    # The note leads with the maintainer's statement and the assertions derived
    # from it — the plan clause's record of what done means — and the session's
    # own research follows it intact rather than being displaced.
    note = (tmp_path / "plan" / "harness-smoke" / "research" / "initial.md").read_text(
        encoding="utf-8"
    )
    assert "Done when the operator has driven it and seen it work." in note
    assert note.endswith("# Findings\n\nResearch only.\n")
    # The anchor is the ONE sanctioned metadata file; no `epic.md`,
    # `handoff.md`, or status file joins it.
    assert sorted(
        path.relative_to(tmp_path).as_posix() for path in (tmp_path / "plan").rglob("*")
    ) == [
        "plan/harness-smoke",
        "plan/harness-smoke/associated_work_item_id",
        "plan/harness-smoke/research",
        "plan/harness-smoke/research/initial.md",
    ]
    [record] = _fake().list_issues()
    assert record["issue_type"] == "epic"
    assert record["metadata"]["plan_slug"] == "harness-smoke"


def test_handoff_append_is_ledger_comment_and_timeline_readable(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="harness-smoke",
        title="Harness smoke planning",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    plan.append_handoff(
        config=_config(),
        epic_id=created["epic_id"],
        body="Next action: dispatch bd-ib-child through the factory.",
        author="factory-test",
        now="2026-08-11T01:02:03Z",
        next_action=plan.NextAction(
            kind="impl",
            ref="bd-ib-child",
            text="Dispatch bd-ib-child through the factory.",
        ),
    )
    entries = plan.read_timeline(config=_config(), epic_id=created["epic_id"])

    assert len(entries) == 1
    assert entries[0].author == "factory-test"
    assert entries[0].created_at == "2026-08-11T01:02:03Z"
    assert entries[0].body == "Next action: dispatch bd-ib-child through the factory."
    metadata = _fake().show_issue(issue_id=created["epic_id"])["metadata"]
    assert metadata["next_action"] == {
        "kind": "impl",
        "ref": "bd-ib-child",
        "text": "Dispatch bd-ib-child through the factory.",
    }
    assert metadata["last_session"] == "factory-test at 2026-08-11T01:02:03Z"


def test_supervisor_handoff_computes_reserved_author_literal(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="harness-smoke",
        title="Harness smoke planning",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    plan.append_supervisor_handoff(
        config=_config(),
        epic_id=created["epic_id"],
        slug="harness-smoke",
        body="Resume state before wind-down.",
        now="2026-08-11T01:02:03Z",
        next_action=plan.NextAction(
            kind="human",
            ref="",
            text="Confirm the anchor filename with the maintainer.",
        ),
    )
    entries = plan.read_timeline(config=_config(), epic_id=created["epic_id"])

    assert len(entries) == 1
    assert entries[0].author == "harness-smoke-supervisor"
    assert entries[0].created_at == "2026-08-11T01:02:03Z"
    assert entries[0].body == "Resume state before wind-down."
    metadata = _fake().show_issue(issue_id=created["epic_id"])["metadata"]
    assert metadata["last_session"] == "harness-smoke-supervisor at 2026-08-11T01:02:03Z"


def test_scope_event_records_requirements_and_explicit_deferrals(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="scope-thread",
        title="Scope thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    plan.record_scope_event(
        config=_config(),
        epic_id=created["epic_id"],
        requirements=("archive must gate children",),
        deferrals=("UI polish is deferred",),
        author="factory-test",
        now="2026-08-11T01:02:03Z",
    )

    [entry] = plan.read_timeline(config=_config(), epic_id=created["epic_id"])
    assert "Requirement carriers:" in entry.body
    assert "- archive must gate children" in entry.body
    assert "Explicit deferrals:" in entry.body
    assert "- UI polish is deferred" in entry.body


def test_archive_refuses_undisposed_children(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=None))
    _fake().add_dependency(from_id=created["epic_id"], to_id="bd-ib-child", edge_type=EDGE_BLOCKS)
    _fake().update_issue(issue_id="bd-ib-child", status="ready")

    with pytest.raises(plan.PlanArchiveRefusedError) as exc:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="bd-comment-1",
        )

    assert "undisposed child work-items: bd-ib-child" in str(exc.value)


def test_archive_refuses_undisposed_parent_child_children(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=created["epic_id"]))
    _fake().update_issue(issue_id="bd-ib-child", status="ready")

    with pytest.raises(plan.PlanArchiveRefusedError) as exc:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="bd-comment-1",
        )

    assert "undisposed child work-items: bd-ib-child" in str(exc.value)


def test_archive_edge_predicate_ignores_malformed_dependency_records() -> None:
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    assert (
        plan._blocking_dependency_ids(  # noqa: SLF001 - malformed ledger-record coverage.
            record={"dependencies": "not-a-list"},
        )
        == frozenset()
    )
    assert (
        plan._is_blocks_dependency_edge(  # noqa: SLF001 - malformed ledger-edge coverage.
            edge="not-an-edge",
        )
        is None
    )
    assert (
        plan._is_blocks_dependency_edge(  # noqa: SLF001 - malformed ledger-edge coverage.
            edge={"type": "blocks", "depends_on_id": 7},
        )
        is None
    )


def test_archive_requires_completeness_review_evidence(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    with pytest.raises(plan.PlanArchiveRefusedError) as exc:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id=None,
        )

    assert "independent completeness-review evidence is required" in str(exc.value)


def test_archive_launches_independent_review_and_waits_for_durable_evidence(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=None))
    _fake().add_dependency(
        from_id="bd-ib-child",
        to_id=created["epic_id"],
        edge_type=EDGE_BLOCKS,
    )
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    launched: list[object] = []

    def launch_review(
        *,
        request: object,
    ) -> str:
        launched.append(request)
        return "review-evidence-1"

    with pytest.raises(plan.PlanArchiveRefusedError) as exc:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id=None,
            review_launcher=launch_review,
        )

    assert len(launched) == 1
    assert "independent completeness-review evidence is required" in str(exc.value)
    assert (tmp_path / "plan" / "archive-thread").is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] != "closed"


def test_archive_after_reviewer_records_valid_durable_evidence(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=None))
    _fake().add_dependency(
        from_id="bd-ib-child",
        to_id=created["epic_id"],
        edge_type=EDGE_BLOCKS,
    )
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    launched: list[object] = []

    def launch_review(
        *,
        request: object,
    ) -> str:
        launched.append(request)
        plan.record_completeness_review_evidence(
            config=_config(),
            epic_id=created["epic_id"],
            evidence_id="review-evidence-1",
            env=_REVIEWING_SESSION_ENV,
            separate_reviewer=True,
            attests_complete_requirement_coverage=True,
            body="All research requirements and deferrals have ledger carriers.",
            now="2026-08-11T02:00:00Z",
        )
        return "review-evidence-1"

    _seed_plan_proof(epic_id=created["epic_id"])

    result = plan.archive_thread(
        env=_ARCHIVING_SESSION_ENV,
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        epic_id=created["epic_id"],
        completeness_review_comment_id=None,
        review_launcher=launch_review,
    )

    assert len(launched) == 1
    assert result["archive_path"] == "plan/archive/archive-thread"
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] == "closed"


def test_launched_review_evidence_is_graded_against_the_archiving_identity_too(
    tmp_path: Path,
) -> None:
    """The LAUNCHER path grades its evidence against the same computed identity.

    There are two routes into the completeness leg — a caller-supplied evidence id
    and one a commissioned reviewer returns — and the defect this closes sat in the
    value BOTH routes compared against. A fix proven on only the supplied route
    would leave the launched one grading against the old constant, and that half is
    the harder one to notice: the launcher has just run, so the evidence is fresh
    and obviously present.

    The discriminating setup is a launcher that records under the ARCHIVING
    session's own environment, which is what a session commissioning a review of
    its own plan and then performing it itself actually produces.
    """
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=(_PLAN_ASSERTION,),
        ),
    )
    _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=created["epic_id"]))
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    _seed_plan_proof(epic_id=created["epic_id"])

    def launch_self_review(*, request: object) -> str:
        del request
        plan.record_completeness_review_evidence(
            config=_config(),
            epic_id=created["epic_id"],
            evidence_id="launched-self-review",
            env=_ARCHIVING_SESSION_ENV,
            separate_reviewer=True,
            attests_complete_requirement_coverage=True,
            body="Self-attested complete.",
            now="2026-08-11T02:00:00Z",
        )
        return "launched-self-review"

    with pytest.raises(plan.PlanArchiveRefusedError) as refused:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id=None,
            review_launcher=launch_self_review,
        )

    assert "archiving-session" in str(refused.value)
    assert "launched-self-review" in str(refused.value)
    assert (tmp_path / "plan" / "archive-thread").is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] != "closed"


def test_archive_refuses_a_self_review_and_accepts_an_independent_one(tmp_path: Path) -> None:
    """BOTH legs of the independence check, in one run against one archiving identity.

    A single-leg test proves nothing here, and that is presumably how the defect
    survived: against the old predicate — which compared the reviewer identity
    against the literal `plan-archive` — the accepted leg passes, because every
    other string differs from the constant. Only the pair discriminates, and only
    while both legs share ONE archiving identity: the refused and the accepted
    evidence differ in nothing except whether their reviewer is the party
    archiving.

    The refusal NAMES the identity and the evidence id, because the remedy is
    neither inferable nor the same as the generic one: the evidence is present,
    well-formed and fully attesting, so "evidence is required" would send the one
    session that cannot satisfy this leg back to author a second comment under the
    same identity.
    """
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=created["epic_id"]))
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="self-review",
        # Recorded FROM the archiving session, which is the only way a self-review
        # can now arise: the reviewer identity is computed from whichever session
        # writes the comment, so this record carries the archiver's own id.
        env=_ARCHIVING_SESSION_ENV,
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="Self-attested complete.",
        now="2026-08-11T02:00:00Z",
    )
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="partial-review",
        env=_REVIEWING_SESSION_ENV,
        separate_reviewer=True,
        attests_complete_requirement_coverage=False,
        body="Did not attest every requirement carrier.",
        now="2026-08-11T02:01:00Z",
    )
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="independent-review",
        env=_REVIEWING_SESSION_ENV,
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-08-11T02:02:00Z",
    )
    _seed_plan_proof(epic_id=created["epic_id"])

    with pytest.raises(plan.PlanArchiveRefusedError) as self_reviewed:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="self-review",
        )
    with pytest.raises(plan.PlanArchiveRefusedError) as partial:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="partial-review",
        )

    assert "archiving-session" in str(self_reviewed.value)
    assert "self-review" in str(self_reviewed.value)
    # Withheld coverage earns the GENERIC refusal, because the remedy there IS the
    # one it names: somebody still has to perform and record a complete review.
    assert "independent completeness-review evidence is required" in str(partial.value)
    assert (tmp_path / "plan" / "archive-thread").is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] != "closed"

    accepted = plan.archive_thread(
        env=_ARCHIVING_SESSION_ENV,
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        epic_id=created["epic_id"],
        completeness_review_comment_id="independent-review",
    )

    assert accepted["archive_path"] == "plan/archive/archive-thread"
    assert not (tmp_path / "plan" / "archive-thread").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] == "closed"


def test_archive_refuses_while_a_file_outside_plan_reads_the_thread_by_path(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=created["epic_id"]))
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="review-evidence-1",
        env=_REVIEWING_SESSION_ENV,
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-08-11T02:00:00Z",
    )
    probe = tmp_path / "plan" / "archive-thread" / "rehearsal" / "probe.py"
    probe.parent.mkdir(parents=True)
    _ = probe.write_text("raise SystemExit\n", encoding="utf-8")
    reader = tmp_path / "tests" / "test_rehearsal.py"
    reader.parent.mkdir(parents=True)
    _ = reader.write_text(
        'PROBE = ROOT / "plan" / "archive-thread" / "rehearsal" / "probe.py"\n',
        encoding="utf-8",
    )

    with pytest.raises(plan.PlanArchiveRefusedError) as exc:
        plan.archive_thread(
            env=_ARCHIVING_SESSION_ENV,
            project_root=tmp_path,
            config=_config(),
            slug="archive-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="review-evidence-1",
        )

    assert "files outside plan/ reference plan/archive-thread/" in str(exc.value)
    assert "tests/test_rehearsal.py" in str(exc.value)
    assert (tmp_path / "plan" / "archive-thread").is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] != "closed"


def test_archive_with_no_outside_references_closes_and_stamps_the_epic_once(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=created["epic_id"]))
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="review-evidence-1",
        env=_REVIEWING_SESSION_ENV,
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-08-11T02:00:00Z",
    )
    _seed_plan_proof(epic_id=created["epic_id"])
    unrelated = tmp_path / "tests" / "test_unrelated.py"
    unrelated.parent.mkdir(parents=True)
    _ = unrelated.write_text('LABEL = "origin:archive-thread"\n', encoding="utf-8")

    result = plan.archive_thread(
        env=_ARCHIVING_SESSION_ENV,
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        epic_id=created["epic_id"],
        completeness_review_comment_id="review-evidence-1",
    )

    assert result["archive_path"] == "plan/archive/archive-thread"
    assert not (tmp_path / "plan" / "archive-thread").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] == "closed"
    entries = plan.read_timeline(config=_config(), epic_id=created["epic_id"])
    assert [entry.author for entry in entries].count("plan-archive") == 1


def test_archive_moves_thread_and_closes_epic_after_two_gates(tmp_path: Path) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        title="Archive thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-08-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    _ = _fake().create_issue(draft=_draft(issue_id="bd-ib-child", parent_id=None))
    _fake().add_dependency(
        from_id="bd-ib-child",
        to_id=created["epic_id"],
        edge_type=EDGE_BLOCKS,
    )
    _fake().close_issue(issue_id="bd-ib-child", reason="completed")
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="review-evidence-1",
        env=_REVIEWING_SESSION_ENV,
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="All research requirements and deferrals have ledger carriers.",
        now="2026-08-11T02:00:00Z",
    )
    _seed_plan_proof(epic_id=created["epic_id"])

    result = plan.archive_thread(
        env=_ARCHIVING_SESSION_ENV,
        project_root=tmp_path,
        config=_config(),
        slug="archive-thread",
        epic_id=created["epic_id"],
        completeness_review_comment_id="review-evidence-1",
    )

    assert result == {
        "archive_path": "plan/archive/archive-thread",
        "epic_id": created["epic_id"],
    }
    assert not (tmp_path / "plan" / "archive-thread").exists()
    assert (tmp_path / "plan" / "archive" / "archive-thread" / "research" / "initial.md").is_file()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] == "closed"
    comments = _fake().list_comments(issue_id=created["epic_id"])
    archive_comment = comments[-1]["text"]
    header, _, body = archive_comment.partition("\n\n")
    timestamp_line = header.splitlines()[2]
    assert _parse_utc_timestamp(value=timestamp_line.removeprefix("timestamp: "))
    assert "review-evidence-1" in body
    entries = plan.read_timeline(config=_config(), epic_id=created["epic_id"])
    archive_entries = [entry for entry in entries if entry.author == "plan-archive"]
    assert len(archive_entries) == 1
    assert _parse_utc_timestamp(value=archive_entries[0].created_at)

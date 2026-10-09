"""The archive leg's own module, split out of `plan.py` by cohesion.

`plan.py` had accreted two concerns: AUTHORING a plan (create, handoff, scope
event) and ARCHIVING one (the child-disposition gate, the working-tree sweep,
the completeness-review evidence resolution, the epic close and the directory
move). The archive half belongs beside its own neighbourhood —
`_plan_archive_gates.py` and `_plan_archive_review.py` already live there —
and the split is what gives `plan.py` the room the plan-level Definition of
Done needs.

The comment-header RENDER moves too, into `_plan_timeline.py`, which already
owns the PARSE of that same header. Both halves of one format now live in one
module and are structurally incapable of drifting apart; the alternative was a
cross-module private import, which pyright strict and the `private_calls`
check both reject.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
# The archiving session's own environment, supplied explicitly so these archives
# grade against a known identity rather than against whatever session happens to
# be running pytest.
_ARCHIVING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "archiving-session"}
# The reviewing session's own environment. The evidence record's reviewer
# identity is COMPUTED from it — there is no field a caller can name one in —
# so a reviewer distinct from the archiver is expressed as a distinct session.
_REVIEWING_SESSION_ENV = {"CLAUDE_CODE_SESSION_ID": "reviewing-session"}


@dataclass(frozen=True, kw_only=True)
class _UnavailableForge:
    """A `CommandRunner` whose forge-login read never resolves a login."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=1, stdout="", stderr="gh: command not found")


def test_the_archive_leg_moved_into_its_own_cohesive_module() -> None:
    module_path = _COMMANDS / "_plan_archive.py"

    assert module_path.is_file()

    archive = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_archive")
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    # The public entry point lives in the new module and is re-exported by the
    # source module, so every existing caller of `plan.archive_thread` is
    # unaffected by the move.
    assert "archive_thread" in archive.__all__
    assert plan.archive_thread is archive.archive_thread
    assert "archive_thread" in plan.__all__

    # The private helpers that ONLY the archive leg used moved WITH it and are
    # gone from the source module. A helper left behind and imported back would
    # be exactly the cross-module private import the split exists to avoid.
    assert not hasattr(plan, "_resolve_completeness_review_evidence")
    assert not hasattr(plan, "_utc_now_iso")


def test_the_plan_comment_header_render_lives_beside_its_parse() -> None:
    timeline = importlib.import_module("livespec_orchestrator_beads_fabro.commands._plan_timeline")
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")

    assert "plan_comment_body" in timeline.__all__
    # The render composes the exact three-line header the module's own
    # `read_timeline` parses back: prefix, author, timestamp, blank line, body.
    assert timeline.plan_comment_body(
        prefix=timeline.PLAN_SCOPE_PREFIX,
        author="factory-test",
        now="2026-10-04T00:00:00Z",
        body="Requirement carriers:\n- one",
    ) == (
        "plan-scope-event\nauthor: factory-test\ntimestamp: 2026-10-04T00:00:00Z\n\n"
        "Requirement carriers:\n- one"
    )
    assert not hasattr(plan, "_comment_body")


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


def test_the_proof_leg_refuses_an_epic_whose_definition_of_done_section_is_gone(
    tmp_path: Path,
) -> None:
    """A legacy epic with no section refuses rather than grading zero assertions.

    Zero assertions means zero UNPROVED ones, so a leg that graded the empty set
    would report met and archive a plan that never stated what done means. The
    refusal is distinct from the unproved-assertions one because the remedy is to
    author the section with the maintainer.
    """
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="sectionless-thread",
        title="Sectionless thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-04T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=created["epic_id"],
        evidence_id="review-evidence-1",
        env=_REVIEWING_SESSION_ENV,
        reviewed_child_ids=(),
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="Every requirement carrier under the plan is covered.",
        now="2026-10-05T00:00:00Z",
    )
    # The legacy shape: a description with prose and no section at all.
    _fake().update_issue(
        issue_id=created["epic_id"],
        description="Plan anchor for plan/sectionless-thread.",
    )

    with pytest.raises(plan.PlanArchiveRefusedError) as refused:
        plan.archive_thread(
            project_root=tmp_path,
            config=_config(),
            slug="sectionless-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="review-evidence-1",
            env=_ARCHIVING_SESSION_ENV,
        )

    assert "carries no gradeable Definition of Done section" in str(refused.value)
    assert (tmp_path / "plan" / "sectionless-thread").is_dir()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] != "closed"


def test_the_archive_computes_its_own_identity_and_refuses_while_it_does_not_resolve(
    tmp_path: Path,
) -> None:
    """The archiving actor is COMPUTED, so an invocation with no identity refuses.

    Until this landed, the completeness leg's independence check compared the
    reviewer identity against the literal `plan-archive` — a constant that always
    resolves, so no invocation could ever lack an archiving actor, and the check
    could only ever refuse a reviewer literally named `plan-archive`. Computing
    the actor from the invoking session is what gives the leg a real comparand.

    The consequence asserted here is the FAIL-CLOSED one, and it is the half a
    constant comparand cannot have: when neither an agent session nor a forge
    login resolves, there is no independence check left to make, so the archive
    refuses rather than proceeding on a comparand nobody could name. A gauge that
    passed while blinded would convert this refusal into a pass and leave a record
    that reads healthy.
    """
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    # The two seams the computation reads. They exist only once the archiving
    # actor is computed from the invoking session rather than taken from a module
    # constant, so this assertion is false against the constant-comparand build.
    assert {"env", "runner"} <= set(inspect.signature(plan.archive_thread).parameters)
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug="identity-thread",
        title="Identity thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-08T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=("The operator drives the delivered command and sees it work.",),
        ),
    )

    with pytest.raises(plan.PlanArchiveRefusedError) as refused:
        plan.archive_thread(
            project_root=tmp_path,
            config=_config(),
            slug="identity-thread",
            epic_id=created["epic_id"],
            completeness_review_comment_id="review-evidence-1",
            env={},
            runner=_UnavailableForge(),
        )

    assert "no publishing identity could be computed" in str(refused.value)
    assert "archiving party" in str(refused.value)
    assert (tmp_path / "plan" / "identity-thread").is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=created["epic_id"])["status"] != "closed"

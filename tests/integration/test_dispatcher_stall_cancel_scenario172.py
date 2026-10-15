"""Integration-tier acceptance for the stall-watchdog cancel routing.

Binds SPECIFICATION/scenarios.md "Scenario 172 — A stall-watchdog cancel is
never non-convergence: a first cancel is released and recovered, a second rests
for a human" and the `contracts.md` section "Dispatcher progress watchdog"
paragraphs "Not non-convergence", "A first stall cancel is released and
recovered" and "A second consecutive stall cancel rests for a human".

WHY THE NOT-NON-CONVERGENCE CASE IS ASSERTED FROM BOTH ENDS. The defect this
module is the acceptance surface for is that one predicate answered two
questions: `is_non_convergence_outcome` graded the watchdog's
`stalled-no-progress` status as a fix-loop-cap exhaustion, so a hung sandbox and
a slice that genuinely would not converge produced the identical disposition —
the item went to `backlog` and the calibration pass counted a non-convergence
observation. Measured 2026-10-12: all six `watchdog-stall-cancel` rows since
2026-10-08 were followed within two seconds by a `non-convergence-bounce` row.
So the predicate is asserted directly AND the bounce it drives is asserted
against a live journal: the predicate alone passes on a build whose bounce reads
the status itself, and the bounce alone passes on a build that bounces nothing at
all.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration import (
    build_calibration_record,
    calibration_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_non_convergence_cap import (
    BOUNCE_CAP_KEY,
    BOUNCE_CAP_OBSERVED_KEY,
    FIX_LOOP_VISIT_CAP,
    NON_CONVERGENCE_BOUNCE_STAGE,
    UNTRIGGERED_NON_CONVERGENCE_CAP,
    non_convergence_cap,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NON_CONVERGED_MARKER,
    is_non_convergence_outcome,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-stall1"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """A fresh in-memory tenant per case, which is the hermetic CI backend.

    `LIVESPEC_BEADS_FAKE` is the ONLY seam that flips the store onto it, and the
    dispatcher resolves its own connection internally, so the toggle has to be
    set in the environment rather than passed down.
    """
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


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice the watchdog cancelled",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-12T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _outcome(*, status: str, stage: str = "fabro-run", detail: str = "") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail=detail,
        fabro_run_id="01STALLRUN",
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    """A journal whose file EXISTS before the first append.

    Pre-created so `_journal_records` needs no absent-file arm: a disposition
    that writes nothing leaves no file at all, and a helper branching on that
    would carry an arm no case in this module exercises.
    """
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _journal_records(*, path: Path) -> list[dict[str, object]]:
    """Every record the journal file holds, as the dispatch wrote them."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_a_stall_cancel_is_not_a_non_convergence_outcome() -> None:
    """The watchdog's own status is NOT the fix-loop-cap signal.

    A hang and a false kill are neither "a slice that repeatedly fails the
    janitor gate within the fix-loop cap", so the predicate that drives the
    `backlog` bounce must not recognise the watchdog status at all. The
    fix-loop-cap sentinel is asserted alongside it because a predicate that
    answered False for everything would satisfy the first assertion on its own.
    """
    assert not is_non_convergence_outcome(outcome=_outcome(status="stalled-no-progress"))
    assert is_non_convergence_outcome(
        outcome=_outcome(
            status="failed",
            detail=f"output\n{NON_CONVERGED_MARKER}: fix-loop cap hit without converging",
        )
    )


def test_a_stall_cancelled_dispatch_is_neither_bounced_nor_journaled_as_one(
    tmp_path: Path,
) -> None:
    """The item stays where the dispatch left it and the journal carries no bounce row.

    Both halves are asserted because they fail independently: a build that
    journals the row but skips the ledger write, and one that moves the item
    while journaling nothing, each satisfy exactly one of them.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(tmp_path=tmp_path)

    bounce_non_convergence_to_backlog(
        repo=repo,
        item=item,
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    stages = [record.get("stage") for record in _journal_records(path=journal.path)]
    assert NON_CONVERGENCE_BOUNCE_STAGE not in stages
    assert _stored()[_ITEM_ID].status == "active"


def _calibration_row(*, outcome: DispatchOutcome) -> dict[str, object]:
    """The journal row the calibration analysis pass reads for one terminal.

    Built through the SAME pure derivation `emit_calibration` uses, with the
    stall window the dispatch would have resolved handed in — the cap
    classification is pure precisely so this reading needs no repository on
    disk, and handing in a real window is what stops a build that still named
    it from passing for one that declines to.
    """
    return calibration_journal_record(
        record=build_calibration_record(
            item=_item(),
            outcome=outcome,
            repo_name="livespec-orchestrator-beads-fabro",
            journal_records=(),
            wall_clock_seconds=12.0,
            token_cost_micros=None,
            dispatch_context_size=0,
            merged_pr_diff_size=None,
            bounce_cap=non_convergence_cap(outcome=outcome, stall_seconds=7200.0),
        )
    )


def test_the_calibration_pass_counts_the_fix_loop_cap_and_not_a_stall_cancel() -> None:
    """One non-convergence observation for the fix-loop cap, none for a stall.

    The two rows are asserted TOGETHER because each alone is vacuous: a pass
    that counted nothing would satisfy the stall half, and one that counted
    everything would satisfy the fix-loop half. Both the observation flag and
    the cap identity are read, because they are independent fields and a build
    that cleared the flag while still naming the stall window reports a
    dispatch that tripped a cap it was not bounced for.
    """
    stalled = _calibration_row(outcome=_outcome(status="stalled-no-progress"))
    assert stalled["bounced_to_regroom"] is False
    assert stalled[BOUNCE_CAP_KEY] is None
    assert stalled[BOUNCE_CAP_OBSERVED_KEY] is None

    exhausted = _calibration_row(
        outcome=_outcome(
            status="failed",
            detail=f"{NON_CONVERGED_MARKER}: janitor fix-loop cap hit without converging",
        )
    )
    assert exhausted["bounced_to_regroom"] is True
    assert exhausted[BOUNCE_CAP_KEY] == FIX_LOOP_VISIT_CAP


def test_a_stall_cancel_trips_no_cap_at_all() -> None:
    """The classification itself declines, so no caller can report a stall cap.

    Asserted on the classification as well as on the row above because the cap
    rides two surfaces — the bounce record and the calibration span — and a
    row-only assertion passes for a build that merely stopped projecting it.
    """
    cap = non_convergence_cap(outcome=_outcome(status="stalled-no-progress"), stall_seconds=7200.0)

    assert cap == UNTRIGGERED_NON_CONVERGENCE_CAP


_RUN_READING_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading"
_CANCEL_RECORD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record"
_PACKAGE_COMMANDS = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)


def _publish_draft_events(*, head: str, pull_request: int) -> tuple[str, str]:
    """An event stream whose `publish_draft` completed, and the record text beside it.

    The marker rides the node's own stderr, which is what the clause means by
    "read from the run's own record" — nothing here reads origin, because
    origin's branch may have moved since the push.
    """
    events = json.dumps(
        [
            {"event": "fabro.stage.started", "node_id": "publish_draft"},
            {"event": "fabro.stage.completed", "node_id": "publish_draft"},
            {
                "event": "fabro.edge.selected",
                "properties": {"from_node": "publish_draft", "to_node": "proof_capture"},
            },
            {"event": "fabro.stage.started", "node_id": "proof_capture"},
        ]
    )
    record_text = (
        f"LIVESPEC_PUBLISH_DRAFT_PUBLISHED: publish_branch=feat/{_ITEM_ID} "
        f"head={head} pull_request=#{pull_request}\n"
    )
    return events, record_text


def test_the_cancel_record_names_every_identifier_the_clause_requires() -> None:
    """One record naming the work-item, dispatch, run, factory, stage, pull request and head.

    The module path is asserted FIRST so this reads as a genuine assertion
    before the import rather than as a collection error, which proves only
    unimportability. Each identifier is then read by NAME off the rendered
    record: a record carrying six of the seven is a plausible record, and the
    missing one is whichever an operator needed.
    """
    assert (_PACKAGE_COMMANDS / "_dispatcher_stall_run_reading.py").is_file()
    assert (_PACKAGE_COMMANDS / "_dispatcher_stall_cancel_record.py").is_file()
    reading = importlib.import_module(_RUN_READING_MODULE)
    rendering = importlib.import_module(_CANCEL_RECORD_MODULE)
    head = "a" * 40
    events, record_text = _publish_draft_events(head=head, pull_request=2612)

    record = rendering.stall_cancel_record(
        work_item_id=_ITEM_ID,
        dispatch_id="d90ca2237f7b4e21bc5f0273439dbb59",
        run_id="01STALLRUN",
        factory="hp",
        executing_stage=reading.executing_stage(events_json=events),
        publication=reading.last_publish_draft_publication(
            events_json=events, record_text=record_text
        ),
    )

    assert record["stage"] == rendering.STALL_CANCEL_STAGE
    assert record["work_item_id"] == _ITEM_ID
    assert record["dispatch_id"] == "d90ca2237f7b4e21bc5f0273439dbb59"
    assert record["run_id"] == "01STALLRUN"
    assert record["factory"] == "hp"
    assert record["executing_stage"] == "proof_capture"
    assert record["pull_request"] == 2612
    assert record["published_head"] == head


def test_the_record_names_the_last_publication_and_not_a_newer_origin_head() -> None:
    """Two completed publications: the record names the LAST one the run pushed.

    `origin` has moved on in the fixture, so a build reading the branch instead
    of the run's record would report the newer head — which is the one thing the
    clause forbids, and which reads exactly like a correct record.
    """
    reading = importlib.import_module(_RUN_READING_MODULE)
    first = "b" * 40
    last = "c" * 40
    events = json.dumps(
        [
            {"event": "fabro.stage.started", "node_id": "publish_draft"},
            {"event": "fabro.stage.completed", "node_id": "publish_draft"},
            {"event": "fabro.stage.started", "node_id": "publish_draft"},
            {"event": "fabro.stage.completed", "node_id": "publish_draft"},
            {
                "event": "fabro.edge.selected",
                "properties": {"from_node": "publish_draft", "to_node": "proof_capture"},
            },
        ]
    )
    record_text = (
        f"LIVESPEC_PUBLISH_DRAFT_PUBLISHED: publish_branch=x head={first} pull_request=#11\n"
        f"LIVESPEC_PUBLISH_DRAFT_PUBLISHED: publish_branch=x head={last} pull_request=#11\n"
    )

    publication = reading.last_publish_draft_publication(
        events_json=events, record_text=record_text
    )

    assert publication is not None
    assert publication.published_head == last
    assert publication.pull_request == 11
    # And the stage is the edge target, because no node is open between nodes.
    assert reading.executing_stage(events_json=events) == "proof_capture"


def test_a_run_that_completed_no_publish_draft_has_no_publication_to_name() -> None:
    """An unpublished run reports no publication, which is not an unreadable head.

    The two answers have opposite remedies — a plain dispatch reclaims the
    publish branch — so a reader that collapsed them would advise reclaiming a
    branch a run had published onto.
    """
    reading = importlib.import_module(_RUN_READING_MODULE)
    events = json.dumps(
        [
            {"event": "fabro.stage.started", "node_id": "implement"},
        ]
    )

    assert reading.last_publish_draft_publication(events_json=events, record_text="") is None
    # The run was cancelled INSIDE `implement`, so the open node is the stage —
    # not the target of any earlier edge.
    assert reading.executing_stage(events_json=events) == "implement"


def test_an_unreadable_published_head_is_stated_rather_than_omitted() -> None:
    """A publication whose head could not be read SAYS so on the record.

    `published_head: null` on a record that DOES name a pull request is
    ambiguous in the expensive direction: it reads as "no head" to a resume,
    whose remedy for no head is a plain dispatch — and a plain dispatch reclaims
    the publish branch, deleting the very head the record failed to name. The
    unpublished control is asserted beside it because a build that stated the
    sentence on every record would satisfy the first half alone, and would then
    claim a failed measurement for a run where none was attempted.
    """
    reading = importlib.import_module(_RUN_READING_MODULE)
    rendering = importlib.import_module(_CANCEL_RECORD_MODULE)
    events = json.dumps(
        [
            {"event": "fabro.stage.started", "node_id": "publish_draft"},
            {"event": "fabro.stage.completed", "node_id": "publish_draft"},
        ]
    )
    # The node declared its pull request and NOT its head, which is what a
    # record written by an engine that does not surface node stderr looks like.
    record_text = "LIVESPEC_PUBLISH_DRAFT_PUBLISHED: publish_branch=feat/x pull_request=#2612\n"
    publication = reading.last_publish_draft_publication(
        events_json=events, record_text=record_text
    )

    assert publication is not None
    assert publication.pull_request == 2612
    assert publication.published_head is None

    stated = rendering.stall_cancel_record(
        work_item_id=_ITEM_ID,
        dispatch_id=None,
        run_id="01STALLRUN",
        factory="hp",
        executing_stage="proof_capture",
        publication=publication,
    )
    assert stated["published_head"] is None
    # Membership first, so the Red is a genuine assertion rather than a
    # KeyError: an absent key and a key holding the wrong value are different
    # faults, and only the first is what a build predating the statement shows.
    assert "published_head_unreadable" in stated
    statement = getattr(rendering, "UNREADABLE_PUBLISHED_HEAD", "")
    assert stated["published_head_unreadable"] == statement
    assert "could not be read" in statement

    unpublished = rendering.stall_cancel_record(
        work_item_id=_ITEM_ID,
        dispatch_id=None,
        run_id="01STALLRUN",
        factory="hp",
        executing_stage="implement",
        publication=None,
    )
    assert "published_head_unreadable" in unpublished
    assert unpublished["published_head_unreadable"] is None

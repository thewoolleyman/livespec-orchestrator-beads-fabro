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
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_acceptance_rework import (
    update_acceptance_failed_ai_passes,
)
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
    read_work_item_comments,
    read_work_items,
    update_work_item_status,
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


def test_a_first_stall_cancel_releases_the_claim_and_returns_the_item_to_ready(
    tmp_path: Path,
) -> None:
    """Scenario 172's "A first stall cancel ... is released and recovered".

    The disposition is asserted through the LEDGER and the JOURNAL together,
    because each surface alone passes on a build that is wrong in the other.
    A build that writes the release record but never reaches the store leaves
    the item `active` with `fabro` still holding it — the stranded shape this
    whole routing exists to retire, and the one a journal-only reading reports
    as a healthy release. A build that moves the item but journals nothing
    leaves an operator with a `ready` item and no account of which run was
    cancelled, so a re-dispatch cannot tell a released stall from work that
    was never dispatched.

    The COMMENT is asserted for the same reason it is required rather than
    optional: the journal is a per-clone file, so it is the ledger comment —
    and only the comment — that still names the cancelled run after the
    dispatching clone is gone. It must name the run, its factory and the stage
    the run was executing, which are the three facts a triager needs before
    deciding whether the kill was genuine.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition"
    )
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal.append(
        record={
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "run_id": "01STALLRUN",
            "factory": "hp",
            "executing_stage": "proof_capture",
        }
    )

    module.dispose_stall_cancel(
        repo=repo,
        item=item,
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    released = _stored()[_ITEM_ID]
    assert released.status == "ready"
    assert released.blocked_reason is None
    assert released.assignee is None

    stages = [record.get("stage") for record in _journal_records(path=journal.path)]
    assert module.STALL_RELEASE_STAGE in stages
    assert NON_CONVERGENCE_BOUNCE_STAGE not in stages

    comments = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    assert len(comments) == 1
    body = comments[0].text
    assert "01STALLRUN" in body
    assert "hp" in body
    assert "proof_capture" in body


def test_a_first_stall_release_is_replayable_without_affecting_a_newer_claim(
    tmp_path: Path,
) -> None:
    """Scenario 172's "A first stall release is replayable without affecting a newer claim".

    The release is keyed by FACTORY AND RUN, which is what makes a second pass
    over the same cancellation a completion rather than a repetition. The
    hazard the clause names is not an untidy duplicate record: it is that the
    replay performs the release's ledger write a second time, long after the
    item was re-dispatched, and so hands a LIVE dispatch's claim back to the
    queue. Nothing about the resulting row says it happened — the item is
    `ready` with no assignee, which is exactly what a correct first release
    leaves — so the item is admitted again while the run it already has keeps
    going, and two runs publish onto one branch.

    The journey is the clause's own: an interrupted release, the reconciliation
    that completes it, a NEWER dispatch that claims the item, and then the
    replay. Both guards are exercised by it, and the two are separate
    mechanisms rather than one read twice — the already-released reading is
    keyed on the cancellation, while the newer-claim reading is keyed on the
    item — so each is asserted on its own instrument: the release row count
    says the completion did not run twice, and the item's status and assignee
    say the live claim survived.

    THE CANCEL-ROW COUNT IS ASSERTED TOO, and it is not decoration. The row
    count IS this item's across-dispatch cancellation record, which is what the
    second-cancel disposition routes on, so a replay that appended one would
    convert this item's single released stall into the repeat cancellation that
    rests for a human — on a dispatch that is still running.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition"
    )
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal.append(
        record={
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "run_id": "01STALLRUN",
            "factory": "hp",
            "executing_stage": "proof_capture",
        }
    )

    module.dispose_stall_cancel(
        repo=repo,
        item=item,
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )
    assert _stored()[_ITEM_ID].status == "ready"

    # The newer dispatch: the ordinary admission valve claims the released item
    # and journals its own `dispatch-id` record, exactly as a live dispatch does.
    update_work_item_status(path=_config(), item_id=_ITEM_ID, status="active", assignee="fabro")
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": "0000000000000000000000000000beef",
        }
    )

    module.dispose_stall_cancel(
        repo=repo,
        item=replace(item, status="active"),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    still_claimed = _stored()[_ITEM_ID]
    assert still_claimed.status == "active"
    assert still_claimed.assignee == "fabro"

    stages = [record.get("stage") for record in _journal_records(path=journal.path)]
    assert stages.count("watchdog-stall-cancel") == 1
    assert stages.count(module.STALL_RELEASE_STAGE) == 1
    assert len(read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)) == 1

    # The held stage is spelled as a LITERAL and bound to the exported name by
    # the `getattr` below, for the reason this module's other Red-predating
    # cases give: a Red authored before the constant exists would die on the
    # attribute lookup, which proves unimportability rather than unimplemented
    # behaviour.
    assert "stall-cancel-release-held" in stages
    assert getattr(module, "STALL_RELEASE_HELD_STAGE", "") == "stall-cancel-release-held"


def test_a_second_consecutive_stall_cancel_rests_the_item_for_a_human(
    tmp_path: Path,
) -> None:
    """Scenario 172's "A second consecutive stall cancel rests for a human".

    The SECOND cancel is where a release stops being the right answer: one
    cancellation says nothing about the slice, but an item that stalls again on
    a fresh run is either genuinely unrunnable or is being killed by something
    a re-dispatch will meet again, and releasing it a second time is an
    unbounded loop with no operator in it. So the disposition flips: the item
    rests at `blocked` / `needs-human` and no further dispatch is invoked.

    BOTH cancellations are named in the comment, and that is what the case
    asserts rather than merely the lifecycle write. A comment naming only the
    current run reads exactly like a first-cancel record, so an operator
    deciding whether the kills share a cause — the same factory, the same
    stage, a false kill inside one open command node twice — would have to
    reconstruct the earlier run from a journal the dispatching clone may no
    longer have. The remedy is named for the same reason the needs-human
    escalation names it: `blocked` is a rest state no automatic path leaves, so
    a record that did not say how to release it leaves the item parked
    indefinitely.
    """
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition"
    )
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    for run_id, factory, stage in (
        ("01FIRSTRUN", "hp", "implement"),
        ("01SECONDRUN", "vps", "proof_capture"),
    ):
        journal.append(
            record={
                "stage": "watchdog-stall-cancel",
                "work_item_id": _ITEM_ID,
                "run_id": run_id,
                "factory": factory,
                "executing_stage": stage,
            }
        )

    module.dispose_stall_cancel(
        repo=repo,
        item=item,
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    rested = _stored()[_ITEM_ID]
    assert rested.status == "blocked"
    assert rested.blocked_reason == "needs-human"

    # The terminal stage is spelled as a LITERAL and bound to the exported name
    # by the `getattr` below, for the reason this repo's other Red-predating
    # cases give: a Red authored before the constant exists would die on the
    # attribute lookup, which proves unimportability rather than unimplemented
    # behaviour. The binding assertion is what stops the literal drifting away
    # from the name every other reader uses.
    stages = [record.get("stage") for record in _journal_records(path=journal.path)]
    assert "stall-cancel-needs-human" in stages
    assert module.STALL_RELEASE_STAGE not in stages
    assert NON_CONVERGENCE_BOUNCE_STAGE not in stages
    assert getattr(module, "STALL_NEEDS_HUMAN_STAGE", "") == "stall-cancel-needs-human"

    body = read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)[0].text
    for named in ("01FIRSTRUN", "01SECONDRUN", "hp", "vps", "implement", "proof_capture"):
        assert named in body, named
    assert f"resolve-blocked:{_ITEM_ID}:ready" in body


def _metadata() -> dict[str, object]:
    """The item's raw metadata object, which is where a spent budget persists.

    Read through the client rather than through `WorkItem`, because the
    adapter projects only the fields the lifecycle models and the rework
    budget is not one of them — a reading taken off the projection could not
    see the counter this case is about either before or after.
    """
    record = make_beads_client(config=_config()).show_issue(issue_id=_ITEM_ID)
    return dict(cast("dict[str, object]", record.get("metadata", {})))


def test_a_released_first_stall_spends_no_budget_and_leaves_the_count_alone(
    tmp_path: Path,
) -> None:
    """Scenario 172's "the released stall consumes no budget … nor resets the count".

    A cancellation is not a verdict about the slice, so it must cost the slice
    nothing: the budgets exist to bound loops the WORK drives, and spending one
    on a hung sandbox or a false kill brings an item closer to a terminal it
    did nothing to earn. The same holds in the other direction for the count —
    a release that RESET it would discard a genuine preceding non-progress
    terminal and hand the item an attempt it had already used.

    The budget is SPENT BEFORE the release rather than asserted at zero, which
    is what makes this a measurement instead of a restatement: an untouched
    counter and a counter cleared back to its initial value are the same
    reading at zero, and the second is exactly what a lifecycle write that
    rewrote the metadata object wholesale would produce. One pass is recorded
    through the production writer, so the value under test is one the store
    itself put there.

    The KEY SET is asserted beside it because the other two rework caps are not
    persisted on the row today: a build that began spending one would announce
    itself as a new metadata key, and `ready_since` is the one addition the
    release is entitled to make, since returning the item to `ready` is what
    stamps the durable dwell instant.
    """
    repo = _repo(tmp_path=tmp_path)
    journal = _journal(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())
    spent = update_acceptance_failed_ai_passes(path=_config(), item_id=_ITEM_ID)
    assert spent.failed_ai_passes == 1
    before = _metadata()
    journal.append(
        record={
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "run_id": "01STALLRUN",
            "factory": "hp",
            "executing_stage": "proof_capture",
        }
    )

    dispose_stall_cancel_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition"
    )
    dispose_stall_cancel_module.dispose_stall_cancel(
        repo=repo,
        item=_item(),
        outcome=_outcome(status="stalled-no-progress"),
        journal=journal,
    )

    assert _stored()[_ITEM_ID].status == "ready"
    after = _metadata()
    assert after.get("acceptance_failed_ai_passes") == 1
    assert set(after) - set(before) <= {"ready_since"}
    assert set(before) - set(after) == set()

    # The cancel rows ARE this item's across-dispatch non-progress record, so
    # the count is read off them: a release that appended one would increment
    # it, and one that rewrote the journal would reset it.
    stages = [record.get("stage") for record in _journal_records(path=journal.path)]
    assert stages.count("watchdog-stall-cancel") == 1

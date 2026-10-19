"""Scenario 175 — a run past the whole-run wall budget is exported and rested.

Binds `SPECIFICATION/scenarios.md` "Scenario 175 — A run past the whole-run wall
budget is exported, cancelled and rested for a human", and the
`contracts.md` paragraphs it exercises (the Dispatcher progress watchdog's "The
whole-run wall budget", and the whole-run wall budget key of "ACP node
timeouts").

The journey is driven through the PRODUCTION launcher — a real
`WatchedFabroLauncher`, a real `FabroPort`, the real per-poll observation seam,
the real export-then-terminate precondition and the real threading — against a
scripted `CommandRunner` and the in-memory tenant. Only the fabro subprocess is
stood in, and it is stood in at the ARGV, because the sub-scenarios are about
which call each poll ISSUES and in which ORDER: nothing about a returned verdict
can distinguish a cancel that exported first from one that did not.

THE OPEN-COMMAND-NODE CASE IS THE SHARPEST OF THEM, and it is the one a
narrower test cannot reach. A command node emits a start event and a completion
event and nothing between them, so the stall watchdog deliberately widens its
window to that node's own timeout while one is open — which is exactly the
deferral the budget clause says "does not defer a budget cancel". The case below
therefore scripts a REAL open `janitor` start event with no completion, so the
production open-command-node reader finds it and the production stall decision
widens its bound, and asserts the budget cancels anyway.

Each case reads the verb sequence AND the journal, because neither alone is the
claim: the verbs say the export preceded the `fabro rm`, and the journal says
what the watchdog concluded — which record it wrote, and which it did not.

THE RESUME-ANCHORING CASE IS THE ONE SUB-SCENARIO THE LAUNCHER CANNOT REACH, so
it is driven through the production `gather_resume` instead. "A budget cancel
between publication and capture can anchor resume" is a claim about what a LATER
invocation reads off the row this watchdog wrote, and the two halves are joined
HERE rather than in two unit modules: the journal that case reads is rendered by
the production `run_wall_budget_exceeded_record`, so a respelling of the stage on
either side leaves both modules self-consistent and makes the test fail. Without
that join, "the budget record anchors" is a claim about a row a test author
typed.
"""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_cancel_anchor import (
    SOURCE_BUDGET_CANCEL_RECORD,
    SOURCE_CANCEL_RECORD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
    run_wall_budget_exceeded_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_cancel_record import (
    STALL_CANCEL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    StallPublication,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    REPOSITORY_LAYER,
    NodeTimeouts,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

_RUN_ID = "01BUDGETRUN"
_ITEM_ID = "bd-ib-sdxfsn"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
_START_EPOCH = 1_791_892_800.0
# One wall-clock reading per poll, each a full budget past the one before, so a
# run the factory reports RUNNING is past its budget by its second poll.
_WALL_STEP = 3601.0

# A `janitor` COMMAND node started and never completed. The production reader
# finds it and the production stall decision widens its window to that node's
# own resolved timeout — the deferral the budget clause overrides.
_OPEN_COMMAND_NODE_EVENTS = (
    '[{"event": "stage.started", "node_id": "janitor",' ' "timestamp": "2026-10-13T12:00:00Z"}]'
)
# No lifecycle events at all, and one frozen timestamp: the only condition the
# stall decision confirms a stall on.
_FROZEN_EVENTS = '[{"timestamp": "2026-10-13T12:00:00Z"}]'
_PS_RUNNING = (
    f'[{{"run_id": "{_RUN_ID}", "goal": "Work-item: {_ITEM_ID}",' ' "status": {"kind": "running"}}]'
)
_PS_RUNNABLE = (
    f'[{{"run_id": "{_RUN_ID}", "goal": "Work-item: {_ITEM_ID}",'
    ' "status": {"kind": "runnable"}}]'
)
_INSPECT_RUNNING = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "running"}}}}]'
_INSPECT_RUNNABLE = f'[{{"run_id": "{_RUN_ID}", "status": {{"kind": "runnable"}}}}]'


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedFabro:
    """The fabro subprocess, scripted at the ARGV for one dispatched run.

    `fabro run` BLOCKS until the scripted poll budget is spent or the run is
    removed, so the background thread stays alive while the foreground watch
    loop runs. Every verb is recorded in order, which is what makes the
    export-before-terminate ordering assertable rather than merely plausible.
    """

    events: str
    status_kind: str
    polls_before_run_returns: int = 4
    run_done: threading.Event = field(default_factory=threading.Event)
    verbs: list[str] = field(default_factory=list)
    _polls: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        verb = argv[1] if len(argv) > 1 else ""
        self.verbs.append(verb)
        if verb == "run":
            _ = self.run_done.wait(timeout=10.0)
            return CommandResult(exit_code=0, stdout=f"    Run: {_RUN_ID}\n", stderr="")
        if verb == "rm":
            self.run_done.set()
            return CommandResult(exit_code=0, stdout="", stderr="")
        if verb == "ps":
            return CommandResult(exit_code=0, stdout=self._listing(), stderr="")
        if verb == "inspect":
            self._polls += 1
            if self._polls >= self.polls_before_run_returns:
                self.run_done.set()
            return CommandResult(exit_code=0, stdout=self._record(), stderr="")
        if verb == "events":
            return CommandResult(exit_code=0, stdout=self.events, stderr="")
        # `dump`, and anything else the export issues: a dump that produced no
        # artifact still yields a pointer body naming the factory and the run,
        # which is what the precondition requires be durable.
        return CommandResult(exit_code=0, stdout="", stderr="")

    def _listing(self) -> str:
        return _PS_RUNNING if self.status_kind == "running" else _PS_RUNNABLE

    def _record(self) -> str:
        return _INSPECT_RUNNING if self.status_kind == "running" else _INSPECT_RUNNABLE


def _seed(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        "{\n"
        '  "livespec-orchestrator-beads-fabro": {\n'
        '    "connection": {"prefix": "bd-ib", "tenant": "t", "fake": true}\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    append_work_item(
        path=store_config(repo=repo),
        item=WorkItem(
            id=_ITEM_ID,
            type="task",
            status="active",
            title="A dispatched slice the wall budget is bounding",
            description="Implement the slice.",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee="fabro",
            depends_on=(),
            captured_at="2026-10-13T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The dispatched slice is verified green.",
        ),
    )


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=_SERVER,
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        run_wall_budget=_BUDGET,
        # A janitor timeout well past the budget, so the open-command-node case
        # below genuinely widens the stall window past it rather than merely
        # appearing to.
        node_timeouts=NodeTimeouts(
            configured={"janitor": 36000},
            stall_seconds=7200,
            stall_layer=REPOSITORY_LAYER,
        ),
    )


def _wall_clock() -> Any:
    ticks = iter(_START_EPOCH + _WALL_STEP * step for step in range(5000))
    return lambda: next(ticks)


def _monotonic_clock() -> Any:
    """A monotonic clock advancing 600s per liveness reading."""
    ticks = iter(float(tick) for tick in range(0, 6_000_000, 600))
    return lambda: next(ticks)


def _launch(*, repo: Path, events: str, status_kind: str = "running") -> tuple[Any, _Journal, Any]:
    _seed(repo=repo)
    fabro = _ScriptedFabro(events=events, status_kind=status_kind)
    journal = _Journal()
    launcher = WatchedFabroLauncher(
        sleep=lambda _seconds: None,
        clock=_monotonic_clock(),
        wall_clock=_wall_clock(),
        dispatch_id="dispatch-01",
    )
    result = launcher.launch(
        plan=_plan(repo=repo),
        runner=cast("Any", fabro),
        journal=cast("Any", journal),
    )
    return result, journal, fabro


def _exceeded_rows(*, journal: _Journal) -> list[dict[str, object]]:
    return [
        json.loads(json.dumps(record))
        for record in journal.records
        if record.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE
    ]


def test_scenario175_a_run_inside_an_open_command_node_is_still_cancelled(
    tmp_path: Path,
) -> None:
    """ "A progressing run is still bounded": the open node does not defer it.

    The stream carries a `janitor` start with no completion, so the production
    stall decision grades this run against that node's 36000-second timeout and
    would not cancel it for hours. The budget cancels it anyway, which is what
    makes the two bounds independent rather than one deferring the other.
    """
    result, journal, fabro = _launch(repo=tmp_path, events=_OPEN_COMMAND_NODE_EVENTS)
    assert result.budget_exceeded_run_id == _RUN_ID
    assert result.stalled_run_id is None
    assert "rm" in fabro.verbs
    rows = _exceeded_rows(journal=journal)
    assert len(rows) == 1
    assert rows[0]["executing_stage"] == "janitor"
    assert rows[0]["elapsed_seconds"] > rows[0]["budget_seconds"]
    # Never the stall record: the two cancels carry opposite dispositions.
    assert all(record.get("stage") != STALL_CANCEL_STAGE for record in journal.records)


def test_scenario175_the_pointer_is_exported_and_read_back_before_the_cancel(
    tmp_path: Path,
) -> None:
    """ "the Dispatcher writes and reads back the preserve-by-reference pointer".

    `fabro rm -f` is what makes the run's record unavailable, so the export has
    to precede it — and an export taken afterwards would still SUCCEED while
    describing nothing.
    """
    _, journal, fabro = _launch(repo=tmp_path, events=_OPEN_COMMAND_NODE_EVENTS)
    assert fabro.verbs.index("dump") < fabro.verbs.index("rm")
    rows = _exceeded_rows(journal=journal)
    pointer = rows[0]["preserved_pointer"]
    assert isinstance(pointer, str)
    assert pointer
    # The pointer is read back off the tenant's OWN comment surface, indexed on
    # `text`: `bd show --json` carries no bodies at all, so a read through it
    # reports every landed write as lost. A pointer in the journal alone would
    # be satisfied by a write nobody confirmed.
    comments = read_work_item_comments(path=store_config(repo=tmp_path), work_item_id=_ITEM_ID)
    bodies = [comment.text for comment in comments]
    assert any(PRESERVE_POINTER_MARKER in body for body in bodies)
    assert any(_RUN_ID in body for body in bodies)


def test_scenario175_the_budget_takes_precedence_over_a_simultaneous_stall(
    tmp_path: Path,
) -> None:
    """ "The budget takes precedence over a simultaneous stall".

    The stream is frozen with no command node open, so this run satisfies the
    stall rule as well. Only one record is written, and it is the budget's.
    """
    result, journal, _ = _launch(repo=tmp_path, events=_FROZEN_EVENTS)
    assert result.budget_exceeded_run_id == _RUN_ID
    assert result.stalled_run_id is None
    stages = [record.get("stage") for record in journal.records]
    assert stages.count(RUN_WALL_BUDGET_EXCEEDED_STAGE) == 1
    assert STALL_CANCEL_STAGE not in stages


def test_scenario175_queue_time_before_running_is_not_charged(tmp_path: Path) -> None:
    """ "Queue time does not count against the budget", and "An unmeasured start
    is not a cancel".

    The factory reports this run `runnable` on every poll, so no poll ever fixes
    its clock — and the wall clock advances a full budget per poll throughout,
    which is what would cancel it if any other instant were measured from.
    """
    result, journal, fabro = _launch(repo=tmp_path, events=_FROZEN_EVENTS, status_kind="runnable")
    assert result.budget_exceeded_run_id is None
    assert "rm" not in fabro.verbs
    stages = [record.get("stage") for record in journal.records]
    assert RUN_WALL_BUDGET_EXCEEDED_STAGE not in stages
    assert "run-wall-budget-held" not in stages


def test_scenario175_the_record_names_the_budget_and_the_layer_that_supplied_it(
    tmp_path: Path,
) -> None:
    """ "naming ... the budget, the layer that supplied it".

    The layer is the FIRST question asked of a cancellation: 3600 seconds is a
    deliberate repository override here, and only the layer separates that from
    a target that simply inherited the fleet default.
    """
    _, journal, _ = _launch(repo=tmp_path, events=_OPEN_COMMAND_NODE_EVENTS)
    row = _exceeded_rows(journal=journal)[0]
    assert row["work_item_id"] == _ITEM_ID
    assert row["dispatch_id"] == "dispatch-01"
    assert row["run_id"] == _RUN_ID
    assert row["factory"] == "hp"
    assert row["budget_seconds"] == 3600.0
    assert row["budget_layer"] == REPOSITORY_LAYER
    assert row["budget_start_source"] in {"run-record", "first-running-poll"}


_PUBLISHED_HEAD = "b" * 40
_OTHER_RUN_ID = "01OTHERRUN"
_DISPATCH_ID = "be09d09660154fd5ae7a1172a976bcbd"
_PR_NUMBER = 2680
_ASSERTION = "The dispatched slice is verified green."


def _budget_cancel_journal(*, path: Path) -> Path:
    """The journal a budget-cancelled dispatch leaves, rendered by PRODUCTION code.

    The cancel row comes from `run_wall_budget_exceeded_record` rather than being
    typed out here, which is what joins the two halves of this sub-scenario: the
    row the watchdog writes IS the row the resume reads, so a respelling of the
    stage or of a field name on either side fails this case instead of leaving
    two self-consistent modules that never meet.

    The `dispatch-id` row is part of the fixture because a dispatch journals one
    at launch and the anchor is scoped to the item's LATEST journaled dispatch.
    Without it this journal carries a cancel row for a dispatch nothing records —
    a shape no Dispatcher writes, and one a correctly scoped reader treats as a
    cancel the item has since dispatched past.
    """
    rows: list[dict[str, object]] = [
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _DISPATCH_ID,
            "workflow_name": "implement-work-item",
        },
        run_wall_budget_exceeded_record(
            work_item_id=_ITEM_ID,
            dispatch_id=_DISPATCH_ID,
            run_id=_RUN_ID,
            factory="hp",
            # "between its last completed publish_draft and proof_capture": the
            # cancel site reports `proof_capture` for that gap exactly as it does
            # for a cancel inside the node itself.
            executing_stage="proof_capture",
            publication=StallPublication(pull_request=_PR_NUMBER, published_head=_PUBLISHED_HEAD),
            elapsed_seconds=3601.0,
            budget=_BUDGET,
            start_source="run-record",
            preserved_pointer="https://github.test/c/9",
        ),
    ]
    _ = path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return path


def _resume_item() -> WorkItem:
    """The rested item a human released back to `ready` after the budget cancel."""
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A dispatched slice the wall budget is bounding",
        description=f"## Definition of Done\n\n- {_ASSERTION}\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


@dataclass(kw_only=True)
class _ResumeForge:
    """The forge and factory answers one resume reads, keyed on each argv's verb.

    `gh pr list` and `gh pr view` share a subcommand, so the forge key comes from
    argv[2] and the factory key from argv[1]: one table, and no case can answer a
    question it did not mean to.
    """

    answers: dict[str, CommandResult]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        key = argv[2] if Path(argv[0]).name == "gh" else argv[1]
        return self.answers.get(key, CommandResult(exit_code=1, stdout="", stderr=""))


def _resume_runner() -> _ResumeForge:
    """An open pull request at the cancelled head, whose proof record is ANOTHER run's.

    The record naming a different run is the clause's own precondition — "no
    proof record carries that dispatch's identifier" — and it is what makes this
    case discriminate rather than merely pass: a reader that ignored the budget
    row would still find that record and report the stage its `captured` verdict
    implies, which is `review` and not `proof_capture`.

    The factory answers that it no longer holds the cancelled run, which is what
    leaves the cancel record deciding the stage.
    """
    record = (
        f"Proof of Done — captured — run {_OTHER_RUN_ID} — 2026-10-13T12:00:00Z\n\n"
        f"## Assertion 1 — {_ASSERTION}\n\n"
        f"Publish-branch head: {_PUBLISHED_HEAD}\n\n"
        "Proof mode: factory_captured.\n"
    )
    return _ResumeForge(
        answers={
            "list": CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    [{"number": _PR_NUMBER, "state": "OPEN", "headRefOid": _PUBLISHED_HEAD}]
                ),
                stderr="",
            ),
            "view": CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    {"comments": [{"body": record, "url": "https://github.test/c/1"}]}
                ),
                stderr="",
            ),
            "ps": CommandResult(exit_code=0, stdout="[]", stderr=""),
        }
    )


def test_scenario175_a_budget_cancel_between_publication_and_capture_anchors_resume(
    tmp_path: Path,
) -> None:
    """ "A budget cancel between publication and capture can anchor resume".

    "Then the run-wall-budget-exceeded record anchors the published head and the
    new run enters at proof_capture." Driven through the production
    `gather_resume` over the journal the production cancel renderer wrote.

    The pre-repair build failed this SILENTLY. The cancel reader recognised only
    `watchdog-stall-cancel`, so a perfectly well-formed budget row anchored
    nothing, the resume refused for a headless pull request, and the re-dispatch
    reclaimed the publish branch and spent another whole budget rebuilding
    implement, janitor and publish_draft — the waste this work-item exists to
    prevent, re-entered through the recovery path.

    `proof_capture` is asserted rather than merely "an anchor exists", because
    the proof record this pull request carries is ANOTHER run's and its
    `captured` verdict implies `review`: the stage is what separates the budget
    row's reading from the record's.
    """
    (tmp_path / "tmp").mkdir()
    _seed(repo=tmp_path)
    gather = gather_resume(
        args=argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None),
        repo=tmp_path,
        item=_resume_item(),
        journal_path=_budget_cancel_journal(path=tmp_path / "tmp" / "journal.jsonl"),
        runner=cast("Any", _resume_runner()),
    )
    assert gather.anchor is not None
    assert gather.anchor.head == _PUBLISHED_HEAD
    assert gather.anchor.run_id == _RUN_ID
    assert gather.anchor.resumed_at == "proof_capture"
    # The resume record names the journal stage an operator can grep for, and the
    # budget row's stage is not the stall row's.
    assert gather.anchor.source == SOURCE_BUDGET_CANCEL_RECORD
    assert gather.anchor.source != SOURCE_CANCEL_RECORD
    assert gather.anchor.record is None
    assert gather.observation.anchor_head == _PUBLISHED_HEAD


def test_scenario175_a_budget_cancel_outside_the_capture_gap_anchors_nothing(
    tmp_path: Path,
) -> None:
    """The control: the clause's stage bound still binds the budget row.

    Without it, "the budget record anchored" is equally consistent with a reader
    that anchors on ANY budget row — including a `janitor` cancel of a rework
    round, whose head "would not carry the rework", so the resume would publish a
    proof record for a tree nobody built.
    """
    (tmp_path / "tmp").mkdir()
    _seed(repo=tmp_path)
    journal = _budget_cancel_journal(path=tmp_path / "tmp" / "journal.jsonl")
    rewritten = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    for row in rewritten:
        if row.get("stage") == RUN_WALL_BUDGET_EXCEEDED_STAGE:
            row["executing_stage"] = "janitor"
    _ = journal.write_text("".join(f"{json.dumps(row)}\n" for row in rewritten), encoding="utf-8")
    gather = gather_resume(
        args=argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None),
        repo=tmp_path,
        item=_resume_item(),
        journal_path=journal,
        runner=cast("Any", _resume_runner()),
    )
    # The anchor falls back to the proof record, whose `captured` verdict enters
    # at `review` — never the cancel anchor's fixed `proof_capture`.
    assert gather.anchor is not None
    assert gather.anchor.resumed_at != "proof_capture"
    assert gather.anchor.source != SOURCE_BUDGET_CANCEL_RECORD

"""A verified preservation ref releases a held budget cancel (bd-ib-l77jxo).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": when the export cannot be read back the Dispatcher
"MUST also list the refs on origin ... and look for a *verified preservation
ref* of the run ... The Dispatcher MUST cancel the run as soon as either a
re-attempted export reads back or a verified preservation ref exists. A cancel
released by a verified preservation ref MUST journal `run-wall-budget-exceeded`
exactly as above, with that ref and its commit id in place of the
preserve-by-reference pointer and a statement that the export could not be read
back, and its ledger comment MUST name the same. When no verified preservation
ref exists, the Dispatcher MUST NOT cancel the run ... at the third consecutive
`run-wall-budget-held` record for the same run, it MUST journal one
`run-wall-budget-hold-escalated` record and add one ledger comment to the item
naming the run id, the factory, the elapsed seconds, the budget, each failed
measurement, the statement that no verified preservation ref exists, and the
remedy ... it MUST NOT change the item's status while the run is live ... and
MUST cancel as soon as either release condition holds. A remote ref listing that
cannot be taken is a failed measurement of that poll, never evidence that no ref
exists."

Every case drives the real per-poll decision, `cancel_run_past_budget`, over a
scripted `git` and `fabro`; a case that held the cancel for the wrong reason
would otherwise satisfy a hold assertion as well as a correct one, so each hold
case is paired with a release case on the SAME world that differs in one fact.

The modules that do not exist when this file is authored are reached inside the
test bodies, behind an assertion on their file, so the Red commit fails on a
genuine assertion and never at collection.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import RunWallBudget
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_comment import (
    run_wall_budget_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_disposition import (
    dispose_run_wall_budget_cancel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
    RUN_WALL_BUDGET_HELD_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_watch import (
    RunWallBudgetWatch,
    RunWallVerdict,
    cancel_run_past_budget,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock import (
    RUN_RECORD_SOURCE,
    RunWallStart,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_HOLD_MODULE = f"{_PACKAGE}._dispatcher_run_wall_budget_hold"
_HOLD_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_run_wall_budget_hold.py"
)
_ESCALATED_STAGE = "run-wall-budget-hold-escalated"
_RUN = "01M6PAS50BAVMD32HFBV8P89YR"
_ITEM = "bd-ib-uq2ocd"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_BUDGET = RunWallBudget(seconds=21600.0, layer=REPOSITORY_LAYER)
_START = 1_791_892_800.0
_NOW = _START + 23515.0
_TIP = "a" * 40
_TREE = "cc9568cc88a0" + "0" * 28
_NEEDS_HUMAN = f"refs/heads/needs-human/{_RUN}"
_WIP = f"refs/livespec/wip/{_ITEM}/{_RUN}"
_REF_COMMIT = "b" * 40


def _inspect(*, tip: str | None) -> str:
    checkpoints = [] if tip is None else [{"checkpoint": {"git_commit_sha": tip}}]
    record = {"run_id": _RUN, "status": {"kind": "running"}, "checkpoints": checkpoints}
    return json.dumps([record])


@dataclass(kw_only=True)
class _World:
    """A scripted origin and factory: the ref listing, the trees and the record."""

    remote: dict[str, str] = field(default_factory=dict)
    tip: str | None = _TIP
    trees: dict[str, str] = field(default_factory=lambda: {_TIP: _TREE, _REF_COMMIT: _TREE})
    listing_exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

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
        self.calls.append(argv)
        verb = argv[1]
        if argv[0] == "git":
            return self._git(verb=verb, argv=argv)
        stdout = _inspect(tip=self.tip) if verb == "inspect" else ""
        return CommandResult(exit_code=0, stdout=stdout, stderr="")

    def _git(self, *, verb: str, argv: list[str]) -> CommandResult:
        if verb == "ls-remote":
            lines = "".join(f"{commit}\t{ref}\n" for ref, commit in self.remote.items())
            code = self.listing_exit_code
            return CommandResult(exit_code=code, stdout="" if code else lines, stderr="")
        commit = argv[-1].removesuffix("^{tree}")
        return CommandResult(exit_code=0, stdout=f"{self.trees[commit]}\n", stderr="")

    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls if call[0] != "git"]


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)

    def stage(self, *, name: str) -> list[dict[str, object]]:
        return [record for record in self.records if record.get("stage") == name]


@dataclass(kw_only=True)
class _Ledger:
    comments: list[dict[str, Any]] = field(default_factory=list)
    write_error: Exception | None = None
    read_error: Exception | None = None

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        _ = issue_id
        if self.read_error is not None:
            raise self.read_error
        return list(self.comments)

    def add_comment(self, *, issue_id: str, body: str) -> None:
        _ = issue_id
        if self.write_error is not None:
            raise self.write_error
        self.comments.append({"id": f"c-{len(self.comments)}", "text": body})


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name="petri",
        fabro_factory_server=_SERVER,
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        run_wall_budget=_BUDGET,
    )


def _port(*, repo: Path, world: _World) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url=_SERVER),
        runner=cast("Any", world),
        cwd=repo,
    )


def _poll(
    *,
    tmp_path: Path,
    world: _World,
    journal: _Journal,
    ledger: _Ledger | None,
    hold: object | None = None,
) -> Any:
    extra: dict[str, object] = {} if hold is None else {"hold": hold}
    return cancel_run_past_budget(
        dispatch_id="dispatch-01",
        plan=_plan(repo=tmp_path),
        port=_port(repo=tmp_path, world=world),
        runner=cast("Any", world),
        journal=cast("Any", journal),
        run_id=_RUN,
        start=RunWallStart(epoch=_START, source=RUN_RECORD_SOURCE),
        now_epoch=_NOW,
        ledger=cast("Any", ledger),
        **extra,
    )


def _hold_state() -> Any:
    assert _HOLD_PATH.is_file(), f"{_HOLD_PATH} does not exist"
    return importlib.import_module(_HOLD_MODULE).RunWallHoldState()


def test_a_needs_human_ref_at_the_runs_tree_releases_the_held_cancel(tmp_path: Path) -> None:
    """The measured instance: the export fails but origin holds the tree."""
    world = _World(remote={_NEEDS_HUMAN: _REF_COMMIT})
    journal = _Journal()
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger())
    assert verdict == RunWallVerdict.CANCELLED
    assert "rm" in world.verbs()
    assert journal.stage(name=RUN_WALL_BUDGET_HELD_STAGE) == []
    exceeded = journal.stage(name=RUN_WALL_BUDGET_EXCEEDED_STAGE)
    assert len(exceeded) == 1
    assert exceeded[0]["preserved_ref"] == _NEEDS_HUMAN
    assert exceeded[0]["preserved_ref_commit"] == _REF_COMMIT
    assert exceeded[0]["export_read_back"] is False
    assert "selective stage-diff read failed" in str(exceeded[0]["export_failed_measurement"])
    assert "preserved_pointer" not in exceeded[0]
    assert exceeded[0]["elapsed_seconds"] == 23515.0
    assert exceeded[0]["budget_seconds"] == 21600.0


def test_the_same_world_with_a_ref_at_another_tree_holds_the_cancel(tmp_path: Path) -> None:
    """The control: origin holding a ref of the run is not a verified copy of its tree."""
    world = _World(remote={_NEEDS_HUMAN: _REF_COMMIT})
    world.trees[_REF_COMMIT] = "f" * 40
    journal = _Journal()
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger())
    assert verdict == RunWallVerdict.HELD
    assert "rm" not in world.verbs()
    assert journal.stage(name=RUN_WALL_BUDGET_EXCEEDED_STAGE) == []
    assert len(journal.stage(name=RUN_WALL_BUDGET_HELD_STAGE)) == 1


def test_a_record_that_reports_no_tip_is_released_by_the_needs_human_ref(tmp_path: Path) -> None:
    """With no tip to compare, the run's own needs-human ref qualifies on its own."""
    world = _World(remote={_NEEDS_HUMAN: _REF_COMMIT}, tip=None)
    world.trees[_REF_COMMIT] = "f" * 40
    journal = _Journal()
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger())
    assert verdict == RunWallVerdict.CANCELLED
    exceeded = journal.stage(name=RUN_WALL_BUDGET_EXCEEDED_STAGE)[0]
    assert exceeded["preserved_ref"] == _NEEDS_HUMAN


def test_a_record_that_reports_no_tip_is_released_by_the_latest_wip_capture(
    tmp_path: Path,
) -> None:
    """The run's latest preserved capture also releases the hold on its own."""
    world = _World(remote={f"{_WIP}/1": "c" * 40, f"{_WIP}/2": _REF_COMMIT}, tip=None)
    journal = _Journal()
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger())
    assert verdict == RunWallVerdict.CANCELLED
    exceeded = journal.stage(name=RUN_WALL_BUDGET_EXCEEDED_STAGE)[0]
    assert (exceeded["preserved_ref"], exceeded["preserved_ref_commit"]) == (
        f"{_WIP}/2",
        _REF_COMMIT,
    )


def test_a_ref_listing_that_cannot_be_taken_is_a_failed_measurement(tmp_path: Path) -> None:
    """The same world as the release case, with the listing refused: still held."""
    world = _World(remote={_NEEDS_HUMAN: _REF_COMMIT}, listing_exit_code=128)
    journal = _Journal()
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger())
    assert verdict == RunWallVerdict.HELD
    assert "rm" not in world.verbs()
    held = journal.stage(name=RUN_WALL_BUDGET_HELD_STAGE)
    assert len(held) == 1
    measurement = str(held[0]["failed_measurement"])
    assert "git ls-remote" in measurement
    assert "selective stage-diff read failed" in measurement


def test_a_ref_release_needs_neither_a_ledger_nor_a_factory_server(tmp_path: Path) -> None:
    """The ref is read from origin, so the export's own preconditions do not gate it."""
    world = _World(remote={_NEEDS_HUMAN: _REF_COMMIT})
    journal = _Journal()
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=None)
    assert verdict == RunWallVerdict.CANCELLED
    exceeded = journal.stage(name=RUN_WALL_BUDGET_EXCEEDED_STAGE)[0]
    assert "ledger" in str(exceeded["export_failed_measurement"])


def test_the_third_consecutive_hold_escalates_once_and_keeps_the_run(tmp_path: Path) -> None:
    """Three holds with no verified ref journal one escalation and one comment."""
    state = _hold_state()
    world = _World()
    journal = _Journal()
    ledger = _Ledger()
    verdicts = [
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
        for _ in range(2)
    ]
    assert journal.stage(name=_ESCALATED_STAGE) == []
    assert ledger.comments == []
    verdicts.append(
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
    )
    assert verdicts == [RunWallVerdict.HELD] * 3
    assert len(journal.stage(name=RUN_WALL_BUDGET_HELD_STAGE)) == 3
    escalated = journal.stage(name=_ESCALATED_STAGE)
    assert len(escalated) == 1
    assert escalated[0]["run_id"] == _RUN
    assert escalated[0]["work_item_id"] == _ITEM
    assert escalated[0]["factory"] == "petri"
    assert escalated[0]["elapsed_seconds"] == 23515.0
    assert escalated[0]["budget_seconds"] == 21600.0
    assert "rm" not in world.verbs()
    assert len(ledger.comments) == 1
    body = ledger.comments[0]["text"]
    for fact in (_RUN, "petri", "23515", "21600", "stage-diff", "no verified preservation ref"):
        assert fact in body
    assert "cancels the run" in body


def test_a_later_hold_does_not_escalate_again(tmp_path: Path) -> None:
    """The escalation is recorded once per run, however long the hold lasts."""
    state = _hold_state()
    world = _World()
    journal = _Journal()
    ledger = _Ledger()
    for _ in range(6):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
    assert len(journal.stage(name=RUN_WALL_BUDGET_HELD_STAGE)) == 6
    assert len(journal.stage(name=_ESCALATED_STAGE)) == 1
    assert len(ledger.comments) == 1


def test_a_poll_after_the_escalation_that_finds_a_ref_cancels_the_run(tmp_path: Path) -> None:
    """The hold stays releasable after it escalated, without a second escalation."""
    state = _hold_state()
    world = _World()
    journal = _Journal()
    ledger = _Ledger()
    for _ in range(3):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
    world.remote[_NEEDS_HUMAN] = _REF_COMMIT
    verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
    assert verdict == RunWallVerdict.CANCELLED
    assert len(journal.stage(name=_ESCALATED_STAGE)) == 1
    assert len(journal.stage(name=RUN_WALL_BUDGET_EXCEEDED_STAGE)) == 1
    assert len(ledger.comments) == 1


def test_a_restarted_watch_does_not_escalate_a_run_already_escalated(tmp_path: Path) -> None:
    """The ledger comment is the durable fact, so a fresh watch reads it first."""
    world = _World()
    journal = _Journal()
    ledger = _Ledger()
    first = _hold_state()
    for _ in range(3):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=first)
    second = _hold_state()
    for _ in range(3):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=second)
    assert len(journal.stage(name=_ESCALATED_STAGE)) == 1
    assert len(ledger.comments) == 1


def test_an_unrelated_comment_does_not_hide_an_escalation(tmp_path: Path) -> None:
    """Only a comment carrying the marker AND this run id counts as prior."""
    world = _World()
    journal = _Journal()
    ledger = _Ledger(comments=[{"id": "c-x", "text": "livespec-run-wall-budget-hold-escalated"}])
    ledger.comments.append({"id": "c-y", "text": 7})
    ledger.comments.append({"id": "c-z", "text": f"run id: {_RUN}"})
    state = _hold_state()
    for _ in range(3):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
    assert len(journal.stage(name=_ESCALATED_STAGE)) == 1
    assert len(ledger.comments) == 4


def test_an_escalation_survives_a_ledger_that_cannot_be_written_or_read(
    tmp_path: Path,
) -> None:
    """The record is the Dispatcher's own, so a failing ledger never loses it."""
    world = _World()
    journal = _Journal()
    ledger = _Ledger(
        write_error=BeadsCommandError(command="bd comments", exit_code=1, stderr="refused")
    )
    ledger.read_error = BeadsCommandError(command="bd comments", exit_code=1, stderr="refused")
    state = _hold_state()
    verdict = None
    for _ in range(3):
        verdict = _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=ledger, hold=state)
    assert verdict == RunWallVerdict.HELD
    assert len(journal.stage(name=_ESCALATED_STAGE)) == 1


def test_an_escalation_with_no_ledger_is_still_journaled(tmp_path: Path) -> None:
    """A host with no ledger records the escalation in the journal alone."""
    world = _World()
    journal = _Journal()
    state = _hold_state()
    for _ in range(3):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=None, hold=state)
    escalated = journal.stage(name=_ESCALATED_STAGE)
    assert len(escalated) == 1
    assert any(
        "ledger" in str(one) for one in cast("list[str]", escalated[0]["failed_measurements"])
    )


def test_an_escalation_names_each_failed_measurement_once(tmp_path: Path) -> None:
    """Different polls fail differently; each distinct failure is named, none twice."""
    world = _World()
    journal = _Journal()
    state = _hold_state()
    _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger(), hold=state)
    world.listing_exit_code = 128
    for _ in range(2):
        _poll(tmp_path=tmp_path, world=world, journal=journal, ledger=_Ledger(), hold=state)
    measurements = cast("list[str]", journal.stage(name=_ESCALATED_STAGE)[0]["failed_measurements"])
    assert len(measurements) == 2
    assert "git ls-remote" not in measurements[0]
    assert "git ls-remote" in measurements[1]


def test_the_watch_carries_one_hold_count_across_its_polls(tmp_path: Path) -> None:
    """The per-run watch owns the count, so the loop holds no budget state itself."""
    world = _World()
    journal = _Journal()
    watch = RunWallBudgetWatch(ledger=cast("Any", _Ledger()))
    for _ in range(3):
        verdict = watch.verdict(
            dispatch_id="dispatch-01",
            plan=_plan(repo=tmp_path),
            port=_port(repo=tmp_path, world=world),
            runner=cast("Any", world),
            journal=cast("Any", journal),
            run_id=_RUN,
            recorded_epoch=_START,
            now_epoch=_NOW,
        )
        assert verdict == RunWallVerdict.HELD
    assert len(journal.stage(name=_ESCALATED_STAGE)) == 1


def test_the_released_cancel_comment_names_the_ref_its_commit_and_the_failed_export() -> None:
    """The ledger comment states the ref in place of the pointer, and why."""
    row: dict[str, object] = {
        "run_id": _RUN,
        "factory": "petri",
        "executing_stage": "implement",
        "elapsed_seconds": 23515.0,
        "budget_seconds": 21600.0,
        "budget_layer": "repository",
        "preserved_ref": _NEEDS_HUMAN,
        "preserved_ref_commit": _REF_COMMIT,
        "export_read_back": False,
        "export_failed_measurement": "fabro dump exited 124",
    }
    body = run_wall_budget_comment(item_id=_ITEM, row=row)
    assert _NEEDS_HUMAN in body
    assert _REF_COMMIT in body
    assert "could not be read back" in body
    assert "fabro dump exited 124" in body
    assert f"resolve-blocked:{_ITEM}:ready" in body
    assert "preserve-by-reference pointer:" not in body


def test_the_pointer_comment_is_unchanged_for_a_cancel_the_export_released() -> None:
    """The control: a row naming a pointer still renders the pointer line."""
    row: dict[str, object] = {"run_id": _RUN, "preserved_pointer": "comment-9173"}
    body = run_wall_budget_comment(item_id=_ITEM, row=row)
    assert "preserve-by-reference pointer: comment-9173" in body
    assert "verified preservation ref" not in body


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_the_rested_items_comment_and_journal_row_name_the_ref(tmp_path: Path) -> None:
    """The disposition writes the same ref into the ledger comment and its own row."""
    config = StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    item = WorkItem(
        id=_ITEM,
        type="task",
        status="active",
        title="A dispatched slice that outran its wall budget",
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
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    append_work_item(path=config, item=item)
    row = {
        "stage": RUN_WALL_BUDGET_EXCEEDED_STAGE,
        "work_item_id": _ITEM,
        "run_id": _RUN,
        "factory": "petri",
        "elapsed_seconds": 23515.0,
        "budget_seconds": 21600.0,
        "preserved_ref": _NEEDS_HUMAN,
        "preserved_ref_commit": _REF_COMMIT,
        "export_failed_measurement": "fabro dump exited 124",
    }
    path = tmp_path / "journal.jsonl"
    _ = path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    journal = JournalFile(path=path)
    dispose_run_wall_budget_cancel(
        repo=repo,
        item=item,
        outcome=DispatchOutcome(
            work_item_id=_ITEM,
            status=RUN_WALL_BUDGET_EXCEEDED_STAGE,
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="",
            fabro_run_id=_RUN,
        ),
        journal=journal,
    )
    comment = read_work_item_comments(path=config, work_item_id=_ITEM)[0].text
    assert _NEEDS_HUMAN in comment
    assert _REF_COMMIT in comment
    rest = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert rest["preserved_ref"] == _NEEDS_HUMAN
    assert rest["preserved_ref_commit"] == _REF_COMMIT


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (None, None),
        ([{"run_id": _RUN}], None),
        ([{"checkpoints": [{"checkpoint": {"git_commit_sha": "1" * 40}}]}], "1" * 40),
        (
            [
                {
                    "checkpoints": [
                        {"checkpoint": {"git_commit_sha": "1" * 40}},
                        {"checkpoint": {"git_commit_sha": "2" * 40}},
                        {"checkpoint": {"node": "no-commit"}},
                    ]
                }
            ],
            "2" * 40,
        ),
        ([{"checkpoint": {"git_commit_sha": ""}}], None),
        ([{"checkpoint": {"git_commit_sha": "3" * 40}}], "3" * 40),
    ],
)
def test_the_committed_tip_is_the_latest_checkpoint_commit_the_record_reports(
    record: object, expected: str | None
) -> None:
    """The run branch's committed tip is read off the record, never guessed."""
    module = importlib.import_module(f"{_PACKAGE}._dispatcher_run_wall_budget_refs")
    assert _HOLD_PATH.is_file(), f"{_HOLD_PATH} does not exist"
    assert module.committed_tip(record=record) == expected

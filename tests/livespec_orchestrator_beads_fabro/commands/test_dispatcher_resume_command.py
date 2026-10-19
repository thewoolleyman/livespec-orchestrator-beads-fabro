"""The `resume --item` entry point: the gather, the ladder, the record, the dispatch.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" is the clause, and Scenarios 142 and 143 exercise it. The
pieces it is assembled from each have their own file — the anchor reader, the
eight-refusal ladder, the gather, the journal record, the derived-graph entry and
the publish-branch exclusivity. This file asserts the SEQUENCE: what the command
does with those pieces, and in which order.

ORDER IS THE WHOLE SUBJECT HERE, because every refusal in the clause is specified
by WHERE it lands. The ladder runs "before the admission valve, before any run
exists and before touching any ref", so a refused resume must leave no claim, no
run, no journaled resume record and no reclaimed branch; and the resume record is
journaled "before the run exists", which also has to be after the wall, or a
dispatch the wall refuses would still consume one of the two resumes the chain
allows and silently lower the cap for the next attempt.

WHY THE REFUSAL CARRIES EVERY LINE AND NOT THE FIRST. The clause is explicit: "a
refusal that names only the first does not satisfy this clause". The command does
not re-decide that — `resume_refusals` already returns the whole tuple — so what
is asserted here is that the command RENDERS the whole tuple rather than
`refusals[0]`, which is the natural coding and reads identically on every
single-refusal case.

WHY THE WORKFLOW NAME IS SET DIRECTLY AND NOT PINNED. The resumed run runs "the
workflow the earlier run's dispatch record names", and separately "a resume MUST
NOT write or clear the item's `dispatch_workflow` metadata, so the next plain
dispatch of the item re-runs the recorded workflow from `start`".
`args_with_dispatch_workflow_name` — the helper the plain dispatch uses — WRITES
that metadata, so the resume must not call it. The two reads of the Namespace
that carry a resume (`resume_entry_node`, `resume_head`) are defensive by design,
so a resume that failed to set them would dispatch as an ordinary one and
re-implement from `start` with nothing in the output to say so.

WHY THE RECLAIM IS ASSERTED AS A SEAM NOBODY ON THIS PATH TOUCHES. The clause says
the resume "MUST NOT run the stale publish-branch reclaim": the surviving publish
branch is the branch the run resumes on. Running both would preserve the head to a
ref and delete the very branch the resumed run was about to check out, and the
journal would then read like a healthy reclaim. The resume used to say so by
passing `reclaim_publish_branches=False` to the shared wall; under `bd-ib-huoyk7`
the reclaim moved PAST the capacity decision, so the wall reclaims for nobody and
this path simply never calls it. The assertion therefore records the reclaim seam
across a whole resume rather than inspecting one argument.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import Admission
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    ProofRecord,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    PUBLISH_BRANCH_RECLAIM_HELD_STAGE,
    PUBLISH_BRANCH_RECLAIM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    RESUMED_AT_PR,
    SOURCE_FACTORY_RUN,
    ResumeAnchor,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_cancel_anchor import (
    SOURCE_CANCEL_RECORD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import RESUME_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, record_dispatch_factory
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_command"

_ITEM_ID = "bd-ib-fngpwg"
_HEAD = "0" * 39 + "a"
_REPUBLISHED_HEAD = "1" * 39 + "b"
_PULL_REQUEST = 2639
_EARLIER_RUN = "01M49TZ44210GSEC8VTFR8VHKP"
_CANCELLED_RUN = "01M4Q4XBZ5398FJAWQ131QER60"
_WORKFLOW = "implement-work-item"
_EXIT_PRECONDITION_ERROR = 3


@dataclass(kw_only=True)
class _RecordingJournal:
    """A journal that keeps every appended record in memory."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _Log:
    """What the resume did, in the order it did it."""

    events: list[str] = field(default_factory=list)
    dispatched_args: list[argparse.Namespace] = field(default_factory=list)


@dataclass(kw_only=True)
class _ProductionResumeRunner:
    """The forge, factory and ancestry readings a real resume command takes."""

    factory_payload: object
    retained: bool = True
    argvs: list[list[str]] = field(default_factory=list)

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
        self.argvs.append(argv)
        program = Path(argv[0]).name
        if program == "gh" and argv[2] == "list":
            return _result(
                stdout=json.dumps(
                    [{"number": _PULL_REQUEST, "state": "OPEN", "headRefOid": _REPUBLISHED_HEAD}]
                )
            )
        if program == "gh" and argv[2] == "view":
            return _result(
                stdout=json.dumps(
                    {
                        "comments": [
                            {"body": _proof_body(), "url": "https://forge.example/comment/1"}
                        ]
                    }
                )
            )
        if program == "fabro" and argv[1] == "ps":
            return _result(
                stdout=json.dumps(
                    [
                        {
                            "run_id": _EARLIER_RUN,
                            "status": "failed",
                            "goal": f"Work-item: {_ITEM_ID}",
                        }
                    ]
                    if self.retained
                    else []
                )
            )
        if program == "fabro" and argv[1] == "inspect":
            return _result(stdout=json.dumps(self.factory_payload))
        if program == "git" and argv[1] == "merge-base":
            return _result(stdout="")
        return CommandResult(exit_code=1, stdout="", stderr="unexpected command")


def test_the_production_resume_runner_reports_an_unexpected_command(tmp_path: Path) -> None:
    """The command-path fixture exposes an unmodeled command as a failed result."""
    runner = _ProductionResumeRunner(factory_payload=_republishing_factory_record())

    result = runner.run(argv=["unexpected"], cwd=tmp_path, timeout_seconds=1)

    assert result.exit_code == 1
    assert result.stderr == "unexpected command"


def _item(*, status: str = "ready") -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A resumable item",
        description="## Definition of Done\n\n- It resumes.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _record() -> ProofRecord:
    return ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id=_EARLIER_RUN,
        timestamp="2026-10-07T01:50:00Z",
        url=f"https://forge.example/pull/{_PULL_REQUEST}#issuecomment-1",
        body=f"Publish-branch head: {_HEAD}\n",
    )


def _anchor() -> ResumeAnchor:
    return ResumeAnchor(
        record=_record(),
        run_id=_EARLIER_RUN,
        head=_HEAD,
        resumed_at=RESUMED_AT_PR,
        source=SOURCE_FACTORY_RUN,
    )


def _observation(*, status: str = "ready", head: str = _HEAD) -> ResumeObservation:
    return ResumeObservation(
        work_item_id=_ITEM_ID,
        status=status,
        anchor_head=head,
        pull_request=_PULL_REQUEST,
        pull_request_state="OPEN",
        pull_request_head=head,
        liveness_observed=True,
    )


def _args(*, repo: Path) -> argparse.Namespace:
    return argparse.Namespace(
        repo=str(repo),
        item=_ITEM_ID,
        journal=str(repo / "journal.jsonl"),
        janitor=None,
        fabro_bin=None,
        workflow=None,
        workflow_name=None,
        as_json=False,
    )


def _result(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _proof_body() -> str:
    """The earlier run's latest proof, deliberately behind its own republish."""
    return (
        f"Proof of Done — verified — run {_EARLIER_RUN} — 2026-10-07T01:50:00Z\n\n"
        "## Assertion 1 — It resumes.\n\n"
        f"Publish-branch head: {_HEAD}\n"
    )


def _republishing_factory_record(*, head: str = _REPUBLISHED_HEAD) -> object:
    return [
        {
            "status": "failed",
            "stages": {
                "proof_capture@1": {"state": "succeeded"},
                "publish_draft@2": {"state": "succeeded"},
                "proof_capture@2": {"state": "failed"},
            },
            "checkpoint": {"current_node": "proof_capture", "git_commit_sha": head},
        }
    ]


def _production_resume_fixture(*, repo: Path) -> None:
    """Provision the persisted earlier-dispatch pin and journal the gather reads."""
    _ = (repo / ".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {"prefix": "bd-ib"},
            "dispatcher": {
              "default_factory": "default",
              "factories": {
                "default": {"server": "https://default.example.test"},
                "retained": {"server": "https://retained.example.test"}
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    append_work_item(path=store_config(repo=repo), item=_item())
    record_dispatch_factory(path=store_config(repo=repo), work_item_id=_ITEM_ID, factory="retained")
    _ = (repo / "journal.jsonl").write_text(
        "".join(
            f"{json.dumps(record)}\n"
            for record in (
                {
                    "stage": "dispatch-id",
                    "work_item_id": _ITEM_ID,
                    "dispatch_id": "earlier-dispatch",
                    "workflow_name": _WORKFLOW,
                },
                {"stage": "run-stamp", "work_item_id": _ITEM_ID, "run_id": _EARLIER_RUN},
            )
        ),
        encoding="utf-8",
    )


def _module_path() -> Path:
    """Where the resume command module is expected on disk."""
    return Path(dispatcher.__file__).parent / "_dispatcher_resume_command.py"


def _gather(*, anchor: ResumeAnchor | None, observation: ResumeObservation) -> ResumeGather:
    """One gathered measurement, shaped as the command's own gather returns it."""
    return ResumeGather(
        observation=observation,
        anchor=anchor,
        branch=f"feat/{_ITEM_ID}",
        earlier_run_ids=(_EARLIER_RUN,),
        workflow_name=_WORKFLOW,
    )


def _stub_resume(
    *,
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    journal: _RecordingJournal,
    item: WorkItem,
    log: _Log,
    anchor: ResumeAnchor | None,
    observation: ResumeObservation,
    refusals: tuple[str, ...],
    wall_exit: int | None = None,
) -> None:
    """Stand in every seam around the decision this file is about."""
    monkeypatch.setattr(module, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(
        module, "gather_resume", lambda **_kwargs: _gather(anchor=anchor, observation=observation)
    )
    monkeypatch.setattr(module, "resume_refusals", lambda **_kwargs: refusals)
    monkeypatch.setattr(module, "ShellCommandRunner", lambda: None)

    def _wall(**_kwargs: Any) -> int | None:
        log.events.append("wall")
        return wall_exit

    monkeypatch.setattr(module, "pre_dispatch_wall_exit", _wall)

    def _admit(**_kwargs: Any) -> Admission:
        log.events.append("claim")
        return Admission(admitted=[item], deferred=[], refused=[])

    monkeypatch.setattr(module, "admit_and_select", _admit)

    def _dispatch(**kwargs: Any) -> DispatchOutcome:
        log.events.append("launch")
        log.dispatched_args.append(kwargs["args"])
        return DispatchOutcome(
            work_item_id=item.id,
            status="green",
            stage="done",
            pr_number=_PULL_REQUEST,
            merge_sha="deadbeef",
            detail="resumed at pr",
        )

    monkeypatch.setattr(module, "dispatch_one", _dispatch)
    monkeypatch.setattr(
        module, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )

    def _tail(**_kwargs: Any) -> int:
        log.events.append("tail")
        return 0

    monkeypatch.setattr(module, "dispatch_tail_exit", _tail)


def _stub_production_resume_command(
    *,
    module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    journal: _RecordingJournal,
    log: _Log,
    runner: _ProductionResumeRunner,
) -> argparse.Namespace:
    """Leave gather real while replacing the command's unrelated outward seams."""
    monkeypatch.setattr(module, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(module, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([_item()], journal))
    monkeypatch.setattr(module, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(module, "pre_dispatch_wall_exit", lambda **_kwargs: None)
    monkeypatch.setattr(
        module,
        "admit_and_select",
        lambda **_kwargs: Admission(admitted=[_item()], deferred=[], refused=[]),
    )

    def _dispatch(**kwargs: Any) -> DispatchOutcome:
        log.dispatched_args.append(kwargs["args"])
        return DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="green",
            stage="done",
            pr_number=_PULL_REQUEST,
            merge_sha="deadbeef",
            detail="resumed at proof_capture",
        )

    monkeypatch.setattr(module, "dispatch_one", _dispatch)
    monkeypatch.setattr(module, "dispatch_tail_exit", lambda **_kwargs: 0)
    args = _args(repo=repo)
    args.fabro_bin = "fabro"
    return args


def test_the_resume_command_module_exists_on_disk() -> None:
    """The first genuine assertion of the surface: the module is a file."""
    assert _module_path().is_file()


def test_the_router_registers_a_resume_subcommand() -> None:
    """`resume --repo --item` parses, and routes to the resume handler."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    parser = dispatcher.main.__globals__["_build_parser"]()

    parsed = parser.parse_args(["resume", "--repo", "/repo", "--item", _ITEM_ID])

    assert parsed.subcommand == "resume"
    assert parsed.item == _ITEM_ID
    handlers = dispatcher.main.__globals__["_SUBCOMMAND_HANDLERS"]
    assert handlers["resume"] is module.run_resume_command


def test_a_clean_resume_claims_launches_and_carries_the_entry_node_and_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resumed dispatch enters at the anchored stage, on the anchored head."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )

    exit_code = module.run_resume_command(args=_args(repo=tmp_path))

    assert exit_code == 0
    assert log.events == ["wall", "claim", "launch", "tail"]
    dispatched = log.dispatched_args[0]
    assert dispatched.resume_entry_node == RESUMED_AT_PR
    assert dispatched.resume_head == _HEAD
    assert dispatched.workflow_name == _WORKFLOW


def test_a_clean_resume_journals_its_record_before_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One `resume` record, naming everything the clause requires it to name."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )

    _ = module.run_resume_command(args=_args(repo=tmp_path))

    assert [record["stage"] for record in journal.records] == [RESUME_STAGE]
    recorded = journal.records[0]
    assert recorded["work_item_id"] == _ITEM_ID
    assert recorded["earlier_run_ids"] == [_EARLIER_RUN]
    assert recorded["pull_request"] == _PULL_REQUEST
    assert recorded["head"] == _HEAD
    assert recorded["resumed_at"] == RESUMED_AT_PR
    assert recorded["resumed_at_source"] == SOURCE_FACTORY_RUN


def test_a_republication_anchor_dispatches_fresh_capture_and_persists_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 142: the command resumes its own moved head at fresh capture.

    Drive the command rather than `gather_resume`: selection alone cannot show
    that an admitted run enters at `proof_capture`, nor that the command writes
    the resume journal record that names the factory decision.
    """
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    _production_resume_fixture(repo=tmp_path)
    journal = _RecordingJournal()
    log = _Log()
    runner = _ProductionResumeRunner(factory_payload=_republishing_factory_record())
    args = _stub_production_resume_command(
        module=module,
        monkeypatch=monkeypatch,
        repo=tmp_path,
        journal=journal,
        log=log,
        runner=runner,
    )

    assert module.run_resume_command(args=args) == 0

    dispatched = log.dispatched_args[0]
    assert dispatched.resume_entry_node == "proof_capture"
    assert dispatched.resume_head == _REPUBLISHED_HEAD
    factory_argv = [
        argv for argv in runner.argvs if argv[:2] in (["fabro", "ps"], ["fabro", "inspect"])
    ]
    assert factory_argv
    assert all(argv[-2:] == ["--server", "https://retained.example.test"] for argv in factory_argv)
    assert len(journal.records) == 1
    recorded = journal.records[0]
    assert recorded["stage"] == RESUME_STAGE
    assert recorded["work_item_id"] == _ITEM_ID
    assert recorded["earlier_run_ids"][0] == _EARLIER_RUN
    assert recorded["pull_request"] == _PULL_REQUEST
    assert recorded["head"] == _REPUBLISHED_HEAD
    assert recorded["resumed_at"] == "proof_capture"
    assert recorded["resumed_at_source"] == SOURCE_FACTORY_RUN


def test_a_non_republishing_retained_run_refuses_the_production_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 143: no qualifying factory record leaves the moved-head refusal intact."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    _production_resume_fixture(repo=tmp_path)
    journal = _RecordingJournal()
    runner = _ProductionResumeRunner(factory_payload=_republishing_factory_record(head=_HEAD))
    args = _stub_production_resume_command(
        module=module,
        monkeypatch=monkeypatch,
        repo=tmp_path,
        journal=journal,
        log=_Log(),
        runner=runner,
    )

    assert module.run_resume_command(args=args) == _EXIT_PRECONDITION_ERROR
    assert journal.records == []
    error = capsys.readouterr().err
    assert _HEAD in error
    assert _REPUBLISHED_HEAD in error
    assert "dispatch it plainly instead" in error


def test_a_factory_that_no_longer_holds_the_run_refuses_the_production_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Scenario 143: a moved head cannot borrow a run a retained factory lacks."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    _production_resume_fixture(repo=tmp_path)
    journal = _RecordingJournal()
    runner = _ProductionResumeRunner(factory_payload=_republishing_factory_record(), retained=False)
    args = _stub_production_resume_command(
        module=module,
        monkeypatch=monkeypatch,
        repo=tmp_path,
        journal=journal,
        log=_Log(),
        runner=runner,
    )

    assert module.run_resume_command(args=args) == _EXIT_PRECONDITION_ERROR
    assert journal.records == []
    error = capsys.readouterr().err
    assert _HEAD in error
    assert _REPUBLISHED_HEAD in error
    assert "dispatch it plainly instead" in error


def test_the_resume_never_runs_the_stale_publish_branch_reclaim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The surviving branch is the one the run resumes on; reclaiming it destroys it.

    Recorded at the reclaim SEAM across a whole clean resume rather than read off
    one argument, because the reclaim is no longer something the wall can be asked
    to skip: it sits past the capacity decision, and a path reaches it only by
    calling `post_admission_publish_branch_reclaim` itself. Its control lives in
    `test_dispatcher_publish_branch_reclaim_after_capacity.py`, which drives both
    dispatch paths and reads the reclaim they DO perform — without it, a build
    where nobody could reclaim would satisfy this case.
    """
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    reclaimed: list[str] = []
    monkeypatch.setattr(
        wall,
        "reclaim_stale_publish_branches",
        lambda **kwargs: reclaimed.append(str(kwargs["items"])),
    )
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=_RecordingJournal(),
        item=_item(),
        log=_Log(),
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )

    _ = module.run_resume_command(args=_args(repo=tmp_path))

    assert reclaimed == []


def test_every_applicable_refusal_is_named_and_nothing_is_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two refusals, both rendered, before the wall and before any claim."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(status="active"),
        log=log,
        anchor=_anchor(),
        observation=_observation(status="active"),
        refusals=("the item is active, not ready", "the earlier run is still live"),
    )

    exit_code = module.run_resume_command(args=_args(repo=tmp_path))

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert log.events == []
    assert journal.records == []
    errors = capsys.readouterr().err
    assert "the item is active, not ready" in errors
    assert "the earlier run is still live" in errors


def test_a_resume_with_no_anchor_refuses_even_when_the_ladder_named_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fail CLOSED: an unanchored resume has no head to check out and no record to cite."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(),
        log=log,
        anchor=None,
        observation=ResumeObservation(
            work_item_id=_ITEM_ID, status="ready", liveness_observed=True
        ),
        refusals=(),
    )

    exit_code = module.run_resume_command(args=_args(repo=tmp_path))

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert log.events == []
    assert journal.records == []
    assert "nothing to resume from" in capsys.readouterr().err


def test_a_wall_refusal_leaves_no_resume_record_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A walled-off resume must not consume one of the two the chain allows."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
        wall_exit=_EXIT_PRECONDITION_ERROR,
    )

    exit_code = module.run_resume_command(args=_args(repo=tmp_path))

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert log.events == ["wall"]
    assert journal.records == []


def test_an_item_absent_from_the_tenant_is_a_precondition_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `--item` naming nothing in this tenant never reaches the gather."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: ([], journal))

    args = _args(repo=tmp_path)
    exit_code = module.run_resume_command(args=args)

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert log.events == []
    assert _ITEM_ID in capsys.readouterr().err


def test_an_unpreparable_repo_refuses_before_the_gather(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`prepare` returning None is the staleness / missing-config refusal."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=_RecordingJournal(),
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )
    monkeypatch.setattr(module, "prepare", lambda **_kwargs: None)

    assert module.run_resume_command(args=_args(repo=tmp_path)) == _EXIT_PRECONDITION_ERROR
    assert log.events == []


def test_a_preamble_refusal_short_circuits_the_whole_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preamble owns the invoker, config and fabro refusals; the resume inherits them."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=_RecordingJournal(),
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )
    monkeypatch.setattr(
        module, "dispatch_preamble", lambda **_kwargs: (None, _EXIT_PRECONDITION_ERROR)
    )

    assert module.run_resume_command(args=_args(repo=tmp_path)) == _EXIT_PRECONDITION_ERROR
    assert log.events == []


def test_a_capacity_deferred_resume_reports_the_valves_own_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The WIP cap binds a resume, so the deferred outcome has to be reportable.

    `dispatch --item` exempts itself from the cap as an operator override; the
    resume clause lists the WIP cap among the rules it IS subject to, so the
    valve can hand back a deferral with nothing launched. Taking `[0]` of the
    launched list alone would raise on exactly that path.
    """
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    log = _Log()
    deferred = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status="skipped",
        stage="wip-cap",
        pr_number=None,
        merge_sha=None,
        detail="deferred: wip cap full",
    )
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=_RecordingJournal(),
        item=_item(),
        log=log,
        anchor=_anchor(),
        observation=_observation(),
        refusals=(),
    )
    monkeypatch.setattr(
        module,
        "admit_and_select",
        lambda **_kwargs: Admission(admitted=[], deferred=[deferred], refused=[]),
    )

    exit_code = module.run_resume_command(args=_args(repo=tmp_path))

    assert exit_code == 0
    assert log.events == ["wall", "tail"]


def test_the_resume_never_pins_the_items_dispatch_workflow_metadata() -> None:
    """The pin helper WRITES that metadata, and a resume must not write or clear it."""
    assert _module_path().is_file()
    source = _module_path().read_text(encoding="utf-8")

    assert "args_with_dispatch_workflow_name" not in source
    assert "record_dispatch_workflow" not in source


def _cancel_anchor() -> ResumeAnchor:
    """The anchor a stall-cancel record provides: no proof record, capture entry."""
    return ResumeAnchor(
        record=None,
        run_id=_CANCELLED_RUN,
        head=_HEAD,
        resumed_at="proof_capture",
        source=SOURCE_CANCEL_RECORD,
    )


def test_a_cancel_anchored_resume_names_its_source_and_reclaims_no_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 172: the `resume` record names the cancel record, and no ref moves.

    Both halves are asserted together because together they are the recovery: the
    record is what links the cancelled run's identifiers to this dispatch, and the
    ABSENT reclaim is what leaves the publish branch standing for the resumed run
    to check out. A build that journaled the record and reclaimed anyway would
    preserve the head to a ref, delete the branch, and leave a journal reading
    exactly like a healthy recovery.
    """
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    journal = _RecordingJournal()
    log = _Log()
    _stub_resume(
        module=module,
        monkeypatch=monkeypatch,
        journal=journal,
        item=_item(),
        log=log,
        anchor=_cancel_anchor(),
        observation=_observation(),
        refusals=(),
    )

    exit_code = module.run_resume_command(args=_args(repo=tmp_path))

    assert exit_code == 0
    resume_records = [one for one in journal.records if one["stage"] == RESUME_STAGE]
    assert len(resume_records) == 1
    assert resume_records[0]["resumed_at"] == "proof_capture"
    assert resume_records[0]["resumed_at_source"] == SOURCE_CANCEL_RECORD
    assert resume_records[0]["head"] == _HEAD
    stages = {one["stage"] for one in journal.records}
    assert PUBLISH_BRANCH_RECLAIM_STAGE not in stages
    assert PUBLISH_BRANCH_RECLAIM_HELD_STAGE not in stages
    dispatched = log.dispatched_args[0]
    assert dispatched.resume_entry_node == "proof_capture"
    assert dispatched.resume_head == _HEAD

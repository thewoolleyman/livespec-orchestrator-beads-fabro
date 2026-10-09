"""Everything one resume MEASURES, gathered once before the ladder grades it.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" names three external systems the decision depends on — the
ledger, the forge and the factory — and the refusal ladder is deliberately PURE
over their answers. This is the gather that produces those answers, so this file
is where the IO-shaped mistakes are caught: a question asked of the wrong system,
a "could not ask" collapsed into an answer, or a resumed-at stage inferred when
the factory would have named it outright.

THE ONE ORDERING THAT IS LOAD-BEARING. The clause says the resumed-at stage is
read "from the earlier run's record on the factory the earlier dispatch names",
and only "when that factory answers that it no longer holds the run" is it derived
from the latest record's verdict. The two sources differ in the direction that
matters: the factory record knows the node the run died INSIDE, while the verdict
fallback can only know the last node that PUBLISHED, so the inferred answer may
re-run a node the precise one would have skipped. The anchor therefore carries
WHICH source decided it, and both arms are asserted here against the SAME records
— the only difference between the two tests is whether the factory still holds the
run.

WHY "THE FACTORY NO LONGER HOLDS IT" IS NOT AN OUTAGE. Scenario 143 states it
outright: a factory answering that it holds no run with the journaled id "does not
refuse on liveness and derives the resumed-at stage from the pull request's latest
record". Only an unanswered or errored query is unobservable. So `fabro ps`
succeeding with the run absent and `fabro ps` failing produce the same empty
live-run tuple and must produce opposite decisions, which is what
`liveness_observed` carries.

WHY THE DEFINITION-OF-DONE DIFFERENCE IS MEASURED AGAINST THE RECORD. The clause
refuses when "the item's current Definition of Done section differs from the
earlier run's dispatch-time snapshot", and gives the reason: "so the inherited
records prove exactly the assertions the resumed dispatch is graded on". The
anchoring record IS that snapshot's evidence — a factory record publishes every
assertion it was dispatched with — so an assertion the record does not carry is an
assertion the inherited proof cannot cover, whatever the journal happens to hold.

WHY THE EARLIER-RUN IDENTIFIER LIST LEADS WITH THE RECORD'S OWN. The journal's
`resumes_anchored_on` names each resume by `earlier_run_ids[0]`, and the
attribution comment in `_dispatcher_proof_attribution` records why the record's
own id is the essential one: the earlier run may have been dispatched from another
checkout whose journal is invisible here, so the identifier read off the FORGE is
the only one guaranteed to be present.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import DispatchLock
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    SOURCE_FACTORY_RUN,
    SOURCE_LATEST_RECORD,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_RECORD_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_run_record"
_GATHER_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation"
_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_RECORD_PATH = _COMMANDS / "_dispatcher_resume_run_record.py"
_GATHER_PATH = _COMMANDS / "_dispatcher_resume_observation.py"

_ITEM_ID = "bd-ib-fngpwg"
_BRANCH = "feat/bd-ib-fngpwg"
_HEAD = "f" * 40
_MOVED_HEAD = "a" * 40
_EARLIER_RUN = "01M49TZ44210GSEC8VTFR8VHKP"
_EARLIER_DISPATCH = "5088bcaff2aa4bad99d9d0cf4fbbbe2f"
_PR = 2639
_ASSERTION = "The resume enters at the unfinished stage."
_COMMENT_URL = "https://github.test/c/1"


@dataclass(kw_only=True)
class _StubRunner:
    """A CommandRunner keyed on the (program, subcommand) pair of each argv.

    `gh pr list` and `gh pr view` share a subcommand, so the forge key is taken
    from argv[2] for `gh` and from argv[1] for `fabro`: one table, and no test
    can accidentally answer a question it did not mean to.
    """

    answers: dict[str, CommandResult]
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
        key = argv[2] if Path(argv[0]).name == "gh" else argv[1]
        return self.answers.get(key, CommandResult(exit_code=1, stdout="", stderr=""))


def _ok(*, stdout: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _record_body(*, assertion: str = _ASSERTION) -> str:
    return (
        f"Proof of Done — captured — run {_EARLIER_RUN} — 2026-10-07T01:50:00Z\n\n"
        f"## Assertion 1 — {assertion}\n\n"
        f"Publish-branch head: {_HEAD}\n\n"
        "Proof mode: factory_captured.\n"
    )


def _comments(*, body: str) -> str:
    return json.dumps({"comments": [{"body": body, "url": _COMMENT_URL}]})


def _pr_listing(*, state: str = "OPEN", head: str | None = _HEAD) -> str:
    return json.dumps([{"number": _PR, "state": state, "headRefOid": head}])


def _held(*, status: str = "failed") -> str:
    return json.dumps(
        [{"run_id": _EARLIER_RUN, "status": status, "goal": f"Work-item: {_ITEM_ID}"}]
    )


def _inspect(*, node: str) -> str:
    return json.dumps(
        [{"status": "failed", "checkpoints": [{"checkpoint": {"next_node_id": node}}]}]
    )


def _item(*, assertion: str = _ASSERTION) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A terminated run is resumed from its pull request",
        description=f"## Definition of Done\n\n- {assertion}\n",
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


def _journal(*, path: Path) -> Path:
    rows: list[dict[str, object]] = [
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _EARLIER_DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {"stage": "run-stamp", "work_item_id": _ITEM_ID, "run_id": _EARLIER_RUN},
    ]
    _ = path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return path


def _args() -> argparse.Namespace:
    return argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None)


def _runner(
    *,
    listing: CommandResult | None = None,
    view: CommandResult | None = None,
    ps: CommandResult | None = None,
    inspect: CommandResult | None = None,
) -> _StubRunner:
    return _StubRunner(
        answers={
            "list": listing if listing is not None else _ok(stdout=_pr_listing()),
            "view": view if view is not None else _ok(stdout=_comments(body=_record_body())),
            "ps": ps if ps is not None else _ok(stdout=_held()),
            "inspect": inspect if inspect is not None else _ok(stdout=_inspect(node="pr")),
        }
    )


def _gather(*, repo: Path, item: WorkItem, runner: _StubRunner) -> Any:
    module = importlib.import_module(_GATHER_MODULE)
    return module.gather_resume(
        args=_args(),
        repo=repo,
        item=item,
        journal_path=_journal(path=repo / "tmp" / "journal.jsonl"),
        runner=runner,
    )


@pytest.fixture(name="repo")
def _repo(tmp_path: Path) -> Path:
    (tmp_path / "tmp").mkdir()
    return tmp_path


def test_the_executing_node_is_the_newest_checkpoints_target() -> None:
    """The node the run was executing, or the edge target its last outcome selected."""
    assert _RECORD_PATH.is_file()
    module = importlib.import_module(_RECORD_MODULE)
    payload: object = [
        {
            "checkpoints": [
                {"checkpoint": {"next_node_id": "review"}},
                {"checkpoint": {"next_node_id": "pr"}},
            ]
        }
    ]
    assert module.executing_node_from_payload(payload=payload) == "pr"


def test_a_run_record_with_no_checkpoint_names_no_executing_node() -> None:
    """None sends the anchor to the verdict fallback rather than to a guessed node."""
    assert _RECORD_PATH.is_file()
    module = importlib.import_module(_RECORD_MODULE)
    assert module.executing_node_from_payload(payload=[{"status": "failed"}]) is None
    assert module.executing_node_from_payload(payload=None) is None


def test_a_blank_next_node_id_names_no_executing_node() -> None:
    """A blank is not a node name; pointing `start` at one yields an invalid graph."""
    assert _RECORD_PATH.is_file()
    module = importlib.import_module(_RECORD_MODULE)
    payload: object = [{"checkpoint": {"next_node_id": "   "}}]
    assert module.executing_node_from_payload(payload=payload) is None


def test_the_factory_record_wins_over_the_verdict(repo: Path) -> None:
    """Same records, factory holding the run: resumed_at is the factory's own node."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner())
    assert gather.anchor is not None
    assert gather.anchor.resumed_at == "pr"
    assert gather.anchor.source == SOURCE_FACTORY_RUN
    assert gather.anchor.head == _HEAD


def test_a_factory_that_no_longer_holds_the_run_falls_back_to_the_verdict(repo: Path) -> None:
    """Scenario 143: an authoritative not-found is an answer, so `captured` means review."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner(ps=_ok(stdout=json.dumps([]))))
    assert gather.anchor is not None
    assert gather.anchor.resumed_at == "review"
    assert gather.anchor.source == SOURCE_LATEST_RECORD
    assert gather.observation.liveness_observed is True
    assert gather.observation.live_runs == ()


def test_an_unanswerable_factory_is_unobserved_and_not_an_empty_inventory(repo: Path) -> None:
    """The two carry the same empty tuple and must produce opposite decisions."""
    assert _GATHER_PATH.is_file()
    gather = _gather(
        repo=repo,
        item=_item(),
        runner=_runner(ps=CommandResult(exit_code=1, stdout="", stderr="no route")),
    )
    assert gather.observation.liveness_observed is False
    assert gather.observation.live_runs == ()


def test_a_live_earlier_run_is_reported_with_its_status(repo: Path) -> None:
    """The refusal must name the run id AND its status, so both ride together."""
    assert _GATHER_PATH.is_file()
    gather = _gather(
        repo=repo, item=_item(), runner=_runner(ps=_ok(stdout=_held(status="blocked")))
    )
    assert [(one.run_id, one.status) for one in gather.observation.live_runs] == [
        (_EARLIER_RUN, "blocked")
    ]


def test_an_unreadable_forge_is_carried_as_unobserved(repo: Path) -> None:
    """The arm that must not read as "this branch carries no pull request"."""
    assert _GATHER_PATH.is_file()
    gather = _gather(
        repo=repo,
        item=_item(),
        runner=_runner(listing=CommandResult(exit_code=1, stdout="", stderr="gh: 503")),
    )
    assert gather.observation.forge_observed is False
    assert gather.observation.pull_request is None
    assert gather.anchor is None


def test_a_branch_with_no_pull_request_is_observed_and_empty(repo: Path) -> None:
    """The control for the arm above: an answer, not an outage."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner(listing=_ok(stdout=json.dumps([]))))
    assert gather.observation.forge_observed is True
    assert gather.observation.pull_request is None
    assert gather.anchor is None


def test_the_pull_request_number_state_and_head_ride_from_the_forge(repo: Path) -> None:
    """Three refusals are decided on these three values, so all three are carried."""
    assert _GATHER_PATH.is_file()
    gather = _gather(
        repo=repo,
        item=_item(),
        runner=_runner(listing=_ok(stdout=_pr_listing(state="MERGED", head=_MOVED_HEAD))),
    )
    assert gather.observation.pull_request == _PR
    assert gather.observation.pull_request_state == "MERGED"
    assert gather.observation.pull_request_head == _MOVED_HEAD
    assert gather.observation.anchor_head == _HEAD
    assert gather.branch == _BRANCH


def test_the_items_own_status_and_blocked_reason_are_carried(repo: Path) -> None:
    """The first refusal names the status and picks its remedy from it."""
    assert _GATHER_PATH.is_file()
    parked = dataclasses.replace(_item(), status="blocked", blocked_reason="needs-human")
    gather = _gather(repo=repo, item=parked, runner=_runner())
    assert gather.observation.status == "blocked"
    assert gather.observation.blocked_reason == "needs-human"
    assert gather.observation.work_item_id == _ITEM_ID


def test_the_earlier_run_identifiers_lead_with_the_records_own_run_id(repo: Path) -> None:
    """`resumes_anchored_on` names each resume by the first identifier, so order matters."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner())
    assert gather.earlier_run_ids[0] == _EARLIER_RUN
    assert _EARLIER_DISPATCH in gather.earlier_run_ids


def test_the_earlier_run_identifiers_carry_no_duplicate(repo: Path) -> None:
    """The journal names the run id too; a doubled id would double-name the resume."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner())
    assert len(gather.earlier_run_ids) == len(set(gather.earlier_run_ids))


def test_the_workflow_name_is_the_one_the_earlier_dispatch_record_names(repo: Path) -> None:
    """The clause: the resumed run runs the workflow the earlier dispatch record names."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner())
    assert gather.workflow_name == "implement-work-item"


def test_an_assertion_the_record_does_not_carry_is_reported_as_changed(repo: Path) -> None:
    """The inherited records must prove exactly what this dispatch is graded on."""
    assert _GATHER_PATH.is_file()
    gather = _gather(
        repo=repo,
        item=_item(assertion="An assertion that arrived after the earlier run."),
        runner=_runner(),
    )
    assert gather.observation.changed_assertions == (
        "An assertion that arrived after the earlier run.",
    )


def test_an_assertion_the_record_carries_wrapped_is_not_reported_as_changed(repo: Path) -> None:
    """A record is prose: the publisher may hard-wrap, so matching is wrap-independent."""
    assert _GATHER_PATH.is_file()
    wrapped = _record_body(assertion="The resume enters at the\nunfinished stage.")
    gather = _gather(
        repo=repo, item=_item(), runner=_runner(view=_ok(stdout=_comments(body=wrapped)))
    )
    assert gather.observation.changed_assertions == ()


def test_an_unreadable_comment_list_anchors_nothing(repo: Path) -> None:
    """A record nobody read cannot anchor a resume; the ladder refuses on the head."""
    assert _GATHER_PATH.is_file()
    gather = _gather(
        repo=repo,
        item=_item(),
        runner=_runner(view=CommandResult(exit_code=1, stdout="", stderr="gh: 503")),
    )
    assert gather.anchor is None
    assert gather.observation.anchor_head is None
    assert gather.observation.pull_request == _PR


def test_a_live_ownership_lock_is_reported_with_its_age(repo: Path, monkeypatch: Any) -> None:
    """The refusal names the lock age, as `reconcile-merged` does."""
    assert _GATHER_PATH.is_file()
    module = importlib.import_module(_GATHER_MODULE)
    monkeypatch.setattr(
        module,
        "live_dispatch_lock",
        lambda **_: DispatchLock(
            work_item_id=_ITEM_ID, pid=1, started_at_epoch=1.0, dispatch_id=_EARLIER_DISPATCH
        ),
    )
    gather = _gather(repo=repo, item=_item(), runner=_runner())
    assert gather.observation.lock_age_seconds is not None
    assert gather.observation.lock_age_seconds > 0.0


def test_no_lock_is_reported_as_no_age_rather_than_zero(repo: Path) -> None:
    """Zero would read as a lock taken this instant and refuse every clean resume."""
    assert _GATHER_PATH.is_file()
    gather = _gather(repo=repo, item=_item(), runner=_runner())
    assert gather.observation.lock_age_seconds is None


def test_earlier_resumes_of_the_same_pull_request_are_counted(repo: Path) -> None:
    """The third-resume bound is per PULL REQUEST, so the number is part of the query."""
    assert _GATHER_PATH.is_file()
    journal = _journal(path=repo / "tmp" / "journal.jsonl")
    with journal.open("a", encoding="utf-8") as handle:
        _ = handle.write(
            json.dumps(
                {
                    "stage": "resume",
                    "work_item_id": _ITEM_ID,
                    "earlier_run_ids": [_EARLIER_RUN],
                    "pull_request": _PR,
                    "resumed_at": "pr",
                }
            )
            + "\n"
        )
    module = importlib.import_module(_GATHER_MODULE)
    gather = module.gather_resume(
        args=_args(),
        repo=repo,
        item=_item(),
        journal_path=journal,
        runner=_runner(),
    )
    assert gather.observation.earlier_resumes == (_EARLIER_RUN,)

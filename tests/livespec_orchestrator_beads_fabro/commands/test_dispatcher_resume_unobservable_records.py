"""A record list nobody read is not a pull request that carries no record.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" scopes the cancel-record anchor on a MEASUREMENT of the pull
request: "When no proof record on the pull request carries the identifier of the
item's latest journaled dispatch, and that dispatch's journal carries a
`watchdog-stall-cancel` record ... naming a published head, that cancel record
anchors the resume instead." A read that FAILED establishes neither half of that
condition, and the same clause's closing rule governs what must happen then: the
resume "MUST NOT proceed on an unobservable answer".

WHY THIS NEEDED ITS OWN ARM RATHER THAN THE TWO BESIDE IT. The forge-listing and
the factory reads were already carried distinctly — `forge_observed` and
`liveness_observed` each render their own refusal. The pull request's RECORD list
was not: `read_pull_request_records` returns `None` both for a pull request
carrying no record and for a `gh pr view` that failed, and its own docstring
states the distinction is deliberate ("a failed read is evidence of nothing at
all, and the two must not produce the same verdict"). The gather collapsed the
two into one empty identifier set, so the cancel reader concluded "no proof
record carries this dispatch's identifier" from a read that never happened.

WHAT THAT COST, WHICH IS WHY THE FAILING DIRECTION IS THE ONE ASSERTED. Measured
against the pre-fix gather with one cancel journal and one open pull request at
the cancelled head: with `gh pr view` exiting 0 the resume anchored on the pull
request's own record and entered at `review`, while with `gh pr view` exiting 1 —
the SAME item, the SAME journal, the SAME publication — it anchored on the cancel
row and entered at `proof_capture`, with NO refusal reported either way. So a
transient forge fault silently re-ran capture and review on a tree already proved
and posted a second capture record.

WHY THE CONTROL IS AN OBSERVABLE EMPTY LIST. A gate that simply stopped the
cancel row from anchoring would satisfy every failing case here while retiring
the anchor this item exists to add. The control therefore reads an EMPTY record
list successfully and asserts the cancel row still anchors `proof_capture`: the
two reads differ only in the exit code of one `gh` call, and only a gather that
distinguishes them passes both.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_cancel_anchor import (
    SOURCE_CANCEL_RECORD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
    resume_refusals,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_GATHER_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation"

_ITEM_ID = "bd-ib-fngpwg"
_HEAD = "f" * 40
_CANCELLED_RUN = "01M4Q4XBZ5398FJAWQ131QER60"
_CANCELLED_DISPATCH = "7a636b5e7d60425c942ebdaf10fe7e53"
_PR = 2639
_RECORDS_OBSERVED = "records_observed"
_UNREADABLE = CommandResult(exit_code=1, stdout="", stderr="gh: 503")


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


def _runner(*, listing: CommandResult | None = None, view: CommandResult) -> _StubRunner:
    """A forge answering the listing, a view under test, and a factory holding nothing.

    The factory answers successfully with an EMPTY inventory, which Scenario 143
    calls an answer rather than an outage, so the liveness arm stays silent and
    every refusal these cases read is the one they are about.
    """
    return _StubRunner(
        answers={
            "list": listing
            if listing is not None
            else _ok(stdout=json.dumps([{"number": _PR, "state": "OPEN", "headRefOid": _HEAD}])),
            "view": view,
            "ps": _ok(stdout=json.dumps([])),
        }
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A stall-cancelled run is resumed from its publication",
        description="## Definition of Done\n\n- The resume enters at the unfinished stage.\n",
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


def _cancel_journal(*, path: Path) -> Path:
    """One dispatch's launch row and the stall cancel it took between publication and capture.

    The cancel row's dispatch is the item's LATEST journaled dispatch, which is
    what the clause scopes the anchor to, and its stage is `proof_capture`, which
    is the one stage that admits the anchor. So this journal reads to an anchoring
    row for every reason except what the pull request's records say — which is
    exactly the measurement these cases vary.
    """
    rows: list[dict[str, object]] = [
        {
            "stage": "dispatch-id",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _CANCELLED_DISPATCH,
            "workflow_name": "implement-work-item",
        },
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM_ID,
            "dispatch_id": _CANCELLED_DISPATCH,
            "run_id": _CANCELLED_RUN,
            "factory": "hp",
            "executing_stage": "proof_capture",
            "pull_request": _PR,
            "published_head": _HEAD,
            "published_head_unreadable": None,
        },
    ]
    _ = path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return path


def _gather(*, repo: Path, runner: _StubRunner) -> Any:
    module = importlib.import_module(_GATHER_MODULE)
    return module.gather_resume(
        args=argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None),
        repo=repo,
        item=_item(),
        journal_path=_cancel_journal(path=repo / "tmp" / "journal.jsonl"),
        runner=runner,
    )


def _declared() -> dict[str, dataclasses.Field[object]]:
    return {one.name: one for one in dataclasses.fields(ResumeObservation)}


def _observation(**overrides: object) -> ResumeObservation:
    """A ready item whose every other measurement succeeded.

    Unknown overrides are DROPPED rather than passed through, which is what lets
    a case about a field the observation does not yet carry fail on its own
    assertion instead of on a constructor error.
    """
    fields: dict[str, object] = {
        "work_item_id": _ITEM_ID,
        "status": "ready",
        "liveness_observed": True,
        "pull_request": _PR,
    }
    fields.update({name: value for name, value in overrides.items() if name in _declared()})
    return ResumeObservation(**fields)  # pyright: ignore[reportArgumentType]


@pytest.fixture(name="repo")
def _repo(tmp_path: Path) -> Path:
    (tmp_path / "tmp").mkdir()
    return tmp_path


def test_the_observation_carries_whether_the_record_list_was_read() -> None:
    """Without the field the ladder cannot tell an outage from a pull request with no record."""
    assert _RECORDS_OBSERVED in _declared()


def test_a_read_record_list_is_the_default_so_every_existing_caller_is_unchanged() -> None:
    """A flipped default would refuse every resume on a measurement that succeeded."""
    assert _declared()[_RECORDS_OBSERVED].default is True


def test_an_unreadable_record_list_lets_no_cancel_row_anchor(repo: Path) -> None:
    """The measured defect: a blinded read concluded no proof record names the dispatch."""
    gather = _gather(repo=repo, runner=_runner(view=_UNREADABLE))
    assert gather.anchor is None
    assert gather.observation.anchor_head is None


def test_an_unreadable_record_list_refuses_naming_the_measurement(repo: Path) -> None:
    """The clause's own words: name the measurement it could not take."""
    gather = _gather(repo=repo, runner=_runner(view=_UNREADABLE))
    refusals = resume_refusals(observation=gather.observation)
    assert len(refusals) == 1
    assert "could not report" in refusals[0]
    assert "unobservable answer" in refusals[0]


def test_the_unreadable_record_list_refusal_does_not_advise_a_plain_dispatch(repo: Path) -> None:
    """A plain dispatch reclaims the branch; that is the destruction this arm prevents."""
    gather = _gather(repo=repo, runner=_runner(view=_UNREADABLE))
    refusals = resume_refusals(observation=gather.observation)
    assert "dispatch it plainly" not in refusals[0]
    assert "names a publish-branch head" not in refusals[0]


def test_an_observable_empty_record_list_still_lets_the_cancel_row_anchor(repo: Path) -> None:
    """The control: the two reads differ only in one exit code, and this one proceeds.

    Scenario 172's anchor is the behaviour under test here, so a gate that
    refused on an empty record list would pass every failing case above while
    retiring the recovery path itself.
    """
    gather = _gather(repo=repo, runner=_runner(view=_ok(stdout=json.dumps({"comments": []}))))
    assert gather.anchor is not None
    assert gather.anchor.resumed_at == "proof_capture"
    assert gather.anchor.source == SOURCE_CANCEL_RECORD
    assert gather.observation.records_observed is True
    assert resume_refusals(observation=gather.observation) == ()


def test_a_branch_with_no_pull_request_reports_the_empty_answer_it_always_did(repo: Path) -> None:
    """No pull request is an ANSWER about the records, so the remedy stays a plain dispatch."""
    gather = _gather(
        repo=repo, runner=_runner(listing=_ok(stdout=json.dumps([])), view=_UNREADABLE)
    )
    assert gather.observation.records_observed is True
    refusals = resume_refusals(observation=gather.observation)
    assert len(refusals) == 1
    assert "no open pull request" in refusals[0]
    assert "dispatch it plainly" in refusals[0]


def test_the_status_refusal_still_precedes_the_unreadable_record_list_one() -> None:
    """The order an operator reads is the order the questions were asked."""
    refusals = resume_refusals(
        observation=_observation(
            status="blocked", blocked_reason="needs-human", records_observed=False
        )
    )
    assert len(refusals) == 2
    assert "not ready" in refusals[0]
    assert "could not report" in refusals[1]


def test_an_unreadable_record_list_still_names_the_state_the_forge_did_report() -> None:
    """The forge answered the LISTING, so its state is a measurement and still refuses.

    This is the half that separates this arm from the forge-outage one beside it.
    An unobservable forge listing leaves no number, no state and no head, so one
    unmeasurable read is one refusal; here the listing succeeded and only the
    record read failed, so the merged state is a fact — and its remedy is
    `reconcile-merged`, which a refusal naming only the unread records would
    withhold.

    No HEAD comparison is named either way: with no anchor there is no head to
    compare, so a mismatch here would name a sha nobody read.
    """
    refusals = resume_refusals(
        observation=_observation(
            records_observed=False, pull_request_state="MERGED", pull_request_head=_HEAD
        )
    )
    assert len(refusals) == 2
    assert "could not report" in refusals[0]
    assert "already merged" in refusals[1]
    assert "is now at" not in " ".join(refusals)

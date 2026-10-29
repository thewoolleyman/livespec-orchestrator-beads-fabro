"""A resume after an exhausted merge wait finishes the published pull request.

Scenario 220's recovery chain: the Dispatcher rests the item for resume, the
operator releases it with `resolve-blocked`, and the `resume` that follows MUST
check out the stranded pull request's published head and MUST NOT re-enter
`implement` from the default branch. Measured 2026-10-29 on `bd-ib-sufca7`: the
hand release led to a plain re-dispatch that reclaimed the publish branch and
re-ran implement from master, where a resume from PR #3913's head would have
spent only the rework on the one red check.

THE RUN HAD ALREADY SUCCEEDED, so the factory names its terminal node as the one
the run was in. A resume entering there would end at once and change nothing; the
anchor must normalize it onto the publication-refresh stage, at the pull
request's own head. The same fixture with the pull request's head moved is the
control that the head comparison still refuses, so "no refusal" is evidence
about this item and not about a ladder that refuses nothing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import (
    ResumeGather,
    gather_resume,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    resume_refusals,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM_ID = "bd-ib-sufca7"
_HEAD = "8ad6cd7b2" + "0" * 31
_RUN = "01M62WN80GEFPBFVFT5XHZN27P"
_PR = 3913


@dataclass(kw_only=True)
class _Runner:
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


def _runner(*, pull_request_head: str) -> _Runner:
    body = (
        f"Proof of Done — verified — run {_RUN} — 2026-10-29T05:10:00Z\n\n"
        f"## Assertion 1 — It merges.\n\nPublish-branch head: {_HEAD}\n\n"
        "Proof mode: factory_captured.\n"
    )
    listing = [{"number": _PR, "state": "OPEN", "headRefOid": pull_request_head}]
    held = [{"run_id": _RUN, "status": "succeeded", "goal": f"Work-item: {_ITEM_ID}"}]
    terminal = [{"status": "succeeded", "checkpoints": [{"checkpoint": {"next_node_id": "exit"}}]}]
    return _Runner(
        answers={
            "list": _ok(stdout=json.dumps(listing)),
            "view": _ok(stdout=json.dumps({"comments": [{"body": body, "url": "https://x/c/1"}]})),
            "ps": _ok(stdout=json.dumps(held)),
            "inspect": _ok(stdout=json.dumps(terminal)),
        }
    )


def _released_item() -> WorkItem:
    """The item as `resolve-blocked:<id>:ready` leaves it: `ready`, no assignee."""
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A succeeded run whose merge wait ran out",
        description="## Definition of Done\n\n- It merges.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-29T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _gather(*, repo: Path, runner: _Runner) -> ResumeGather:
    (repo / "tmp").mkdir(exist_ok=True)
    journal = repo / "tmp" / "journal.jsonl"
    _ = journal.write_text(
        json.dumps({"stage": "run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN}) + "\n",
        encoding="utf-8",
    )
    return gather_resume(
        args=argparse.Namespace(fabro_bin="fabro", fabro_factory_target=None),
        repo=repo,
        item=_released_item(),
        journal_path=journal,
        runner=runner,
    )


def test_a_released_item_resumes_from_the_published_head_and_not_from_implement(
    tmp_path: Path,
) -> None:
    gather = _gather(repo=tmp_path, runner=_runner(pull_request_head=_HEAD))

    assert resume_refusals(observation=gather.observation) == ()
    assert gather.anchor is not None
    assert gather.anchor.head == _HEAD
    assert gather.anchor.run_id == _RUN
    assert gather.anchor.resumed_at == "pr_refresh"
    assert gather.anchor.resumed_at not in {"start", "implement"}


def test_a_head_that_moved_since_the_record_is_still_refused(tmp_path: Path) -> None:
    gather = _gather(repo=tmp_path, runner=_runner(pull_request_head="b" * 40))

    refusals = resume_refusals(observation=gather.observation)

    assert any("is now at" in refusal for refusal in refusals)

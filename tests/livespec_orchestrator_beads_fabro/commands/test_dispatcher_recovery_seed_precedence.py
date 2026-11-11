"""One table over every source recovery routing seeds from, and which one wins.

WHY A TABLE, AND WHY ONE. Two fixes each kept their own rule's tests green while
silently reordering the other's: `bd-ib-v6br5b` ranked the latest run's
highest-numbered work-in-progress capture over the observed published head and
over every preservation ref of an earlier run, and `bd-ib-so6fef` then widened the
needs-human lookup to every earlier run and dropped the latest-run scope of the
checkpoint-failed tree row, which put an earlier run's ref back above that
capture. A rule asserted by a test of its own cannot notice another rule moving
underneath it; a pair asserted in one place can. Every row below names the sources
that stand on origin and the route routing must take, so a change to ONE rule that
reorders ANOTHER turns exactly the rows that pair names red.

THE ORDER, HIGHEST FIRST, as the recovery clause of `contracts.md` (the ACP
fallback priority section, on the failed run's preserved work) states it for the
sources routing reads on this base:

1. an admitted resume;
2. a needs-human ref or failed-checkpoint preservation ref published at the LATEST
   run's ending;
3. the latest run's highest-numbered work-in-progress ref;
4. an earlier run's needs-human ref or failed-checkpoint preservation ref, which
   outranks the observed published head only when its run is the head's run or a
   later one;
5. the observed published head;
6. a preserved-publish ref an earlier reclaim left behind.

A non-fallback refusal holds the item before any of them. The current seed ruling
that ranks above a resume is read by recovery routing from the item's ledger
comments, and its rows are in `test_dispatcher_recovery_ruled_seed` and
`test_dispatcher_recovery_ruled_seed_routes`, where the ledger can be seeded; the
fresh ruling that ranks beside it is not read by routing yet and has no row.

The table drives `route_recovery` itself, over a scripted origin, forge and
factory board, so a row exercises the resume admission and the seed choice as one
decision rather than the seed choice alone. Every row also stands the LOWER-ranked
sources on origin beside the winner: a row whose origin held only the winner would
be satisfied by a build that ignored every other source. The work-in-progress
captures are numbered 1, 9 and 10 so that a reading that orders them as text takes
9. The released item's latest dispatch ends in a factory restart cancel or a
whole-run wall-budget cancel in the rows that say so, and in a stall release
otherwise.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_route_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_RESUME,
    ROUTE_SEEDED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routing import (
    route_recovery,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-prec"
_EARLIER = "01EARLIERRUN0000000000000A"
_LATEST = "01LATESTRUN00000000000000B"
_EARLIER_DISPATCH = "e" * 32
_LATEST_DISPATCH = "f" * 32

_NH_EARLIER = f"refs/heads/needs-human/{_EARLIER}"
_NH_LATEST = f"refs/heads/needs-human/{_LATEST}"
_NH_EARLIER_COMMIT = "a1" * 20
_NH_LATEST_COMMIT = "a2" * 20

_WIP = f"refs/livespec/wip/{_ITEM}/{_LATEST}"
_WIP_COMMITS = {1: "b1" * 20, 9: "b9" * 20, 10: "b0" * 20}

_PREFIX = f"refs/livespec/preserved-publish/{_ITEM}"
_TREE_EARLIER_COMMIT = "c1" * 20
_TREE_LATEST_COMMIT = "c2" * 20
_TREE_EARLIER = f"{_PREFIX}/{_TREE_EARLIER_COMMIT}"
_TREE_LATEST = f"{_PREFIX}/{_TREE_LATEST_COMMIT}"
_BASE = "d0" * 20

_BRANCH = f"refs/heads/feat/{_ITEM}"
_HEAD = "e0" * 20
_HEAD_PRESERVED = f"{_PREFIX}/{_HEAD}"
_OLD_HEAD = "e1" * 20
_OLD_HEAD_PRESERVED = f"{_PREFIX}/{_OLD_HEAD}"

_PULL_REQUEST = 3001
_RESUME = "resume"
_RESTART_CANCEL = "cancelled"
_BUDGET_CANCEL = "run-wall-budget-exceeded"
_STALL_RELEASE = "stall-release"


class _Origin:
    """A scripted origin, forge and factory board; an unscripted argv FAILS.

    `ls-remote` is answered from the refs the row stands on origin, by pattern. The
    forge names the pull request only when the row admits a resume, and the factory
    board holds nothing alive. An argv no row scripted fails rather than answering a
    blank success, so a route decided on a blank reply cannot pass for one decided
    on evidence.
    """

    def __init__(self, *, refs: dict[str, str], open_pull_request: bool) -> None:
        self.refs = refs
        self.open_pull_request = open_pull_request

    def answer(self, *, argv: list[str]) -> CommandResult:
        joined = " ".join(argv)
        if argv[:3] == ["git", "ls-remote", "origin"]:
            lines = [
                f"{commit}\t{ref}"
                for ref, commit in sorted(self.refs.items())
                if any(fnmatch.fnmatchcase(ref, pattern) for pattern in argv[3:])
            ]
            return CommandResult(exit_code=0, stdout="\n".join(lines), stderr="")
        if joined.startswith(f"gh pr list --head feat/{_ITEM}"):
            listed = (
                [{"number": _PULL_REQUEST, "state": "OPEN", "headRefOid": _HEAD}]
                if self.open_pull_request
                else []
            )
            return CommandResult(exit_code=0, stdout=json.dumps(listed), stderr="")
        if joined.startswith(f"gh pr view {_PULL_REQUEST} --json comments"):
            return CommandResult(exit_code=0, stdout=json.dumps({"comments": []}), stderr="")
        if "ps -a --json" in joined:
            return CommandResult(exit_code=0, stdout="[]", stderr="")
        message = f"unscripted command reached the shell seam: {joined}"
        raise AssertionError(message)


@dataclass(frozen=True, kw_only=True)
class _Row:
    """The sources that stand on origin, the journal that dates them, and the winner."""

    refs: dict[str, str]
    wins: str
    tree_run: str | None = None
    head_run: str | None = None
    passed_over: tuple[str, ...] = ()
    ending: str = _STALL_RELEASE


def _wip() -> dict[str, str]:
    return {f"{_WIP}/{number}": commit for number, commit in _WIP_COMMITS.items()}


_ROWS: dict[str, _Row] = {
    "wip beats an earlier run's needs-human ref": _Row(
        refs={**_wip(), _NH_EARLIER: _NH_EARLIER_COMMIT},
        wins=f"{_WIP}/10",
        passed_over=(_NH_EARLIER,),
    ),
    "wip beats an earlier run's failed-checkpoint preservation ref": _Row(
        refs={**_wip(), _TREE_EARLIER: _TREE_EARLIER_COMMIT},
        tree_run=_EARLIER,
        wins=f"{_WIP}/10",
    ),
    "wip beats the observed published head": _Row(
        refs={**_wip(), _BRANCH: _HEAD},
        head_run=_LATEST,
        wins=f"{_WIP}/10",
    ),
    "wip beats an earlier run's ref and the head together": _Row(
        refs={
            **_wip(),
            _NH_EARLIER: _NH_EARLIER_COMMIT,
            _TREE_EARLIER: _TREE_EARLIER_COMMIT,
            _BRANCH: _HEAD,
        },
        tree_run=_EARLIER,
        head_run=_EARLIER,
        wins=f"{_WIP}/10",
        passed_over=(_NH_EARLIER,),
    ),
    "wip beats an earlier run's ref after a factory restart cancel": _Row(
        refs={**_wip(), _NH_EARLIER: _NH_EARLIER_COMMIT},
        wins=f"{_WIP}/10",
        passed_over=(_NH_EARLIER,),
        ending=_RESTART_CANCEL,
    ),
    "wip beats an earlier run's ref after a whole-run wall-budget cancel": _Row(
        refs={**_wip(), _NH_EARLIER: _NH_EARLIER_COMMIT},
        wins=f"{_WIP}/10",
        passed_over=(_NH_EARLIER,),
        ending=_BUDGET_CANCEL,
    ),
    "the latest run's needs-human ref beats its wip": _Row(
        refs={**_wip(), _NH_LATEST: _NH_LATEST_COMMIT, _NH_EARLIER: _NH_EARLIER_COMMIT},
        wins=_NH_LATEST,
        passed_over=(_NH_EARLIER,),
    ),
    "the latest run's failed-checkpoint preservation ref beats its wip": _Row(
        refs={**_wip(), _TREE_LATEST: _TREE_LATEST_COMMIT},
        tree_run=_LATEST,
        wins=_TREE_LATEST,
    ),
    "an earlier run's needs-human ref beats a head its own run published": _Row(
        refs={_NH_EARLIER: _NH_EARLIER_COMMIT, _BRANCH: _HEAD},
        head_run=_EARLIER,
        wins=_NH_EARLIER,
    ),
    "an earlier run's needs-human ref loses to a later run's head": _Row(
        refs={_NH_EARLIER: _NH_EARLIER_COMMIT, _BRANCH: _HEAD},
        head_run=_LATEST,
        wins=_HEAD_PRESERVED,
        passed_over=(_NH_EARLIER,),
    ),
    "an earlier run's preservation ref loses to a later run's head": _Row(
        refs={_TREE_EARLIER: _TREE_EARLIER_COMMIT, _BRANCH: _HEAD},
        tree_run=_EARLIER,
        head_run=_LATEST,
        wins=_HEAD_PRESERVED,
    ),
    "the observed published head beats an earlier reclaim's preserved head": _Row(
        refs={_BRANCH: _HEAD, _OLD_HEAD_PRESERVED: _OLD_HEAD},
        wins=_HEAD_PRESERVED,
    ),
    "an earlier reclaim's preserved head is the last source": _Row(
        refs={_OLD_HEAD_PRESERVED: _OLD_HEAD},
        wins=_OLD_HEAD_PRESERVED,
    ),
    "an admitted resume beats every seed source": _Row(
        refs={
            **_wip(),
            _NH_LATEST: _NH_LATEST_COMMIT,
            _NH_EARLIER: _NH_EARLIER_COMMIT,
            _TREE_LATEST: _TREE_LATEST_COMMIT,
            _BRANCH: _HEAD,
        },
        tree_run=_LATEST,
        head_run=_LATEST,
        wins=_RESUME,
    ),
}


def _journal(*, tmp_path: Path, row: _Row) -> JournalFile:
    """The dispatch journal in the order the dispatches happened, oldest run first.

    Each run's tree row and published head sit beside THAT run's own record: the
    journal is append-only, so a row for an earlier run written after the latest
    run's record would make the earlier run the newest one the journal names. The
    latest dispatch then ends the way the row says: a stall release that anchors a
    resume when the row admits one, else a cancel or a stall release that anchors
    nothing.
    """
    records: list[dict[str, object]] = []
    for run, dispatch, ref in (
        (_EARLIER, _EARLIER_DISPATCH, _TREE_EARLIER),
        (_LATEST, _LATEST_DISPATCH, _TREE_LATEST),
    ):
        records.append({"stage": "dispatch-id", "work_item_id": _ITEM, "dispatch_id": dispatch})
        records.append({"stage": "fabro-run", "work_item_id": _ITEM, "run_id": run})
        if row.tree_run == run:
            records.append(
                {
                    "stage": PRESERVED_TREE_STAGE,
                    "work_item_id": _ITEM,
                    "run_id": run,
                    "base_commit": _BASE,
                    "preservation_ref": ref,
                }
            )
        if row.head_run == run:
            records.append({"work_item_id": _ITEM, "run_id": run, "published_head": _HEAD})
    records.extend(_ending(row=row))
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    _ = journal.path.write_text(
        "".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8"
    )
    return journal


def _ending(*, row: _Row) -> list[dict[str, object]]:
    """The rows that end the latest dispatch and release the item for recovery."""
    if row.ending in {_RESTART_CANCEL, _BUDGET_CANCEL}:
        outcome = {"work_item_id": _ITEM, "status": row.ending, "detail": ""}
        return [{"stage": "outcome", "outcome": outcome}]
    # Only a row that admits a resume names a pull request and a published head on
    # the stall record: a head named here belongs to the LATEST run, which would
    # make every ref of an earlier run lose to it by the run-age bound.
    anchor: dict[str, object] = (
        {"pull_request": _PULL_REQUEST, "published_head": _HEAD} if row.wins == _RESUME else {}
    )
    return [
        {
            "stage": "watchdog-stall-cancel",
            "work_item_id": _ITEM,
            "dispatch_id": _LATEST_DISPATCH,
            "run_id": _LATEST,
            "factory": "hp",
            "executing_stage": "proof_capture",
            **anchor,
        },
        {"stage": "stall-cancel-release", "work_item_id": _ITEM, "status": "ready"},
    ]


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="ready",
        title="A released item whose preserved work is ranked",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_the_scripted_origin_refuses_a_command_no_row_scripted() -> None:
    """The instrument's own control: every claim below rests on this refusal firing.

    A seam that answered an unscripted argv with a blank success could not tell a
    route decided on the evidence a row stands from one decided on an empty reply.
    """
    with pytest.raises(AssertionError, match="unscripted command"):
        _ = _Origin(refs={}, open_pull_request=False).answer(argv=["git", "fetch", "origin"])


@pytest.mark.parametrize("name", list(_ROWS))
def test_the_source_routing_takes_is_the_one_the_precedence_table_names(
    *, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _ROWS[name]
    resumes = row.wins == _RESUME
    origin = _Origin(refs=row.refs, open_pull_request=resumes)

    def _run(
        _self: ShellCommandRunner,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        return origin.answer(argv=argv)

    monkeypatch.setattr(ShellCommandRunner, "run", _run)
    journal = _journal(tmp_path=tmp_path, row=row)
    routing = route_recovery(
        args=argparse.Namespace(
            repo=str(tmp_path),
            journal=str(journal.path),
            item=None,
            items=None,
            skip_ledger_check=True,
            workflow_name=None,
            fabro_bin="/usr/local/bin/fabro",
        ),
        repo=tmp_path,
        candidates=[_item()],
        journal=journal,
    )
    route = routing.route_for(work_item_id=_ITEM)
    assert route is not None
    if resumes:
        assert route.route == ROUTE_RESUME
        assert route.seed is None
        return
    assert route.route == ROUTE_SEEDED
    assert route.seed is not None
    assert route.seed.preservation_ref == row.wins
    record = recovery_route_record(work_item_id=_ITEM, route=ROUTE_SEEDED, seed=route.seed)
    assert {entry["ref"] for entry in record["passed_over_needs_human"]} == set(row.passed_over)
    assert {entry["reason"] for entry in record["passed_over_needs_human"]} <= {"not-taken"}

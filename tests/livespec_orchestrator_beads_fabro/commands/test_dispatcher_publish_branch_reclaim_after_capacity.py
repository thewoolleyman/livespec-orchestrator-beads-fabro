"""The publish-branch reclaim belongs to the LAUNCH, not to the selection.

The reclaim is DESTRUCTIVE to origin: it preserves a dead run's surviving head to
`refs/livespec/preserved-publish/<item>/<sha>` and then DELETES `feat/<item>`,
which closes any pull request open on that branch. It ran at the end of
`pre_dispatch_wall_exit`, which every entry point calls BEFORE admission decides
whether the selection has a slot — so a dispatch about to be capacity-deferred
destroyed the branch and then created no run that could republish it.

Measured 2026-10-14 on `bd-ib-zlkjm4`. Its factory run 01M4WYNGFMKM had published
pull request 2948 — reviewed and proof-verified three times — before dying on the
`pr_refresh` re-proof cycle. A re-dispatch through `dispatcher.py loop --item
bd-ib-zlkjm4` journaled `publish-branch-reclaim` for `feat/bd-ib-zlkjm4` at
13:29:26Z at head f3f139b2, and the forge closed pull request 2948 in the same
second. At 13:29:43Z that same dispatch ended `capacity-deferred` with detail
"capacity deferred: active_count=11 wip_cap=10 free_slots=0 ...", having created
no Fabro run at all. The reviewed work survived only because the preservation ref
exists; the branch had to be recreated by hand and the pull request reopened.

WHAT THIS FILE ASSERTS FIRST, AND WHY IT IS THIS HALF. Moving a destructive act
later is only safe if it still HAPPENS, so the launched half comes first: each
launch path reclaims for exactly the item it is about to launch, between the
valve's claim and the run. Both paths are driven, because they are two separate
call sites and a fix wired into one of them leaves the other's recovery stuck.

EVERY CASE HERE IS SCRIPTED AGAINST A SURVIVING BRANCH ON ORIGIN AND A JOURNAL
THAT ALREADY RECORDS AN EARLIER DISPATCH, because without both the reclaim
returns before asking origin anything and no case could return a hit. A fixture
whose item had never been dispatched would report "no reclaim" whatever the code
did, which is the instrument-that-cannot-hit trap.

THE JOURNAL ALSO RECORDS AN EARLIER DISPATCH OF A SECOND ITEM, whose branch
origin carries too. That is the per-item control: a reclaim that walked the
journal rather than the selection it was handed would ask about both.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_wave as loop_wave
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_publish_branch_reclaim as reclaim,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_run_commands as run_commands
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import Admission
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import ReworkPass
from livespec_orchestrator_beads_fabro.types import WorkItem
from returns.io import IOSuccess

_ITEM_ID = "bd-ib-zlkjm4"
_BRANCH = f"feat/{_ITEM_ID}"
# A second item the journal also records an earlier dispatch for, so a reclaim
# that walked the journal instead of the selection it was handed is caught.
_OTHER_ITEM_ID = "bd-ib-huoyk7"
_OTHER_BRANCH = f"feat/{_OTHER_ITEM_ID}"
# The head the dead run published, and the one the preserved ref must carry.
_DEAD_HEAD = "f3f139b28469c7efaae32dcb897d73518edbaadd"
_RECLAIM_STAGE_PREFIX = "publish-branch-reclaim"

# The acts whose ORDER this file is about, in the order a launched item must see
# them. Spelled as constants so each assertion reads as a sequence of acts rather
# than as a list of argv fragments.
_ADMIT = "admission decided"
_ASK_ORIGIN = "asked origin for the publish branch"
_PRESERVE = "created the preservation ref"
_DELETE = "deleted the publish branch"
_LAUNCH = "launched the run"


@dataclass(kw_only=True)
class _Runner:
    """A scripted subprocess seam that also writes to the shared timeline.

    Keyed by argv substring so a case states only what it scripts, and appending
    each argv to `events` is what lets the ORDER of a remote mutation be read
    against the admission and the launch rather than counted on its own.
    """

    events: list[str]
    answers: dict[str, CommandResult] = field(default_factory=dict)
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
        _ = cwd, timeout_seconds, env, stdin
        self.argvs.append(list(argv))
        joined = " ".join(argv)
        self.events.append(joined)
        for needle, result in self.answers.items():
            if needle in joined:
                return result
        return CommandResult(exit_code=0, stdout="", stderr="")


def _runner(*, events: list[str]) -> _Runner:
    """A seam whose origin carries BOTH items' publish branches, at the dead head."""
    return _Runner(
        events=events,
        answers={
            f"ls-remote origin refs/heads/{_BRANCH}": CommandResult(
                exit_code=0, stdout=f"{_DEAD_HEAD}\trefs/heads/{_BRANCH}\n", stderr=""
            ),
            f"ls-remote origin refs/heads/{_OTHER_BRANCH}": CommandResult(
                exit_code=0, stdout=f"{_DEAD_HEAD}\trefs/heads/{_OTHER_BRANCH}\n", stderr=""
            ),
        },
    )


def _timeline(*, events: list[str]) -> list[str]:
    """The timeline reduced to the acts whose order this file is about.

    A reduction rather than a whole-sequence assertion because the liveness probe
    builds its own argv through the Fabro port facade, and pinning that argv here
    would make an unrelated flag change fail every case in this file.
    """
    marks: list[str] = []
    for event in events:
        if event in (_ADMIT, _LAUNCH):
            marks.append(event)
        elif "ls-remote" in event:
            marks.append(_ASK_ORIGIN)
        elif event.startswith("gh api --method POST"):
            marks.append(_PRESERVE)
        elif event.startswith("gh api --method DELETE"):
            marks.append(_DELETE)
    return marks


def _work_item(*, item_id: str) -> WorkItem:
    """A selected candidate, carrying nothing these seams read but its id."""
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="A capacity-deferred dispatch must not run the publish-branch reclaim",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-14T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _journal_after_a_previous_dispatch(*, tmp_path: Path, item_ids: Sequence[str]) -> JournalFile:
    """A journal recording one previous dispatch per named item.

    The record SHAPES are the production ones — the `dispatch-id` stage record
    written before launch and the `fabro-run` record carrying the run id —
    because the reclaim reads the same file the Dispatcher writes. Written
    directly rather than through `append`, which stamps an invoker no writer may
    supply.
    """
    journal = JournalFile(path=tmp_path / "fabro-dispatch-journal.jsonl")
    lines = [
        json.dumps(record)
        for item_id in item_ids
        for record in (
            {"stage": "dispatch-id", "work_item_id": item_id, "dispatch_id": f"d-{item_id}"},
            {"stage": "fabro-run", "work_item_id": item_id, "run_id": f"01M4WY{item_id}"},
        )
    ]
    _ = journal.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return journal


def _reclaim_rows(*, journal: JournalFile) -> tuple[dict[str, Any], ...]:
    """This valve's own records, in order, with the pre-seeded history filtered out."""
    written = (
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    )
    return tuple(
        record for record in written if str(record.get("stage")).startswith(_RECLAIM_STAGE_PREFIX)
    )


def _args(*, repo: Path, journal: JournalFile) -> argparse.Namespace:
    """The dispatch namespace every seam below reads its own inputs off."""
    return argparse.Namespace(
        repo=str(repo),
        journal=str(journal.path),
        item=_ITEM_ID,
        items=None,
        budget=1,
        parallel=1,
        as_json=False,
        dry_run=False,
        skip_ledger_check=True,
        workflow_name=None,
        fabro_bin="/usr/local/bin/fabro",
    )


def _green_outcome(*, item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=item_id,
        status="green",
        stage="done",
        pr_number=2948,
        merge_sha="deadbeef",
        detail="merged, post-merge janitor green",
    )


def _admitted_one(*, item: WorkItem) -> Admission:
    """The valve's answer when the one candidate got a slot and was claimed."""
    return Admission(admitted=[item], deferred=[], refused=[])


def _stub_wave_seams(
    *, monkeypatch: pytest.MonkeyPatch, admission: Admission, events: list[str]
) -> None:
    """Stand in everything the wave does EXCEPT the reclaim decision and its order."""
    monkeypatch.setattr(loop_wave, "await_usable_credential", lambda **_kwargs: None)
    monkeypatch.setattr(loop_wave, "resolve_acp_preflight", lambda **_kwargs: None)

    def _admit(**_kwargs: Any) -> Admission:
        events.append(_ADMIT)
        return admission

    monkeypatch.setattr(loop_wave, "admit_and_select", _admit)
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        loop_wave, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        events.append(_LAUNCH)
        return _green_outcome(item_id=str(kwargs["item"].id))

    monkeypatch.setattr(loop_wave, "dispatch_one", _launch)


def _drive_loop_wave(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    admission: Admission,
    events: list[str],
) -> tuple[JournalFile, _Runner]:
    """One drain wave, with the reclaim live and its subprocess seam scripted.

    The seam is monkeypatched rather than injected because the reclaim constructs
    the production one itself — it is handed no runner — so a drive that could not
    reach that construction would leave the whole remote half of this decision
    unexercised.
    """
    item = _work_item(item_id=_ITEM_ID)
    journal = _journal_after_a_previous_dispatch(
        tmp_path=tmp_path, item_ids=(_ITEM_ID, _OTHER_ITEM_ID)
    )
    runner = _runner(events=events)
    monkeypatch.setattr(reclaim, "ShellCommandRunner", lambda: runner)
    _stub_wave_seams(monkeypatch=monkeypatch, admission=admission, events=events)

    _ = loop_wave.dispatch_loop_wave(
        args=_args(repo=tmp_path, journal=journal),
        repo=tmp_path,
        items=[item],
        selected_candidates=[item],
        journal=journal,
        janitor=None,
        rework=ReworkPass(),
    )
    return journal, runner


def _stub_single_dispatch(
    *,
    monkeypatch: pytest.MonkeyPatch,
    item: WorkItem,
    journal: JournalFile,
    admission: Admission,
    events: list[str],
) -> None:
    """Stand in every `dispatch --item` seam around the launch this case is about.

    The shared wall is stood in deliberately: what it does with the reclaim is
    asserted on the wall itself, and leaving it live here would mix two positions
    into one timeline.
    """
    monkeypatch.setattr(run_commands, "dispatch_preamble", lambda **_kwargs: (None, None))
    monkeypatch.setattr(run_commands, "arm_otel_egress", lambda **_kwargs: None)
    monkeypatch.setattr(run_commands, "prepare", lambda **_kwargs: ([item], journal))
    monkeypatch.setattr(
        run_commands, "apply_factory_size_dispatch_entry", lambda **_kwargs: IOSuccess(())
    )
    monkeypatch.setattr(run_commands, "ready_items", lambda **_kwargs: [item])
    monkeypatch.setattr(run_commands, "pre_dispatch_wall_exit", lambda **_kwargs: None)

    def _admit(**_kwargs: Any) -> Admission:
        events.append(_ADMIT)
        return admission

    monkeypatch.setattr(run_commands, "admit_and_select", _admit)
    monkeypatch.setattr(
        run_commands, "args_with_dispatch_factory_target", lambda **kwargs: kwargs["args"]
    )
    monkeypatch.setattr(
        run_commands, "args_with_dispatch_workflow_name", lambda **kwargs: kwargs["args"]
    )

    def _launch(**kwargs: Any) -> DispatchOutcome:
        events.append(_LAUNCH)
        return _green_outcome(item_id=str(kwargs["item"].id))

    monkeypatch.setattr(run_commands, "dispatch_one", _launch)
    monkeypatch.setattr(run_commands, "dispatch_tail_exit", lambda **_kwargs: 0)


def test_an_item_selected_to_launch_is_reclaimed_for_before_its_run_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The drain's launched item: claimed, then reclaimed for, then launched.

    The order is the assertion. The reclaim must land AFTER the valve, because
    only then is it known that this item will actually run; and BEFORE the
    launch, because clearing the branch is what lets the new run's
    `publish_draft` push a plain fast-forward at all.
    """
    events: list[str] = []
    item = _work_item(item_id=_ITEM_ID)

    journal, runner = _drive_loop_wave(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        admission=_admitted_one(item=item),
        events=events,
    )

    assert _timeline(events=events) == [_ADMIT, _ASK_ORIGIN, _PRESERVE, _DELETE, _LAUNCH]
    # Exactly this item's branch was asked about, though the journal records an
    # earlier dispatch of another item whose branch origin also carries.
    assert [argv for argv in runner.argvs if "ls-remote" in " ".join(argv)] == [
        ["git", "ls-remote", "origin", f"refs/heads/{_BRANCH}"]
    ]
    assert [
        {key: record[key] for key in ("stage", "work_item_id", "branch", "head")}
        for record in _reclaim_rows(journal=journal)
    ] == [
        {
            "stage": reclaim.PUBLISH_BRANCH_RECLAIM_STAGE,
            "work_item_id": _ITEM_ID,
            "branch": _BRANCH,
            "head": _DEAD_HEAD,
        }
    ]


def test_the_single_dispatch_path_reclaims_for_the_item_it_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dispatch --item` is the second launch path, and it is wired separately.

    It enforces no WIP cap, so nothing here can be capacity-deferred — which is
    exactly why it needs its own case: a fix wired only into the drain would leave
    this path with no reclaim at all, and its recovery stuck at `publish_draft`.
    """
    events: list[str] = []
    item = _work_item(item_id=_ITEM_ID)
    journal = _journal_after_a_previous_dispatch(
        tmp_path=tmp_path, item_ids=(_ITEM_ID, _OTHER_ITEM_ID)
    )
    runner = _runner(events=events)
    monkeypatch.setattr(reclaim, "ShellCommandRunner", lambda: runner)
    _stub_single_dispatch(
        monkeypatch=monkeypatch,
        item=item,
        journal=journal,
        admission=_admitted_one(item=item),
        events=events,
    )

    exit_code = run_commands.run_dispatch_command(args=_args(repo=tmp_path, journal=journal))

    assert exit_code == 0
    assert _timeline(events=events) == [_ADMIT, _ASK_ORIGIN, _PRESERVE, _DELETE, _LAUNCH]
    assert [record["work_item_id"] for record in _reclaim_rows(journal=journal)] == [_ITEM_ID]

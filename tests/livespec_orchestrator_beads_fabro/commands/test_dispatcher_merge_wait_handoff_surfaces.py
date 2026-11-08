"""A handed-off dispatch is a success on every surface that reports a dispatch ending.

Binds the "dispatch exits 0" and "dispatching process ends" lines of
`SPECIFICATION/scenarios.md` Scenario 220 on the surfaces that carry the status
past the engine: the `drive` result and its exit code, the terminal alarm, the
emitted payload, and the attention lane that finds stranded dispatches.

EVERY CASE SITS BESIDE THE ENDING IT MUST NOT BE MISTAKEN FOR. A handed-off item is
`active` with no live lock by design, which is exactly the shape the stranded-
dispatch lane reports, so the lane's `failed` outcome is the control: a lane that
had stopped reporting anything would satisfy the handed-off case alone.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    claimed_active_projection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    release_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import emit_outcomes
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff import (
    MergeWaitHandedOff,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import terminal_events
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    CommandRun,
    run_impl_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_stranded_dispatch import (
    stranded_dispatch_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_ITEM = "bd-ib-handoff-surface"


def _handed_off() -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status="handed-off",
        stage="merge-poll",
        pr_number=4615,
        merge_sha=None,
        detail="merge-wait-handed-off: ...",
        fabro_run_id="01M6VNKFXRA85Q8WF0JV23204B",
        merge_wait_handed_off=MergeWaitHandedOff(
            factory="petri", pr_head="head1111", waited_seconds=2400, running_checks=("check-lint",)
        ),
    )


def test_the_alarm_does_not_fire_for_a_handed_off_dispatch() -> None:
    handed = _handed_off()
    failed = DispatchOutcome(
        work_item_id=_ITEM,
        status="failed",
        stage="merge-poll",
        pr_number=1,
        merge_sha=None,
        detail="x",
    )

    assert terminal_events(outcomes=(handed,), include_loop_summary=True) == ()
    assert [
        e.outcome_class
        for e in terminal_events(outcomes=(handed, failed), include_loop_summary=False)
    ] == ["failed"]


def test_the_emitted_payload_carries_the_handoff_only_for_a_handed_off_outcome(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plain = DispatchOutcome(
        work_item_id=_ITEM, status="green", stage="done", pr_number=1, merge_sha="a", detail="x"
    )

    emit_outcomes(outcomes=[_handed_off(), plain], as_json=True)

    emitted = json.loads(capsys.readouterr().out)
    assert emitted[0]["merge_wait_handed_off"]["running_checks"] == ["check-lint"]
    assert emitted[0]["merge_wait_handed_off"]["waited_seconds"] == 2400
    assert "merge_wait_handed_off" not in emitted[1]


def test_the_drive_result_reports_a_handed_off_dispatch_as_a_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    emit_outcomes(outcomes=[_handed_off()], as_json=True)
    emitted = capsys.readouterr().out

    def _runner(*, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        del cwd
        return CommandRun(argv=argv, returncode=0, stdout=emitted, stderr="")

    result = run_impl_dispatch(
        repo=tmp_path,
        work_item_ref=_ITEM,
        runner=_runner,
        dispatcher_bin=tmp_path / "dispatcher.py",
        acp_nodes=(),
        workflow_name=None,
        identity=None,
    )

    assert result["status"] == "handed-off"
    assert "handed the merge wait" in result["summary"]
    assert "reconciliation" in result["summary"]


def _active_item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="task",
        status="active",
        title="t",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-11-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _no_live_lock(*, repo: Path, work_item_id: str) -> None:
    _ = (repo, work_item_id)


def _attention(*, root: Path, outcome_status: str) -> list[str]:
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True)
    records = [
        {"stage": "dispatch-id", "work_item_id": _ITEM},
        {
            "stage": "outcome",
            "outcome": {
                "work_item_id": _ITEM,
                "status": outcome_status,
                "stage": "merge-poll",
                "pr_number": 4615,
                "merge_sha": None,
            },
        },
    ]
    _ = journal.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return [
        item.id
        for item in stranded_dispatch_items(
            project_root=root,
            repo="repo",
            items=[_active_item()],
            live_lock_lookup=_no_live_lock,
        )
    ]


def test_a_handed_off_item_is_not_reported_as_a_stranded_dispatch(tmp_path: Path) -> None:
    assert _attention(root=tmp_path, outcome_status="handed-off") == []


def test_a_failed_outcome_for_the_same_item_is_still_reported_as_stranded(tmp_path: Path) -> None:
    assert _attention(root=tmp_path, outcome_status="failed") == [
        f"host-only:stranded-dispatch:{_ITEM}"
    ]


def test_a_handed_off_item_is_not_a_counted_claim_once_its_dispatching_process_ends(
    tmp_path: Path,
) -> None:
    item = _active_item()
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    journal.append(record={"stage": "ledger-admit", "work_item_id": _ITEM})
    journal.append(record={"stage": "outcome", "outcome": asdict(_handed_off())})

    lock = write_dispatch_lock(repo=tmp_path, work_item_id=_ITEM, dispatch_id="01DISPATCH")
    while_the_process_runs = claimed_active_projection(repo=tmp_path, items=[item], journal=journal)
    release_dispatch_lock(path=lock)
    after_it_ends = claimed_active_projection(repo=tmp_path, items=[item], journal=journal)

    assert while_the_process_runs.live_lock_active_ids == (_ITEM,)
    assert while_the_process_runs.active_count == 1
    assert after_it_ends.active_count == 0
    assert after_it_ends.live_lock_active_ids == ()
    assert after_it_ends.journal_unreadable_active_ids == ()

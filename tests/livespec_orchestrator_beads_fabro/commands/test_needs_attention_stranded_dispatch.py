"""Focused coverage for stranded-dispatch attention lanes."""

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    release_to_ready_command,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_stranded_dispatch import (
    stranded_dispatch_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item(*, id_: str, status: str = "active", rework_pending: bool = False) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # type: ignore[arg-type]
        rework_pending=rework_pending,
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-05-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _write_journal_lines(project_root: Path, *, records: list[object]) -> None:
    journal = project_root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True)
    lines = [record if isinstance(record, str) else json.dumps(record) for record in records]
    _ = journal.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _outcome(**overrides: object) -> dict[str, Any]:
    payload: dict[str, object] = {
        "work_item_id": "bd-active",
        "status": "failed",
        "stage": "janitor-post-merge",
        "pr_number": 836,
        "merge_sha": "ba9fdafef895",
    }
    payload.update(overrides)
    return {"stage": "outcome", "outcome": payload}


def _no_live_lock(*, repo: Path, work_item_id: str) -> None:
    _ = (repo, work_item_id)


def test_stranded_dispatch_items_render_reconcile_handoff(tmp_path: Path) -> None:
    _write_journal_lines(tmp_path, records=[_outcome()])

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-active")],
        live_lock_lookup=_no_live_lock,
    )

    assert [item.id for item in attention] == ["host-only:stranded-dispatch:bd-active"]
    assert attention[0].handoff.kind == "shell"
    assert "reconcile-merged" in attention[0].handoff.command


def test_a_rework_pending_item_is_never_reported_as_stranded(tmp_path: Path) -> None:
    """The marker partitions the two populations that share one shape.

    A marked item is `active` with no live lock BY DESIGN — the very shape this
    surface reads as stranded — so without the discriminator the sanctioned
    rework park would be surfaced as a leak. The unmarked sibling carrying the
    identical journal evidence is the control: it still surfaces, which is what
    proves the marked item's absence is the marker's doing.
    """
    _write_journal_lines(
        tmp_path,
        records=[_outcome(), _outcome(work_item_id="bd-marked")],
    )

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[
            _item(id_="bd-active"),
            _item(id_="bd-marked", rework_pending=True),
        ],
        live_lock_lookup=_no_live_lock,
    )

    assert [item.id for item in attention] == ["host-only:stranded-dispatch:bd-active"]


def test_a_merge_held_item_is_never_reported_as_stranded(tmp_path: Path) -> None:
    """The `merge-hold:` label is the second discriminator, beside `rework:pending`.

    A held item is `active` with no live lock BY CONSTRUCTION: its run terminated
    green at the pr stage and its claim was reclaimed, which is exactly the shape
    this surface reads as a leaked claim. The unheld sibling carrying the
    identical journal evidence is the control — it still surfaces, so the held
    item's absence is the discriminator's doing and not the fixture's.
    """
    _write_journal_lines(
        tmp_path,
        records=[_outcome(), _outcome(work_item_id="bd-held")],
    )

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-active"), _item(id_="bd-held")],
        live_lock_lookup=_no_live_lock,
        held_work_item_ids=frozenset({"bd-held"}),
    )

    assert [item.id for item in attention] == ["host-only:stranded-dispatch:bd-active"]


def test_stranded_dispatch_items_render_release_handoff_for_pre_branch_death(
    tmp_path: Path,
) -> None:
    """A pre-branch death hands over the move-to-ready action, not a reconcile.

    The handoff is asserted by IDENTITY against the renderer that owns that
    action, never as a substring of the rendered command. `drive_command`
    embeds `_wrapper_path`, which resolves against the installed package --
    i.e. against the CHECKOUT DIRECTORY -- so a substring assertion also
    ranges over a path this test neither controls nor intends to test. The
    `"reconcile-merged" not in ...` form it replaces failed for a correct
    implementation whenever the repository was checked out under a directory
    whose name carried that token, and read exactly like a real regression in
    the change under test. Identity is also the stronger instrument in the
    direction that matters: a handoff rendering `reconcile_merged_command`
    here fails this assertion, whereas `"--action reconcile-merged" not in
    ...` could never have matched that command's argv at all.
    """
    _write_journal_lines(
        tmp_path,
        records=[
            {"stage": "ledger-admit", "work_item_id": "bd-active"},
            {"stage": "dispatch-id", "work_item_id": "bd-active", "dispatch_id": "dispatch-1"},
        ],
    )

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-active")],
        live_lock_lookup=_no_live_lock,
    )

    assert [item.id for item in attention] == ["host-only:stranded-dispatch:bd-active"]
    stranded = attention[0]
    assert "dispatch-id" in stranded.summary
    assert "1 prior attempt" in stranded.summary
    assert stranded.handoff.kind == "shell"
    assert stranded.handoff.command == release_to_ready_command(
        project_root=tmp_path, work_item="bd-active"
    )


def test_stranded_dispatch_items_render_pr_handoff_for_unmerged_pr_failure(
    tmp_path: Path,
) -> None:
    _write_journal_lines(
        tmp_path,
        records=[_outcome(stage="merge-poll", pr_number=2018, merge_sha=None)],
    )

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-active")],
        live_lock_lookup=_no_live_lock,
    )

    assert [item.id for item in attention] == ["host-only:stranded-dispatch:bd-active"]
    stranded = attention[0]
    assert "PR #2018" in stranded.summary
    assert "merge-poll" in stranded.summary
    assert stranded.handoff.kind == "shell"
    assert "gh pr view 2018" in stranded.handoff.command
    assert "reconcile-merged" not in stranded.handoff.command


def test_stranded_dispatch_items_ignore_watchable_run_without_lock(tmp_path: Path) -> None:
    _write_journal_lines(
        tmp_path,
        records=[{"stage": "dispatch-id", "work_item_id": "bd-active"}],
    )

    def _watchable_run(*, repo: Path, work_item_id: str) -> object | None:
        _ = (repo, work_item_id)
        return object()

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-active")],
        live_lock_lookup=_no_live_lock,
        watchable_run_lookup=_watchable_run,
    )

    assert attention == []


def test_stranded_dispatch_items_fail_soft_when_journal_is_absent(tmp_path: Path) -> None:
    assert (
        stranded_dispatch_items(
            project_root=tmp_path,
            repo="repo",
            items=[_item(id_="bd-active")],
            live_lock_lookup=_no_live_lock,
        )
        == []
    )


def test_stranded_dispatch_items_fail_soft_when_journal_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_journal_lines(tmp_path, records=[_outcome()])

    def _raise(*args: object, **kwargs: object) -> str:
        _ = args
        _ = kwargs
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", _raise)

    assert (
        stranded_dispatch_items(
            project_root=tmp_path,
            repo="repo",
            items=[_item(id_="bd-active")],
            live_lock_lookup=_no_live_lock,
        )
        == []
    )


def test_stranded_dispatch_items_ignore_malformed_or_non_merged_outcomes(tmp_path: Path) -> None:
    _write_journal_lines(
        tmp_path,
        records=[
            "{",
            [],
            {"stage": "fabro-run"},
            {"stage": "outcome", "outcome": "not-a-dict"},
            _outcome(status="green"),
            _outcome(work_item_id=""),
            _outcome(stage=""),
            _outcome(pr_number=True),
            _outcome(pr_number="836"),
            _outcome(work_item_id="bd-other"),
        ],
    )

    attention = stranded_dispatch_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-active")],
        live_lock_lookup=_no_live_lock,
    )

    assert attention == []

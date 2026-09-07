"""The groom door's launch leg: a door-claimed row reaches the ordinary launch.

`_dispatcher_groom_door` opens the door — it pins the groom variant, moves the
item `backlog -> active`, and writes a dispatch lock. Nothing then LAUNCHED it:
the drain's selection predicate admitted only `ready` (plus a projected
`pending-approval`) rows, and the `--item` preflight read the door's OWN claim
as somebody else's in-flight dispatch and refused. The door was a dead end that
could only be undone by hand-clearing the claim.

WHY THE FIXTURES COME IN TWO SHAPES, and why both are needed. A door call made
in THIS process leaves a lock whose holder is alive, so `live_dispatch_lock`
answers it. The measured field case is the other one: the door ran in a
process that has since exited, so the identical claim reads STALE. Both are the
door's own claim and both must launch, so the cases below build each shape
deliberately — `_open_the_door` runs the real door here, and
`_claim_left_by_an_exited_door` writes the same claim under a pid that cannot
be running. A predicate keyed on liveness alone would pass one and fail the
other, and nothing in either fixture announces which one a reader is looking at.

WHAT IS DELIBERATELY STILL REFUSED. Two rows that also sit at `active`: one
carrying neither pin nor claim (the ordinary abandoned claim the preflight's
existing diagnostic is written for), and one whose claim is held by a DIFFERENT
live process (a groom dispatch already in flight). The widening is scoped to
the door's own claim, so both of those must stay refused, and asserting the
negatives here is what makes that a property rather than an intention.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import (
    candidates,
    is_dispatch_candidate,
    ready_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks import (
    requested_items_preflight_error,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    resolve_dispatch_workflow_name,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.types import WorkItemStatus

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door"

_ITEM_ID = "bd-ib-groom-launch"
_PEER_ID = "bd-ib-ready-peer"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
_IMPLEMENT_VARIANT = "codex-first"
_IMPLEMENT_DIR = ".fabro/workflows/codex-first"

# The dispatch id the 2026-09-07 door call actually wrote, kept verbatim so the
# fixture is the measured claim rather than a plausible-looking stand-in.
_DOOR_DISPATCH_ID = "964c81f7a4e345ab943c223f95336e89"

# A pid no process can hold: the exited door's claim, as a later dispatcher
# invocation finds it. `_dispatcher_engine`'s janitor-lock cases use the same
# sentinel.
_EXITED_DOOR_PID = 999999999


def _door_module() -> Any:
    return importlib.import_module(_MODULE_NAME)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _manifest(*, kind: str) -> str:
    return f'[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "{kind}"\n'


def _repo(*, tmp_path: Path) -> Path:
    """A target registering one groom variant, with the IMPLEMENT one as default.

    The default is deliberately the implement variant: it is what an unpinned
    dispatch of this item would resolve, so the pinned-variant assertion below
    can distinguish the pin from the default instead of agreeing with it.
    """
    repo = tmp_path / "repo"
    for directory, kind in ((_GROOM_DIR, "groom"), (_IMPLEMENT_DIR, "implement")):
        target = repo / directory
        target.mkdir(parents=True)
        _ = (target / "workflow.toml").write_text(_manifest(kind=kind), encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_workflow": _IMPLEMENT_VARIANT,
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _item(
    *,
    item_id: str = _ITEM_ID,
    status: WorkItemStatus = "backlog",
    rank: str = "m",
) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,
        title="An epic with more than one coherent done",
        description="It carries more than one coherent done.",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-09-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- The epic is decomposed.",
    )


def _journal(*, repo: Path) -> JournalFile:
    return JournalFile(path=repo / "journal.jsonl")


def _open_the_door(*, repo: Path) -> WorkItem:
    """Run the REAL door here, so its claim is one this live process holds."""
    reset_fake_singleton()
    filed = _item()
    append_work_item(path=_config(), item=filed)
    module = _door_module()
    opened = module.groom_dispatch(
        repo=repo,
        item=filed,
        variant=_GROOM_VARIANT,
        journal=_journal(repo=repo),
    )
    assert not isinstance(opened, module.GroomDoorRefusal)
    return replace(filed, status="active", assignee="fabro")


def _write_claim(*, repo: Path, pid: int, dispatch_id: str | None) -> None:
    path = dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        json.dumps(
            {
                "work_item_id": _ITEM_ID,
                "pid": pid,
                "started_at_epoch": 1.0,
                "dispatch_id": dispatch_id,
            }
        ),
        encoding="utf-8",
    )


def _claim_left_by_an_exited_door(
    *,
    repo: Path,
    variant: str = _GROOM_VARIANT,
    dispatch_id: str | None = _DOOR_DISPATCH_ID,
) -> WorkItem:
    """The measured field shape: the door's claim, its writing process gone."""
    reset_fake_singleton()
    claimed = _item(status="active")
    append_work_item(path=_config(), item=claimed)
    record_dispatch_workflow(path=_config(), work_item_id=_ITEM_ID, workflow=variant)
    _write_claim(repo=repo, pid=_EXITED_DOOR_PID, dispatch_id=dispatch_id)
    return claimed


def _an_ordinary_active_row(*, repo: Path) -> WorkItem:
    """`active`, with no groom pin and no claim of any kind. Nothing is written."""
    reset_fake_singleton()
    ordinary = _item(status="active")
    append_work_item(path=_config(), item=ordinary)
    assert not dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID).exists()
    return ordinary


def _is_candidate(*, repo: Path, item: WorkItem) -> bool:
    return is_dispatch_candidate(
        item=item,
        index={item.id: item},
        manifest=load_manifest(project_root=repo),
        repo=repo,
    )


def test_the_drain_selects_the_doors_claimed_groom_pinned_row(tmp_path: Path) -> None:
    """The whole gap, at the seam that decides it, with a ready peer as control.

    The peer proves the ordering authority is untouched: the claimed row sorts
    ahead of it on `(rank, id)` exactly as a ready row of the same rank would,
    so the widening adds a member to the candidate set rather than a special
    case beside it.
    """
    repo = _repo(tmp_path=tmp_path)
    claimed = _open_the_door(repo=repo)
    peer = _item(item_id=_PEER_ID, status="ready", rank="n")

    selected = ready_items(items=[claimed, peer], repo=repo)

    assert [item.id for item in selected] == [_ITEM_ID, _PEER_ID]


def test_a_live_claim_the_door_itself_holds_is_a_dispatch_candidate(tmp_path: Path) -> None:
    """The door's claim, read while the claiming process is still alive."""
    repo = _repo(tmp_path=tmp_path)
    claimed = _open_the_door(repo=repo)

    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is not None
    assert _is_candidate(repo=repo, item=claimed) is True


def test_a_claim_left_by_an_exited_door_is_still_a_dispatch_candidate(tmp_path: Path) -> None:
    """The field shape. A liveness-only predicate would refuse exactly this row."""
    repo = _repo(tmp_path=tmp_path)
    claimed = _claim_left_by_an_exited_door(repo=repo)

    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is None
    assert _is_candidate(repo=repo, item=claimed) is True


def test_the_requested_item_preflight_admits_the_doors_claim(tmp_path: Path) -> None:
    """The second seam: `--item <door-claimed>` no longer reads as claimed-by-another."""
    repo = _repo(tmp_path=tmp_path)
    claimed = _claim_left_by_an_exited_door(repo=repo)

    assert (
        requested_items_preflight_error(
            requested_ids={_ITEM_ID},
            items=[claimed],
            repo=repo,
            journal=_journal(repo=repo),
        )
        is None
    )


def test_an_ordinary_active_row_is_still_refused_by_the_same_preflight(tmp_path: Path) -> None:
    """The scoping negative: no pin, no claim, so the existing refusal still fires."""
    repo = _repo(tmp_path=tmp_path)
    ordinary = _an_ordinary_active_row(repo=repo)

    error = requested_items_preflight_error(
        requested_ids={_ITEM_ID},
        items=[ordinary],
        repo=repo,
        journal=_journal(repo=repo),
    )

    assert error is not None
    assert "already claimed by a dispatch" in error
    assert _is_candidate(repo=repo, item=ordinary) is False


def test_a_claim_held_by_another_live_process_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A groom dispatch already in flight elsewhere is not the door's own claim.

    The door's claim is recognised by being THIS process's or by its holder
    having exited; a live holder that is neither is somebody else's dispatch,
    and selecting it would launch the same row twice. Reported as a different
    pid rather than by spawning one, so the case is deterministic.
    """
    repo = _repo(tmp_path=tmp_path)
    claimed = _open_the_door(repo=repo)
    monkeypatch.setattr(os, "getpid", lambda: _EXITED_DOOR_PID)

    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is not None
    assert _is_candidate(repo=repo, item=claimed) is False


def test_a_claim_carrying_no_dispatch_id_is_not_the_doors_claim(tmp_path: Path) -> None:
    """The door stamps a dispatch id; a claim without one did not come from it."""
    repo = _repo(tmp_path=tmp_path)
    claimed = _claim_left_by_an_exited_door(repo=repo, dispatch_id=None)

    assert _is_candidate(repo=repo, item=claimed) is False


def test_a_claimed_row_pinned_to_an_implement_variant_is_refused(tmp_path: Path) -> None:
    """The pin is half the discriminator: a claim alone is an abandoned dispatch."""
    repo = _repo(tmp_path=tmp_path)
    claimed = _claim_left_by_an_exited_door(repo=repo, variant=_IMPLEMENT_VARIANT)

    assert _is_candidate(repo=repo, item=claimed) is False


def test_a_door_claimed_row_reaches_the_launch_leg(tmp_path: Path) -> None:
    """Selection and admission, driven for real, up to the list the loop launches.

    `admission.admitted` IS the launch leg's input: `_dispatch_loop_wave`
    submits exactly those items to `dispatch_one`. Asserting on it rather than
    on a stubbed Fabro call keeps the case about the two seams this change
    moves, while still failing if either one refuses the row.
    """
    repo = _repo(tmp_path=tmp_path)
    claimed = _claim_left_by_an_exited_door(repo=repo)
    journal = _journal(repo=repo)

    selected = candidates(args=argparse.Namespace(items=[_ITEM_ID]), items=[claimed], repo=repo)
    admission = admit_and_select(
        repo=repo,
        items=[claimed],
        candidates=selected,
        journal=journal,
        enforce_cap=True,
    )

    assert [item.id for item in selected] == [_ITEM_ID]
    assert [item.id for item in admission.admitted] == [_ITEM_ID]


def test_the_launched_row_resolves_the_pinned_groom_variant(tmp_path: Path) -> None:
    """Criterion four's discriminator: the target's default is the implement variant.

    `resolve_dispatch_workflow_name` is what `args_with_dispatch_workflow_name`
    calls on the way into `dispatch_one`, so this is the name the launched run
    actually carries — and it differs from `dispatcher.default_workflow`, which
    is what an unpinned row would have resolved.
    """
    repo = _repo(tmp_path=tmp_path)
    _ = _claim_left_by_an_exited_door(repo=repo)

    resolved = resolve_dispatch_workflow_name(
        args=argparse.Namespace(),
        repo=repo,
        work_item_id=_ITEM_ID,
    )

    assert resolved == _GROOM_VARIANT

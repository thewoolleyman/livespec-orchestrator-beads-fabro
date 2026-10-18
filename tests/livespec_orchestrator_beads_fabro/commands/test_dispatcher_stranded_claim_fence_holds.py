"""Every arm of the fence and the write-once pairing that CANNOT measure.

The happy fence and the converging replay are asserted in
`test_dispatcher_stranded_claim_convergence.py`. These are the arms that case
cannot reach, and they are the ones worth the most: each is a point where the
recovery is BLIND, and the dangerous reading at every one of them is the
negative answer rather than an error.

An unresolvable primary checkout, a lock another holder has, an unreadable
journal and an unreadable comment list all mean the same thing — this pass
cannot establish its effect — and all four must hold the claim at
`effect-unobservable` while writing NOTHING. The opposite coding of any one of
them releases a claim on evidence nobody took, or appends a duplicate ledger
comment that can never be deleted.

THE CONTENDED-LOCK CASE USES A REAL LIVE HOLDER, not a patched writer. The
whole point of the fence is that a second pass cannot proceed while the first
holds the lock, and a stubbed `write_dispatch_lock` proves only that the
recovery handles an exception. The fixture writes a lock payload naming THIS
process — alive by construction — so the real reclaim path reads it, finds the
holder live, and refuses, which is exactly the contention a sibling pass
creates.
"""

from __future__ import annotations

import importlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    RELEASE_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RECOVERY = f"{_PACKAGE}._dispatcher_stranded_claim_recovery"
_FENCE = f"{_PACKAGE}._dispatcher_stranded_claim_fence"
_REPLAY = f"{_PACKAGE}._dispatcher_stranded_claim_replay"
_EFFECTS = f"{_PACKAGE}._dispatcher_stranded_claim_effects"

_ITEM_ID = "bd-ib-fenced"
_RUN_ID = "01FENCEDRUN"
_NOW = "2026-10-18T09:00:00Z"
_HOLD = "effect-unobservable"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module(*, name: str) -> Any:
    return importlib.import_module(name)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A dispatched slice whose run vanished",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _seed() -> WorkItem:
    item = _item()
    append_work_item(path=_config(), item=item)
    record_claim_stamp(
        path=_config(),
        work_item_id=item.id,
        stamp=ClaimStamp(
            dispatch_id="01DISPATCH",
            dispatching_host="owning-host",
            run_id=_RUN_ID,
            factory_name="hp",
            factory_server="https://hp.example:32276",
        ),
    )
    return item


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _request(*, recovery: Any, item: WorkItem) -> Any:
    return recovery.ClaimRecoveryRequest(
        item=item,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        action="absent-run-release",
        predecessor_run_id="01PREVIOUSRUN",
    )


def _assert_nothing_written() -> None:
    """No status move, and no release comment.

    Both halves matter: a claim held on an unobservable reading must be left
    for the next pass EXACTLY as it was found, and the comment is the effect
    that cannot be withdrawn.
    """
    assert next(iter(read_work_items(path=_config()))).status == "active"
    assert [
        comment
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(RELEASE_COMMENT_MARKER)
    ] == []


def test_an_unresolvable_primary_checkout_holds_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No agreed lock location means no exclusion to take, so nothing is written."""
    repo = _repo(tmp_path=tmp_path)
    item = _seed()
    journal = _journal(repo=repo)
    recovery = _module(name=_RECOVERY)
    fence = _module(name=_FENCE)

    def _cannot_ask(*, repository: Path) -> Path:
        _ = repository
        raise OSError("git is not available to ask")

    monkeypatch.setattr(fence, "resolve_primary_repository", _cannot_ask)

    outcome = recovery.recover_claim(
        repo=repo, journal=journal, request=_request(recovery=recovery, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == _HOLD
    _assert_nothing_written()


def test_a_lock_a_live_holder_already_owns_holds_the_claim(tmp_path: Path) -> None:
    """The contention a sibling pass creates, produced by a genuinely live holder."""
    repo = _repo(tmp_path=tmp_path)
    item = _seed()
    journal = _journal(repo=repo)
    recovery = _module(name=_RECOVERY)
    # A lock naming THIS process: alive by construction, so the reclaim path
    # reads it, finds the holder live, and refuses to take it over.
    held = dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID)
    held.parent.mkdir(parents=True, exist_ok=True)
    _ = held.write_text(
        json.dumps(
            {
                "work_item_id": _ITEM_ID,
                "pid": os.getpid(),
                "started_at_epoch": time.time(),
                "dispatch_id": "a-sibling-pass",
            }
        ),
        encoding="utf-8",
    )

    outcome = recovery.recover_claim(
        repo=repo, journal=journal, request=_request(recovery=recovery, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == _HOLD
    _assert_nothing_written()
    # The holder's own lock survives: a refused recovery must not clear the
    # exclusion it failed to acquire.
    assert json.loads(held.read_text(encoding="utf-8"))["dispatch_id"] == "a-sibling-pass"


def test_an_unreadable_journal_holds_the_claim_before_any_write(tmp_path: Path) -> None:
    """The journal cannot be consulted, so the row it might already carry is unknown."""
    repo = _repo(tmp_path=tmp_path)
    item = _seed()
    # A DIRECTORY where the journal file belongs: it exists, and reading it
    # raises — which is "unavailable", not "empty".
    path = repo / "tmp" / "journal.jsonl"
    path.mkdir(parents=True)
    recovery = _module(name=_RECOVERY)

    outcome = recovery.recover_claim(
        repo=repo,
        journal=JournalFile(path=path),
        request=_request(recovery=recovery, item=item),
        now_iso=_NOW,
    )

    assert outcome.hold_reason == _HOLD
    _assert_nothing_written()


def test_an_unreadable_comment_list_holds_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A comment that cannot be read must never be treated as a comment that is absent.

    This is the costliest arm to get wrong: reading the failure as "no comment
    yet" appends a second one, and `bd comments` offers neither edit nor
    delete.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _seed()
    journal = _journal(repo=repo)
    recovery = _module(name=_RECOVERY)
    replay = _module(name=_REPLAY)

    def _refuse(*, path: StoreConfig, work_item_id: str) -> object:
        _ = (path, work_item_id)
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="refused")

    monkeypatch.setattr(replay, "read_work_item_comments", _refuse)

    outcome = recovery.recover_claim(
        repo=repo, journal=journal, request=_request(recovery=recovery, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == _HOLD
    _assert_nothing_written()


def test_a_refused_comment_append_holds_the_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write itself failing is the same answer as the read failing."""
    repo = _repo(tmp_path=tmp_path)
    item = _seed()
    journal = _journal(repo=repo)
    recovery = _module(name=_RECOVERY)
    effects = _module(name=_EFFECTS)

    def _refuse(*, path: StoreConfig, work_item_id: str, body: str) -> None:
        _ = (path, work_item_id, body)
        raise BeadsCommandError(command="bd comment", exit_code=1, stderr="refused")

    monkeypatch.setattr(effects, "append_work_item_comment", _refuse)

    outcome = recovery.recover_claim(
        repo=repo, journal=journal, request=_request(recovery=recovery, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == _HOLD
    # The status never moved; the journal row DID land, which is correct — it is
    # written first by the clause's order and is not the effect that cannot be
    # withdrawn.
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_the_replay_readers_report_unobservable_rather_than_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two readers, asserted directly: `None` and never `False`.

    Driven at the unit seam as well as through the recovery above, because
    `False` and `None` send the recovery down different paths and only one of
    them is safe — and a reader returning `False` here would still produce a
    perfectly plausible recovery.
    """
    repo = _repo(tmp_path=tmp_path)
    _ = _seed()
    replay = _module(name=_REPLAY)
    missing = tmp_path / "nowhere"
    missing.mkdir()

    def _refuse(*, path: StoreConfig, work_item_id: str) -> object:
        _ = (path, work_item_id)
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="refused")

    monkeypatch.setattr(replay, "read_work_item_comments", _refuse)

    assert (
        replay.journal_record_already_written(
            journal_path=missing,
            stage="stranded-claim-release",
            work_item_id=_ITEM_ID,
            run_id=_RUN_ID,
        )
        is None
    )
    assert replay.comment_already_written(repo=repo, work_item_id=_ITEM_ID, body="anything") is None


def test_a_readable_but_empty_journal_reports_absent_rather_than_unobservable(
    tmp_path: Path,
) -> None:
    """The positive control for the reader above.

    Without it, a reader hard-wired to `None` would satisfy every assertion in
    this module while holding every claim on every fresh checkout forever.
    """
    repo = _repo(tmp_path=tmp_path)
    _ = _seed()
    replay = _module(name=_REPLAY)

    assert (
        replay.journal_record_already_written(
            journal_path=repo / "tmp" / "never-written.jsonl",
            stage="stranded-claim-release",
            work_item_id=_ITEM_ID,
            run_id=_RUN_ID,
        )
        is False
    )
    assert replay.comment_already_written(repo=repo, work_item_id=_ITEM_ID, body="absent") is False


def test_a_journal_row_for_another_run_is_not_this_recovery_s_row(tmp_path: Path) -> None:
    """The reader is keyed on the RUN, not just the stage and the item.

    An item legitimately carries a release row for an earlier run; reading
    that as this run's row would skip the record this recovery owes.
    """
    repo = _repo(tmp_path=tmp_path)
    _ = _seed()
    journal = _journal(repo=repo)
    journal.append(
        record={
            "stage": "stranded-claim-release",
            "work_item_id": _ITEM_ID,
            "run_id": "01ANEARLIERRUN",
        }
    )
    replay = _module(name=_REPLAY)

    assert (
        replay.journal_record_already_written(
            journal_path=journal.path,
            stage="stranded-claim-release",
            work_item_id=_ITEM_ID,
            run_id=_RUN_ID,
        )
        is False
    )

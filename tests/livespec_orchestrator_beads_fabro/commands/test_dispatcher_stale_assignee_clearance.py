"""Scenario 210: reconciliation clears a stale fabro assignee from a ready item.

A *stale assignee* is a work-item resting at `ready` whose assignee is still
`fabro`. Its claim ended when it left `active`, so no terminal disposition is
owed; the claim survey clears the assignee when the run stamp names this host
and the factory reports the run terminal or absent with no live owner, and holds
with the first failing reason otherwise. Driven end to end through
`survey_stranded_claims` against a hermetic tenant and a faked factory listing.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import CLAIM_STAMP_METADATA_KEY
from livespec_orchestrator_beads_fabro._store_rework_mutations import LABEL_REWORK_PENDING
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_observe as observe_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_replay as replay_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_survey as survey_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    LOCK_LIVE,
    LOCK_UNREADABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-staleassg"
_RUN_ID = "01M4FWX1Z9J7HPQRSTVWXYZ012"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "test-dispatching-host"
_CLEAR_STAGE = "stale-assignee-clear"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A ready item still assigned fabro",
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
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _stamp(**overrides: object) -> dict[str, Any] | None:
    stamp: dict[str, Any] = {
        "dispatch_id": "01DISPATCHONE",
        "dispatching_host": _HOST,
        "run_id": _RUN_ID,
        "factory": {"name": _FACTORY, "server": _SERVER},
    }
    stamp.update(overrides)
    return {key: value for key, value in stamp.items() if value is not None}


def _seed(*, item: WorkItem, stamp: dict[str, Any] | None) -> None:
    append_work_item(path=_config(), item=item)
    if stamp is None:
        return
    client = make_beads_client(config=_config())
    raw = client.show_issue(issue_id=item.id).get("metadata")
    metadata = dict(raw) if isinstance(raw, dict) else {}
    metadata[CLAIM_STAMP_METADATA_KEY] = stamp
    client.update_issue(issue_id=item.id, metadata=metadata)


def _journal(*, repo: Path, extra: tuple[dict[str, object], ...] = ()) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = (
        {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": "01DISPATCHONE"},
        {"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN_ID},
        *extra,
    )
    _ = path.write_text("".join(f"{json.dumps(row)}\n" for row in rows), encoding="utf-8")
    return JournalFile(path=path)


def _rows(*, journal: JournalFile, stage: str) -> list[dict[str, Any]]:
    parsed = [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]
    return [row for row in parsed if row.get("stage") == stage]


def _survey(
    *,
    repo: Path,
    journal: JournalFile,
    kinds: dict[str, str | None] | None,
    dry_run: bool = False,
) -> Any:
    items = tuple(read_work_items(path=_config()))
    runner = MagicMock()
    result = survey_module.survey_stranded_claims(
        inputs=survey_module.StrandedClaimInputs(
            repo=repo,
            items=items,
            journal=journal,
            runner=runner,
            inventories=(
                survey_module.FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=kinds is not None,
                    status_kinds={} if kinds is None else kinds,
                ),
            ),
            this_host=_HOST,
            now_iso="2026-11-08T23:00:00Z",
            dry_run=dry_run,
        )
    )
    # A stale assignee is not a dispatch claim: no forge or factory command is run for it.
    runner.run.assert_not_called()
    return result


def _only_item() -> WorkItem:
    return next(iter(read_work_items(path=_config())))


def _raw_record() -> dict[str, Any]:
    return dict(make_beads_client(config=_config()).show_issue(issue_id=_ITEM_ID))


@pytest.mark.parametrize(
    ("kinds", "state"),
    [
        ({_RUN_ID: "failed"}, "failed"),
        ({}, "absent"),
        ({_RUN_ID: "succeeded"}, "succeeded"),
    ],
)
def test_a_stale_assignee_with_a_terminal_or_absent_run_is_cleared(
    tmp_path: Path, kinds: dict[str, str | None], state: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    before = _raw_record()

    survey = _survey(repo=repo, journal=journal, kinds=kinds)

    cleared = _only_item()
    after = _raw_record()
    assert (cleared.status, cleared.assignee) == ("ready", None)
    assert after.get("labels") == before.get("labels")
    assert (
        after["metadata"][CLAIM_STAMP_METADATA_KEY] == before["metadata"][CLAIM_STAMP_METADATA_KEY]
    )
    assert survey.held == ()
    assert [(one.work_item_id, one.run_id, one.reason) for one in survey.recovered] == [
        (_ITEM_ID, _RUN_ID, state)
    ]
    records = _rows(journal=journal, stage=_CLEAR_STAGE)
    assert [
        (row["work_item_id"], row["run_id"], row["factory"], row["run_state"]) for row in records
    ] == [(_ITEM_ID, _RUN_ID, _FACTORY, state)]
    comments = [
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
    ]
    assert len(comments) == 1
    assert all(name in comments[0] for name in (_ITEM_ID, _RUN_ID, _FACTORY, state))
    for other in (
        "provider-limit-release",
        "stranded-claim-release",
        "stranded-claim-terminal-completion",
    ):
        assert _rows(journal=journal, stage=other) == []
    assert after.get("status") == before.get("status")


@pytest.mark.parametrize(
    ("stamp", "kinds", "reason"),
    [
        (None, {}, "claim-unattributable"),
        (_stamp(run_id=None), {}, "attribution-pending"),
        (_stamp(dispatching_host="another-host"), {}, "owner-elsewhere"),
        (_stamp(), None, "factory-unobservable"),
        (_stamp(), {_RUN_ID: "running"}, "run-live"),
        (_stamp(), {_RUN_ID: "blocked"}, "run-live"),
    ],
)
def test_a_stale_assignee_that_cannot_be_cleared_is_held_unchanged(
    tmp_path: Path,
    stamp: dict[str, Any] | None,
    kinds: dict[str, str | None] | None,
    reason: str,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=stamp)
    journal = _journal(repo=repo)
    before = _raw_record()

    survey = _survey(repo=repo, journal=journal, kinds=kinds)

    held = _only_item()
    assert (held.status, held.assignee) == ("ready", "fabro")
    assert _raw_record() == before
    assert survey.recovered == ()
    assert [(one.work_item_id, one.hold_reason) for one in survey.held] == [(_ITEM_ID, reason)]
    assert _rows(journal=journal, stage=_CLEAR_STAGE) == []
    assert not read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)


@pytest.mark.parametrize(
    ("observed", "reason"),
    [(LOCK_UNREADABLE, "liveness-unobservable"), (LOCK_LIVE, "dispatch-live")],
)
def test_a_stale_assignee_with_an_unreadable_or_live_owner_lock_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observed: str, reason: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    monkeypatch.setattr(observe_module, "observe_dispatch_lock", lambda **_: observed)

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    assert _only_item().assignee == "fabro"
    assert [one.hold_reason for one in survey.held] == [reason]
    assert _rows(journal=journal, stage=_CLEAR_STAGE) == []


def test_a_stale_assignee_whose_journal_cannot_be_read_is_held_effect_unobservable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    monkeypatch.setattr(replay_module, "journal_records_or_none", lambda **_: None)

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    assert _only_item().assignee == "fabro"
    assert [one.hold_reason for one in survey.held] == ["effect-unobservable"]
    assert not read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)


def test_a_marked_stale_assignee_is_not_surveyed(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    make_beads_client(config=_config()).update_issue(
        issue_id=_ITEM_ID, add_labels=[LABEL_REWORK_PENDING]
    )
    journal = _journal(repo=repo)

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    assert (survey.recovered, survey.held) == ((), ())
    assert _only_item().assignee == "fabro"


def test_an_interrupted_clearance_writes_only_the_missing_effects(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    already = {
        "stage": _CLEAR_STAGE,
        "work_item_id": _ITEM_ID,
        "run_id": _RUN_ID,
        "factory": _FACTORY,
        "run_state": "failed",
    }
    journal = _journal(repo=repo, extra=(already,))

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    assert _only_item().assignee is None
    assert len(_rows(journal=journal, stage=_CLEAR_STAGE)) == 1
    assert len(read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)) == 1
    assert [one.effects_written for one in survey.recovered] == [
        ("ledger-comment", "assignee-clear")
    ]


def test_a_second_pass_over_a_cleared_stale_assignee_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    _ = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})
    first_journal = journal.path.read_text(encoding="utf-8")

    second = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    assert (second.recovered, second.held) == ((), ())
    assert journal.path.read_text(encoding="utf-8") == first_journal
    assert len(read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)) == 1


def test_a_human_move_before_the_assignee_write_is_respected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    clear_module = _clear_module()
    real_establish = clear_module.establish_comment

    def _comment_then_human_move(**kwargs: Any) -> str | None:
        outcome = real_establish(**kwargs)
        make_beads_client(config=_config()).update_issue(issue_id=_ITEM_ID, status="backlog")
        return outcome

    monkeypatch.setattr(clear_module, "establish_comment", _comment_then_human_move)

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    moved = _only_item()
    assert (moved.status, moved.assignee) == ("backlog", "fabro")
    assert survey.recovered == ()
    assert [one.hold_reason for one in survey.held] == ["claim-changed"]


def test_a_dry_run_projects_the_clearance_and_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    before = _raw_record()

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "succeeded"}, dry_run=True)

    assert _raw_record() == before
    assert _rows(journal=journal, stage=_CLEAR_STAGE) == []
    assert [(one.route, one.reason, one.effects_written) for one in survey.recovered] == [
        ("stale-assignee-clear", "succeeded", ())
    ]


def _clear_module() -> Any:
    import importlib

    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_stale_assignee_clear"
    )


@pytest.mark.parametrize(
    ("refusal", "reason"),
    [("claim-lease-expired", "effect-unobservable"), ("claim-changed", "claim-changed")],
)
def test_a_refused_assignee_write_is_held_under_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: str, reason: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _seed(item=_item(), stamp=_stamp())
    journal = _journal(repo=repo)
    monkeypatch.setattr(_clear_module(), "write_assignee_clear", lambda **_: refusal)

    survey = _survey(repo=repo, journal=journal, kinds={_RUN_ID: "failed"})

    assert _only_item().assignee == "fabro"
    assert [one.hold_reason for one in survey.held] == [reason]

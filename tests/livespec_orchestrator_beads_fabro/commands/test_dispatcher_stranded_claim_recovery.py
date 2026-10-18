"""One claim recovery: the ordered effects, and every re-read that stops it.

The happy release is asserted end to end one module over, in
`test_dispatcher_stranded_claim_release.py`. These are the arms that case
cannot reach without breaking the thing it measures: a row that changed under
the recovery, a row that could not be read at all, a comment write that
failed, and a transition that failed.

THE ORDER ASSERTION IS THE LOAD-BEARING ONE. The journal record and the ledger
comment must both exist BEFORE the status transition, because an operator who
finds a `ready` item has to be able to find the account that released it. A
recovery that transitioned first and then wrote its records would satisfy
every end-state assertion while leaving "released with no account" reachable,
so the final-re-read case checks the records landed AND the status did not.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    ClaimStamp,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    RELEASE_COMMENT_MARKER,
    STRANDED_CLAIM_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_PATH = (
    Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
    / "_dispatcher_stranded_claim_recovery.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery"
# The four ledger acts live one module over; a recovery arm that fails because
# one of them failed is injected THERE, which is where the `attempt` ladder is.
_EFFECTS_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects"

_ITEM_ID = "bd-ib-recover"
_RUN_ID = "01RECOVERRUN"
_NOW = "2026-10-18T09:00:00Z"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module() -> object:
    return importlib.import_module(_MODULE_NAME)


def _effects() -> object:
    return importlib.import_module(_EFFECTS_NAME)


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
    return replace(base, **overrides)


def _stamp(*, run_id: str | None = _RUN_ID) -> ClaimStamp:
    return ClaimStamp(
        dispatch_id="01DISPATCH",
        dispatching_host="owning-host",
        run_id=run_id,
        factory_name="hp",
        factory_server="https://hp.example:32276",
    )


def _seed(*, item: WorkItem, run_id: str | None = _RUN_ID) -> None:
    append_work_item(path=_config(), item=item)
    record_claim_stamp(path=_config(), work_item_id=item.id, stamp=_stamp(run_id=run_id))


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _request(*, module: object, item: WorkItem, action: str = "absent-run-release") -> object:
    return module.ClaimRecoveryRequest(
        item=item,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        action=action,
        predecessor_run_id="01PREVIOUSRUN",
    )


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def test_the_three_effects_land_and_the_route_reports_each_of_them(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.effects_written == (
        module.EFFECT_JOURNAL_RECORD,
        module.EFFECT_COMMENT,
        module.EFFECT_TRANSITION,
    )
    assert _stages(journal=journal) == [STRANDED_CLAIM_RELEASE_STAGE]
    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "blocked"},
        {"assignee": None},
    ],
)
def test_a_row_that_no_longer_carries_the_claim_is_held_unchanged(
    *, tmp_path: Path, overrides: dict[str, object]
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item(**overrides)
    _seed(item=item)
    journal = _journal(repo=repo)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=_item()), now_iso=_NOW
    )

    assert outcome.hold_reason == "claim-changed"
    # NOTHING was written: not the record, not the comment, not the status.
    assert _stages(journal=journal) == []
    assert next(iter(read_work_items(path=_config()))).status == overrides.get("status", "active")


@pytest.mark.parametrize("stamped", [None, "01ADIFFERENTRUN"])
def test_a_row_stamped_with_another_run_is_held_unchanged(
    *, tmp_path: Path, stamped: str | None
) -> None:
    """A pending stamp and a re-stamped one are both `claim-changed`."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item, run_id=stamped)
    journal = _journal(repo=repo)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "claim-changed"
    assert _stages(journal=journal) == []


def test_a_row_carrying_no_stamp_at_all_is_held_unchanged(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    append_work_item(path=_config(), item=item)
    journal = _journal(repo=repo)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "claim-changed"


def test_a_row_that_cannot_be_read_is_held_as_effect_unobservable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    def _refuse(*, path: StoreConfig, work_item_id: str) -> object:
        _ = (path, work_item_id)
        raise BeadsCommandError(command="bd show", exit_code=1, stderr="refused")

    monkeypatch.setattr(_effects(), "claim_row_for", _refuse)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "effect-unobservable"
    assert _stages(journal=journal) == []


def test_a_comment_write_that_fails_withholds_the_transition(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    def _refuse(*, path: StoreConfig, work_item_id: str, body: str) -> None:
        _ = (path, work_item_id, body)
        raise BeadsCommandError(command="bd comment", exit_code=1, stderr="refused")

    monkeypatch.setattr(_effects(), "append_work_item_comment", _refuse)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "effect-unobservable"
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_transition_that_fails_leaves_the_records_standing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    def _refuse(
        *,
        path: StoreConfig,
        item_id: str,
        status: str,
        clear_assignee: bool = False,
    ) -> None:
        _ = (path, item_id, status, clear_assignee)
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="refused")

    monkeypatch.setattr(_effects(), "update_work_item_status", _refuse)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "effect-unobservable"
    # Both durable records exist, which is the ORDER the clause requires: the
    # audit trail precedes the transition, so a failed transition leaves an
    # account rather than a silently untouched row.
    assert _stages(journal=journal) == [STRANDED_CLAIM_RELEASE_STAGE]
    bodies = [
        str(entry.get("text", ""))
        for entry in make_beads_client(config=_config()).list_comments(issue_id=_ITEM_ID)
    ]
    assert any(body.startswith(RELEASE_COMMENT_MARKER) for body in bodies)
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_final_re_read_that_cannot_be_taken_withholds_the_transition(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable re-read is a failure to MEASURE, so nothing is written.

    It must not read as `claim-changed`: that asserts a positive finding about
    the row, which an unreadable row cannot support.
    """
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    real = _effects().claim_row_for
    reads: list[int] = []

    def _refuse_the_second_read(*, path: StoreConfig, work_item_id: str) -> object:
        reads.append(1)
        if len(reads) == 2:
            raise BeadsCommandError(command="bd show", exit_code=1, stderr="refused")
        return real(path=path, work_item_id=work_item_id)

    monkeypatch.setattr(_effects(), "claim_row_for", _refuse_the_second_read)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "effect-unobservable"
    assert next(iter(read_work_items(path=_config()))).status == "active"


def test_a_row_re_stamped_between_the_comment_and_the_transition_is_not_overwritten(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one case the clause's final re-read exists for."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    real = _effects().claim_row_for
    reads: list[int] = []

    def _restamp_after_first_read(*, path: StoreConfig, work_item_id: str) -> object:
        reads.append(1)
        if len(reads) == 2:
            record_claim_stamp(
                path=_config(), work_item_id=work_item_id, stamp=_stamp(run_id="01ANEWRUN")
            )
        return real(path=path, work_item_id=work_item_id)

    monkeypatch.setattr(_effects(), "claim_row_for", _restamp_after_first_read)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert outcome.hold_reason == "claim-changed"
    assert next(iter(read_work_items(path=_config()))).status == "active"
    # The records were already written when the re-read refused: that is the
    # cost of ordering the audit trail first, and it is the cheaper direction.
    assert _stages(journal=journal) == [STRANDED_CLAIM_RELEASE_STAGE]


def test_the_repeat_route_rests_the_item_and_names_both_runs(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    outcome = module.recover_claim(
        repo=repo,
        journal=journal,
        request=_request(module=module, item=item, action="absent-run-repeated"),
        now_iso=_NOW,
    )

    assert outcome.status == "blocked"
    assert outcome.reason == "run-absent-repeated"
    assert _stages(journal=journal) == ["stranded-claim-run-absent-repeated"]
    rested = next(iter(read_work_items(path=_config())))
    assert (rested.status, rested.blocked_reason) == ("blocked", "needs-human")
    bodies = [
        str(entry.get("text", ""))
        for entry in make_beads_client(config=_config()).list_comments(issue_id=_ITEM_ID)
    ]
    assert any("01PREVIOUSRUN" in body and _RUN_ID in body for body in bodies)


def test_a_repeat_rest_that_fails_leaves_the_records_standing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)

    def _refuse(
        *,
        path: StoreConfig,
        item_id: str,
        status: str,
        blocked_reason: str | None,
        admission_policy: str | None = None,
    ) -> None:
        _ = (path, item_id, status, blocked_reason, admission_policy)
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="refused")

    monkeypatch.setattr(_effects(), "update_work_item_blocked_state", _refuse)

    outcome = module.recover_claim(
        repo=repo,
        journal=journal,
        request=_request(module=module, item=item, action="absent-run-repeated"),
        now_iso=_NOW,
    )

    assert outcome.hold_reason == "effect-unobservable"
    assert _stages(journal=journal) == ["stranded-claim-run-absent-repeated"]
    assert next(iter(read_work_items(path=_config()))).status == "active"

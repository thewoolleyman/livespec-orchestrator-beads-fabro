"""The recovery's EXCLUSION and its CONVERGENCE: one lock, and no effect twice.

`test_dispatcher_stranded_claim_recovery.py` covers the ordered effects and
every re-read that stops them. These are the two properties that only show up
when a recovery runs BESIDE something else, or AGAIN:

THE LOCK IS TAKEN AT THE PRIMARY CHECKOUT, not at the invoking one. A
reconciliation pass runs from whichever checkout happened to invoke it — a
worktree, a janitor checkout, a fresh clone — and those never share a
filesystem root, so a lock taken under `--repo` excludes only this checkout's
own callers while a second pass in a sibling checkout recovers the same claim
concurrently. The fixture therefore sets `livespec.primaryPath` to a DIFFERENT
directory and asserts the lock appears THERE and never under the invoking
repo: a build locking the invoking checkout passes every end-state assertion
and provides no exclusion at all.

A REPLAY WRITES NO EFFECT TWICE, and the interrupted case is the one worth
testing, because the fully-completed one is already stopped by the claim
re-read — the row is no longer `active`, so it holds as `claim-changed`. An
INTERRUPTED recovery leaves the row still claimed with its journal record and
its ledger comment already written, which is exactly the state a replay must
converge on rather than duplicate. A ledger comment can be neither edited nor
deleted, so a duplicated one is permanent.

THE EFFECT LIST IS READ AS "WHAT THIS PASS WROTE". A convergent second pass
reports the same route with only the effects it actually performed, which is
what makes a replay distinguishable from a first recovery — and the assertion
that fails loudest if a build re-writes an effect it should have skipped.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from dataclasses import replace
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
    STRANDED_CLAIM_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery"
_EFFECTS_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_effects"

_ITEM_ID = "bd-ib-converge"
_RUN_ID = "01CONVERGERUN"
_NOW = "2026-10-18T09:00:00Z"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module() -> Any:
    return importlib.import_module(_MODULE_NAME)


def _effects() -> Any:
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


def _livespec_config(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _livespec_config(repo=repo)
    return repo


def _repo_with_primary_elsewhere(*, tmp_path: Path) -> tuple[Path, Path]:
    """An invoking checkout whose `livespec.primaryPath` names a DIFFERENT root.

    Returned as a pair so each assertion can name the root it means. Without
    the two being distinct, "the lock is taken at the primary checkout" and
    "the lock is taken at the invoking checkout" are the same observation.
    """
    primary = tmp_path / "primary"
    primary.mkdir()
    _livespec_config(repo=primary)
    repo = _repo(tmp_path=tmp_path)
    _ = subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _ = subprocess.run(
        ["git", "-C", str(repo), "config", "livespec.primaryPath", str(primary)], check=True
    )
    return repo, primary


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


def _seed(*, item: WorkItem) -> None:
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


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _request(*, module: Any, item: WorkItem) -> Any:
    return module.ClaimRecoveryRequest(
        item=item,
        run_id=_RUN_ID,
        factory_name="hp",
        factory_server_url="https://hp.example:32276",
        action="absent-run-release",
        predecessor_run_id="01PREVIOUSRUN",
    )


def _release_rows(*, journal: JournalFile) -> list[dict[str, Any]]:
    return [
        record
        for record in (
            json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()
        )
        if record.get("stage") == STRANDED_CLAIM_RELEASE_STAGE
    ]


def _release_comments() -> list[str]:
    """Every release comment on the item. Indexed by `text`, never `body`.

    `bd comments` keys the body under `text`; reaching for `body` yields an
    empty string per comment, which is the identical observation to the
    duplication these cases are counting.
    """
    return [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(RELEASE_COMMENT_MARKER)
    ]


def test_the_recovery_holds_the_lock_at_the_primary_checkout_while_it_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exclusion is taken at the PRIMARY checkout, held across the writes, released after."""
    repo, primary = _repo_with_primary_elsewhere(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    module = _module()
    effects = _effects()
    real_append = effects.append_work_item_comment
    observed: list[tuple[bool, bool]] = []

    def _observe_then_append(*, path: StoreConfig, work_item_id: str, body: str) -> None:
        # Read DURING the recovery, at the ledger seam the comment write goes
        # through: the lock must already be held by the time the first durable
        # effect lands, not merely taken somewhere.
        observed.append(
            (
                dispatch_lock_path(repo=primary, work_item_id=_ITEM_ID).exists(),
                dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID).exists(),
            )
        )
        real_append(path=path, work_item_id=work_item_id, body=body)

    monkeypatch.setattr(effects, "append_work_item_comment", _observe_then_append)

    outcome = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    # Held at the primary checkout, and NEVER at the invoking one.
    assert observed == [(True, False)]
    assert outcome.effects_written == (
        module.EFFECT_JOURNAL_RECORD,
        module.EFFECT_COMMENT,
        module.EFFECT_TRANSITION,
    )
    # Released once the recovery is done: a lock left behind would make the
    # item look permanently owned to every later pass.
    assert dispatch_lock_path(repo=primary, work_item_id=_ITEM_ID).exists() is False


def test_an_interrupted_recovery_replays_without_writing_any_effect_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The replay finishes the transition and re-writes neither durable record."""
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    module = _module()
    effects = _effects()
    # Captured so the replay can restore THIS attribute alone. `monkeypatch.undo()`
    # would also revert the autouse fixture's `LIVESPEC_BEADS_FAKE`, selecting the
    # shell backend mid-test — a failure that reads like a credential fault.
    real_update = effects.update_work_item_status

    def _refuse_the_transition(
        *,
        path: StoreConfig,
        item_id: str,
        status: str,
        clear_assignee: bool = False,
    ) -> None:
        _ = (path, item_id, status, clear_assignee)
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="refused")

    monkeypatch.setattr(effects, "update_work_item_status", _refuse_the_transition)

    interrupted = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    # The interruption lands exactly where a killed recovery does: both durable
    # records written, the status not yet moved.
    assert interrupted.hold_reason == "effect-unobservable"
    assert len(_release_rows(journal=journal)) == 1
    assert len(_release_comments()) == 1
    assert next(iter(read_work_items(path=_config()))).status == "active"

    monkeypatch.setattr(effects, "update_work_item_status", real_update)
    replayed = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    # Converged: the transition is applied, and NEITHER durable record is
    # duplicated. A ledger comment cannot be deleted, so a second one is
    # permanent.
    assert len(_release_rows(journal=journal)) == 1
    assert len(_release_comments()) == 1
    released = next(iter(read_work_items(path=_config())))
    assert (released.status, released.assignee) == ("ready", None)
    # Only the effect this pass actually performed is reported.
    assert replayed.effects_written == (module.EFFECT_TRANSITION,)


def test_a_repeated_recovery_of_an_already_released_claim_writes_nothing_further(
    tmp_path: Path,
) -> None:
    """The REPEATED half: a second full pass over a released row adds no effect.

    Stopped one rung earlier than the interrupted case — the row is `ready`
    with no assignee, so it no longer carries the claim at all — which is why
    this reports `claim-changed` rather than converging. Asserted here beside
    the interrupted case because the clause names both, and because the two
    outcomes are only meaningful against each other.
    """
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    _seed(item=item)
    journal = _journal(repo=repo)
    module = _module()

    first = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )
    repeated = module.recover_claim(
        repo=repo, journal=journal, request=_request(module=module, item=item), now_iso=_NOW
    )

    assert first.effects_written == (
        module.EFFECT_JOURNAL_RECORD,
        module.EFFECT_COMMENT,
        module.EFFECT_TRANSITION,
    )
    assert repeated.hold_reason == "claim-changed"
    assert len(_release_rows(journal=journal)) == 1
    assert len(_release_comments()) == 1

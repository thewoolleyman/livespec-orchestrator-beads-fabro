"""Stranded-claim recovery after the claim-token cutover.

`SPECIFICATION/contracts.md` ("Claim tokens") keeps three older rules in force
beside the token: "the owning-host rule, the canonical recovery lock and the
stamp re-read ... remain, because they decide WHETHER a recovery may act, while
the token decides WHICH of several concurrent writers acts."

So with `dispatcher.claim_tokens` true there are two things to show, and they
are different:

- Each of the three older rules still stops a recovery on its own. In every one
  of those cases the item's current token is still OPEN afterwards: the
  recovery was refused before it ever contested the token, so the hold names
  the rule that stopped it and not `claim-changed` from a lost race.
- When all three permit, the recovery contests the token. The one that wins
  writes the transition and names the successor; the one that loses writes
  nothing to the item and is held as `claim-changed`. Any other way the guarded
  write fails to land is `effect-unobservable`.
"""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_stranded_claim_effects as effects,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery import (
    ClaimRecoveryRequest,
    recover_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-strandtok"
_RUN_ID = "01STRANDEDTOKENRUN"
_DISPATCH_ID = "01DISPATCHONE"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "owning-host"
_NOW = "2026-11-06T09:00:00Z"
_ANOTHER_WRITER = "another writer won this token"


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
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
    """A repository whose committed configuration has cut over to claim tokens."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}, '
        '"dispatcher": {"claim_tokens": true}}}',
        encoding="utf-8",
    )
    return repo


def _journal(*, repo: Path) -> JournalFile:
    """A journal carrying this item's ONE launch: a confirmed first dispatch."""
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        "".join(
            f"{json.dumps(record)}\n"
            for record in (
                {"stage": "dispatch-id", "work_item_id": _ITEM_ID, "dispatch_id": _DISPATCH_ID},
                {"stage": "dispatch-run-stamp", "work_item_id": _ITEM_ID, "run_id": _RUN_ID},
            )
        ),
        encoding="utf-8",
    )
    return JournalFile(path=path)


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
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _stamp(*, run_id: str = _RUN_ID) -> ClaimStamp:
    return ClaimStamp(
        dispatch_id=_DISPATCH_ID,
        dispatching_host=_HOST,
        run_id=run_id,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )


def _seed(*, name_a_token: bool = True) -> tuple[WorkItem, FakeBeadsClient, str]:
    """The stranded claim: `active`, assigned `fabro`, stamped, naming an open token."""
    item = _item()
    append_work_item(path=_config(), item=item)
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_stamp())
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    if name_a_token:
        metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
        metadata[CLAIM_TOKEN_METADATA_KEY] = token
        client.update_issue(issue_id=_ITEM_ID, metadata=metadata)
    return item, client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _is_open(*, client: FakeBeadsClient, token: str) -> bool:
    return client.show_issue(issue_id=token)["status"] != "closed"


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _request(*, item: WorkItem, action: str = "absent-run-release") -> ClaimRecoveryRequest:
    return ClaimRecoveryRequest(
        item=item,
        run_id=_RUN_ID,
        factory_name=_FACTORY,
        factory_server_url=_SERVER,
        action=action,
        predecessor_run_id="01PREVIOUSRUN",
    )


def _recover(*, repo: Path, item: WorkItem, action: str = "absent-run-release") -> object:
    return recover_claim(
        repo=repo,
        journal=_journal(repo=repo),
        request=_request(item=item, action=action),
        now_iso=_NOW,
    )


class _Forge:
    """A forge that reports no pull request for the item."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def _survey(*, repo: Path, item: WorkItem, this_host: str) -> object:
    """One reconciliation pass over the claim, on `this_host`, with its run absent."""
    return survey_stranded_claims(
        inputs=StrandedClaimInputs(
            repo=repo,
            items=(item,),
            journal=_journal(repo=repo),
            runner=_Forge(),
            inventories=(
                FactoryInventory(
                    name=_FACTORY,
                    server_url=_SERVER,
                    fabro_bin="fabro",
                    surveyed=True,
                    status_kinds={},
                ),
            ),
            this_host=this_host,
            now_iso=_NOW,
        )
    )


def test_the_owning_host_recovers_and_wins_the_token_when_every_rule_permits(
    tmp_path: Path,
) -> None:
    """DoD 4's positive half: the recovery still acts, and acts through the token."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()

    survey = _survey(repo=repo, item=item, this_host=_HOST)

    record = client.show_issue(issue_id=_ITEM_ID)
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert [held.hold_reason for held in survey.held] == []
    assert len(survey.recovered) == 1
    assert (record["status"], record["assignee"]) == ("ready", None)
    assert (won["writer"], won["intent"]) == ("stranded-claim-recovery", "absent-run-release")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]


def test_a_claim_owned_by_another_host_is_held_and_its_token_is_never_contested(
    tmp_path: Path,
) -> None:
    """The owning-host rule decides first: a foreign claim is not this host's to win."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    before = _snapshot(client=client)

    survey = _survey(repo=repo, item=item, this_host="some-other-host")

    assert [held.hold_reason for held in survey.held] == ["owner-elsewhere"]
    assert survey.recovered == ()
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)


def test_a_recovery_lock_another_holder_owns_stops_the_recovery_before_the_token(
    tmp_path: Path,
) -> None:
    """The canonical recovery lock decides next, with a genuinely live holder."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    before = _snapshot(client=client)
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

    outcome = _recover(repo=repo, item=item)

    assert getattr(outcome, "hold_reason", None) == "effect-unobservable"
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)


def test_a_claim_re_stamped_before_the_recovery_is_claim_changed_with_the_token_open(
    tmp_path: Path,
) -> None:
    """The stamp re-read under the lock decides third: another run now owns the item."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_stamp(run_id="01ANEWRUN"))
    before = _snapshot(client=client)

    outcome = _recover(repo=repo, item=item)

    assert getattr(outcome, "hold_reason", None) == "claim-changed"
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)


def test_a_claim_re_stamped_just_before_the_transition_is_not_contested_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The LAST re-read, after the record and the comment, still precedes the token."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    real = effects.claim_row_for
    reads: list[str] = []

    def _restamp_before_the_second_read(*, path: StoreConfig, work_item_id: str) -> object:
        reads.append(work_item_id)
        # The final re-read is the second one.
        if len(reads) == 2:
            record_claim_stamp(path=path, work_item_id=work_item_id, stamp=_stamp(run_id="01ANEW"))
        return real(path=path, work_item_id=work_item_id)

    monkeypatch.setattr(effects, "claim_row_for", _restamp_before_the_second_read)

    outcome = _recover(repo=repo, item=item)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert getattr(outcome, "hold_reason", None) == "claim-changed"
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert _is_open(client=client, token=token)


def test_a_repeated_absent_run_rests_the_item_for_a_human_under_the_won_token(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()

    outcome = _recover(repo=repo, item=item, action="absent-run-repeated")

    record = client.show_issue(issue_id=_ITEM_ID)
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert getattr(outcome, "hold_reason", None) is None
    assert record["status"] == "blocked"
    assert "blocked-reason:needs-human" in record["labels"]
    assert (won["writer"], won["intent"]) == (
        "stranded-claim-recovery",
        "absent-run-repeated-rest",
    )
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]


@pytest.mark.parametrize("action", ["absent-run-release", "absent-run-repeated"])
def test_a_recovery_that_loses_the_token_is_held_as_claim_changed_and_leaves_the_item(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3, on both absent-run routes."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    outcome = _recover(repo=repo, item=item, action=action)

    assert getattr(outcome, "hold_reason", None) == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER


def test_a_claim_naming_no_token_is_held_as_effect_unobservable_and_not_written_blind(
    tmp_path: Path,
) -> None:
    """A guarded write that fails for any reason but a lost token is not `claim-changed`."""
    repo = _repo(tmp_path=tmp_path)
    item, client, _ = _seed(name_a_token=False)
    before = _snapshot(client=client)

    outcome = _recover(repo=repo, item=item)

    assert getattr(outcome, "hold_reason", None) == "effect-unobservable"
    assert _snapshot(client=client) == before


def test_a_recovery_that_decided_on_a_stale_read_is_refused_by_the_record_the_write_is_based_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both re-reads answered from before a newer dispatch re-stamped the claim.

    The re-reads are the recovery's own, earlier than the write. The guarded
    transition asks the same three facts of the record it is based on, so a
    claim that changed after the last re-read is still `claim-changed`, and the
    token the newer dispatch holds is never contested.
    """
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _seed()
    stale = effects.claim_row_for(path=_config(), work_item_id=_ITEM_ID)
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_stamp(run_id="01ANEWRUN"))
    before = _snapshot(client=client)
    monkeypatch.setattr(effects, "claim_row_for", lambda **_: stale)

    outcome = _recover(repo=repo, item=item)

    assert getattr(outcome, "hold_reason", None) == "claim-changed"
    assert _snapshot(client=client) == before
    assert _is_open(client=client, token=token)

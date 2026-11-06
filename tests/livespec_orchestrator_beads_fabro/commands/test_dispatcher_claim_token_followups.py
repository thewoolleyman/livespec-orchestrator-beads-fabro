"""Four claim writers the claim-token cutover left unable to act, or untruthful.

`SPECIFICATION/contracts.md` ("Dispatcher policy settings" -> "Stranded claim
release" -> "Claim tokens") and `SPECIFICATION/scenarios.md` Scenario 263 say
one thing about every claim-changing write: exactly one writer changes the
claim, and every other writer stands down having written nothing to the item.
The first cut of that protocol on the Dispatcher got four writers wrong, each
only while `dispatcher.claim_tokens` is `true`:

- A GROOM-DOOR CLAIM COULD NEVER BE LAUNCHED. The door moves an item
  `backlog -> active` and the drain then admits that row. The admission stated
  its decision as "still `ready`", which such a row never is, so every pass
  refused it.
- A REWORK RE-DISPATCH COULD NEVER FINISH. The rework leg left the previous
  dispatch's claim stamp on the row, so the new dispatch's run stamp and every
  one of its terminal writes was refused as another run's.
- A TERMINAL-COMPLETION RECOVERY THAT LOST THE TOKEN REPORTED A RECOVERY. The
  delegated dispositions return nothing, so a refused one read as applied.
- THE GROOM APPLY SEAM CLOSED THE ORIGINAL WITHOUT A TOKEN. Its release was
  guarded and its close was not.

Every case drives a public entry point against the in-memory tenant and asserts
on what the tenant then holds. Where two admissions must have planned on ONE
state of a row, the second is made to plan before the first writes: a
Dispatcher mints its dispatch id after it has planned and before it claims, so
the first admission is run from inside the second's mint.

THE DISABLED CASES ARE HERE ON PURPOSE. The cutover key defaults to `false`,
and until it is committed `true` none of these writers may add a ledger write.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_STAMP_METADATA_KEY,
    CLAIM_TOKEN_METADATA_KEY,
    ClaimStamp,
    create_claim_token,
    record_claim_stamp,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    LABEL_REWORK_PENDING,
    update_work_item_rework_pending,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as selfup
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission import admit_and_select
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_apply import file_groom_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_door import groom_dispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import stamp_dispatch_run
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery import (
    ClaimRecoveryRequest,
    recover_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_terminal import (
    TerminalObservation,
    apply_terminal_disposition,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_ITEM_ID = "bd-ib-followup"
_FIRST_RUN = "01FIRSTRUN"
_SECOND_RUN = "01SECONDRUN"
_FIRST_DISPATCH = "01FIRSTDISPATCH"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_HOST = "owning-host"
_NOW = "2026-11-06T09:00:00Z"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = ".fabro/workflows/groom-cut"
_SLICE = "Move the filing host-side"
_ANOTHER_WRITER = "another writer won this token"
_ADMISSION = "dispatcher-admission"
_REFUSED_STAGE = "claim-write-refused"
# A pid no process can hold: the door's own, once the door has returned and exited.
_EXITED_DOOR_PID = 999999999


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


def _tenant() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _repo(*, tmp_path: Path, claim_tokens: bool = True, name: str = "repo") -> Path:
    """One checkout of the tenant, registering a groom variant."""
    repo = tmp_path / name
    variant = repo / _GROOM_DIR
    variant.mkdir(parents=True)
    _ = (variant / "workflow.toml").write_text(
        '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n',
        encoding="utf-8",
    )
    dispatcher: dict[str, object] = {"workflows": {_GROOM_VARIANT: _GROOM_DIR}}
    if claim_tokens:
        dispatcher["claim_tokens"] = True
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _journal(*, repo: Path) -> JournalFile:
    path = repo / "tmp" / "journal.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text("", encoding="utf-8")
    return JournalFile(path=path)


def _rows(*, journal: JournalFile) -> list[dict[str, object]]:
    return [json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines()]


def _stages(*, journal: JournalFile) -> list[object]:
    return [row.get("stage") for row in _rows(journal=journal)]


def _item(
    *, status: WorkItemStatus, assignee: str | None, rework_pending: bool = False
) -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A slice whose claim is already held",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=assignee,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="- The slice is verified green by the check suite.",
        rework_pending=rework_pending,
    )


def _first_dispatch_stamp() -> ClaimStamp:
    """The stamp the row's PREVIOUS dispatch left: its dispatch, its host, its run."""
    return ClaimStamp(
        dispatch_id=_FIRST_DISPATCH,
        dispatching_host=_HOST,
        run_id=_FIRST_RUN,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )


def _name_a_token(*, client: FakeBeadsClient) -> str:
    """Name an open current token on the filed item, as the migration pass does."""
    token = create_claim_token(client=client)
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return token


def _file(*, item: WorkItem) -> tuple[FakeBeadsClient, str]:
    """File `item` and name an open current token on it."""
    append_work_item(path=_config(), item=item)
    client = _tenant()
    return client, _name_a_token(client=client)


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _current_token(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _stamp(*, client: FakeBeadsClient) -> dict[str, object]:
    """The item's claim stamp as the tenant holds it; empty when it holds none."""
    return dict(
        client.show_issue(issue_id=_ITEM_ID)["metadata"].get(CLAIM_STAMP_METADATA_KEY) or {}
    )


def _close_of(*, client: FakeBeadsClient, token: str) -> dict[str, object]:
    """The reason `token` was closed with; empty while it is open."""
    return json.loads(client.show_issue(issue_id=token).get("close_reason") or "{}")


def _labels(*, client: FakeBeadsClient) -> list[object]:
    return list(client.show_issue(issue_id=_ITEM_ID).get("labels") or [])


def _lose_contest(
    *, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch, contest: int = 1
) -> None:
    """Let another writer win the item's current token on its `contest`-th contest."""
    close = client.close_issue_without_verdict
    contests: list[str] = []

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == _current_token(client=client):
            contests.append(issue_id)
            if len(contests) == contest:
                close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _admit_while_the_other_is_between_plan_and_claim(
    *, monkeypatch: pytest.MonkeyPatch, other: Callable[[], list[str]]
) -> list[list[str]]:
    """Run `other` from inside the next dispatch-id mint, once.

    An admission mints its dispatch id after it has planned and before it
    claims, so the admission that calls the patched mint has already read the
    row when `other` writes it. The list is filled with what `other` admitted.
    """
    mint = selfup.run_id
    admitted_by_other: list[list[str]] = []

    def _mint_after_the_other_admission() -> str:
        monkeypatch.setattr(selfup, "run_id", mint)
        admitted_by_other.append(other())
        return mint()

    monkeypatch.setattr(selfup, "run_id", _mint_after_the_other_admission)
    return admitted_by_other


# --- C1: a row the groom door claimed is launched, exactly once -------------------------------


def _door_claimed(*, repo: Path) -> tuple[WorkItem, FakeBeadsClient, str]:
    """A row the real groom door moved `backlog -> active`, and the token it named."""
    client, _ = _file(item=_item(status="backlog", assignee=None))
    opened = groom_dispatch(
        repo=repo,
        item=_item(status="backlog", assignee=None),
        variant=_GROOM_VARIANT,
        journal=_journal(repo=repo),
    )
    assignee = getattr(opened, "assignee", None)
    # The door writes its claim and its process exits, which is how a later
    # Dispatcher finds it: the lock is the door's, and nobody is holding it.
    lock = dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID)
    payload = json.loads(lock.read_text(encoding="utf-8"))
    payload["pid"] = _EXITED_DOOR_PID
    _ = lock.write_text(json.dumps(payload), encoding="utf-8")
    return _item(status="active", assignee=assignee), client, _current_token(client=client)


def _admitted(*, repo: Path, item: WorkItem, journal: JournalFile) -> list[str]:
    admission = admit_and_select(
        repo=repo, items=[item], candidates=[item], journal=journal, enforce_cap=False
    )
    return [admitted.id for admitted in admission.admitted]


def test_an_enabled_admission_launches_the_row_the_groom_door_claimed(tmp_path: Path) -> None:
    """The door's claim is admitted through its token, and stamped for this dispatch."""
    repo = _repo(tmp_path=tmp_path)
    claimed, client, door_token = _door_claimed(repo=repo)
    journal = _journal(repo=repo)

    admitted = _admitted(repo=repo, item=claimed, journal=journal)

    record = client.show_issue(issue_id=_ITEM_ID)
    won = _close_of(client=client, token=door_token)
    stamp = _stamp(client=client)
    lock = live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID)
    assert admitted == [_ITEM_ID]
    assert (record["status"], record["assignee"]) == ("active", claimed.assignee)
    assert (won.get("writer"), won.get("intent")) == (_ADMISSION, "admit")
    assert won.get("successor") == _current_token(client=client)
    # The pending claim stamp rode the same write: this dispatch, and no run yet.
    assert stamp.get("run_id", "absent") is None
    assert lock is not None
    assert stamp.get("dispatch_id") == lock.dispatch_id
    assert "ledger-admit" in _stages(journal=journal)


def test_two_admissions_that_planned_on_one_door_claim_launch_it_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second writes after the first has finished, and must not win its successor."""
    first_host = _repo(tmp_path=tmp_path, name="first-host")
    second_host = _repo(tmp_path=tmp_path, name="second-host")
    claimed, client, door_token = _door_claimed(repo=first_host)
    second_journal = _journal(repo=second_host)
    left_by_first: list[dict[str, object]] = []

    def _first_admission() -> list[str]:
        first = _admitted(repo=first_host, item=claimed, journal=_journal(repo=first_host))
        left_by_first.append(_snapshot(client=client))
        return first

    first = _admit_while_the_other_is_between_plan_and_claim(
        monkeypatch=monkeypatch, other=_first_admission
    )
    second = _admitted(repo=second_host, item=claimed, journal=second_journal)

    successor = _close_of(client=client, token=door_token).get("successor")
    assert (first, second) == ([[_ITEM_ID]], [])
    assert [_snapshot(client=client)] == left_by_first
    assert _current_token(client=client) == successor
    assert client.show_issue(issue_id=str(successor))["status"] != "closed"
    second_stages = _stages(journal=second_journal)
    assert "ledger-admit" not in second_stages
    assert _REFUSED_STAGE in second_stages


def test_a_disabled_admission_of_a_door_claim_touches_no_token(tmp_path: Path) -> None:
    """Before the cutover the door's row is admitted by the writes it always was."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    claimed, client, token = _door_claimed(repo=repo)

    admitted = _admitted(repo=repo, item=claimed, journal=_journal(repo=repo))

    record = client.show_issue(issue_id=_ITEM_ID)
    assert admitted == [_ITEM_ID]
    assert (record["status"], record["assignee"]) == ("active", claimed.assignee)
    assert _current_token(client=client) == token
    assert client.show_issue(issue_id=token)["status"] != "closed"


# --- C2: a rework re-dispatch claims its row, and can then finish -----------------------------


def _marked_row() -> tuple[WorkItem, FakeBeadsClient, str]:
    """A row parked for rework: `active`, marked, stamped by the dispatch before."""
    item = _item(status="active", assignee="fabro", rework_pending=True)
    append_work_item(path=_config(), item=replace(item, rework_pending=False))
    update_work_item_rework_pending(path=_config(), item_id=_ITEM_ID, value=True)
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_first_dispatch_stamp())
    client = _tenant()
    return item, client, _name_a_token(client=client)


def _reworked(*, repo: Path, item: WorkItem, journal: JournalFile) -> list[str]:
    admission = admit_and_select(
        repo=repo, items=[item], candidates=[], journal=journal, enforce_cap=False
    )
    return [admitted.id for admitted in admission.rework]


def test_an_enabled_rework_admission_claims_the_row_for_its_own_dispatch(tmp_path: Path) -> None:
    """The previous dispatch's stamp is replaced, under the won token, by a pending one."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _marked_row()

    reworked = _reworked(repo=repo, item=item, journal=_journal(repo=repo))

    record = client.show_issue(issue_id=_ITEM_ID)
    won = _close_of(client=client, token=token)
    stamp = _stamp(client=client)
    lock = live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID)
    assert reworked == [_ITEM_ID]
    assert (record["status"], record["assignee"]) == ("active", "fabro")
    assert LABEL_REWORK_PENDING in _labels(client=client)
    assert (won.get("writer"), won.get("intent")) == (_ADMISSION, "rework-admit")
    assert won.get("successor") == _current_token(client=client)
    assert stamp.get("run_id") is None
    assert lock is not None
    assert stamp.get("dispatch_id") == lock.dispatch_id


def test_an_enabled_rework_dispatch_stamps_its_run_and_lands_its_terminal(
    tmp_path: Path,
) -> None:
    """The whole arc the defect broke: admit, learn the run, reach a terminal."""
    repo = _repo(tmp_path=tmp_path)
    item, client, _ = _marked_row()
    journal = _journal(repo=repo)

    reworked = _reworked(repo=repo, item=item, journal=journal)
    lock = live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID)
    _ = stamp_dispatch_run(
        plan=build_plan(
            repo=repo,
            work_item_id=_ITEM_ID,
            workflow_toml=repo / "workflow.toml",
            goal_file=repo / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=repo / "janitor",
            fabro_factory_name=_FACTORY,
            fabro_factory_server=_SERVER,
        ),
        journal=journal,
        run_id=_SECOND_RUN,
        dispatch_id=getattr(lock, "dispatch_id", None),
    )
    stamped_run = _stamp(client=client).get("run_id")
    escalate_needs_human_block(
        repo=repo,
        item=item,
        outcome=DispatchOutcome(
            work_item_id=_ITEM_ID,
            status="blocked",
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="",
            fabro_run_id=_SECOND_RUN,
            fabro_factory_name=_FACTORY,
        ),
        journal=journal,
    )

    stamps = [row.get("stamped") for row in _rows(journal=journal) if "stamped" in row]
    assert reworked == [_ITEM_ID]
    assert stamps == [True]
    assert stamped_run == _SECOND_RUN
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "blocked"
    assert LABEL_REWORK_PENDING not in _labels(client=client)
    assert _REFUSED_STAGE not in _stages(journal=journal)


def test_two_rework_admissions_that_planned_on_one_row_claim_it_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two Dispatchers on two hosts share no lock, so only the token can refuse the second."""
    first_host = _repo(tmp_path=tmp_path, name="first-host")
    second_host = _repo(tmp_path=tmp_path, name="second-host")
    item, client, token = _marked_row()
    second_journal = _journal(repo=second_host)
    left_by_first: list[dict[str, object]] = []

    def _first_admission() -> list[str]:
        first = _reworked(repo=first_host, item=item, journal=_journal(repo=first_host))
        left_by_first.append(_snapshot(client=client))
        return first

    first = _admit_while_the_other_is_between_plan_and_claim(
        monkeypatch=monkeypatch, other=_first_admission
    )
    second = _reworked(repo=second_host, item=item, journal=second_journal)

    assert (first, second) == ([[_ITEM_ID]], [])
    assert [_snapshot(client=client)] == left_by_first
    assert _current_token(client=client) == _close_of(client=client, token=token).get("successor")
    assert live_dispatch_lock(repo=second_host, work_item_id=_ITEM_ID) is None
    second_stages = _stages(journal=second_journal)
    assert "ledger-rework-admit" not in second_stages
    assert _REFUSED_STAGE in second_stages


def test_a_refused_rework_claim_is_reported_as_a_failed_outcome_not_a_deferral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row the protocol refused wrote nothing, took no lock, and says why."""
    repo = _repo(tmp_path=tmp_path)
    item, client, _ = _marked_row()
    before = _snapshot(client=client)
    _lose_contest(client=client, monkeypatch=monkeypatch)

    admission = admit_and_select(
        repo=repo, items=[item], candidates=[], journal=_journal(repo=repo), enforce_cap=False
    )

    refused = [(outcome.status, outcome.stage) for outcome in admission.refused]
    assert admission.rework == []
    assert admission.deferred == []
    assert refused == [("failed", "admission-claim-refused")]
    assert "claim-changed" in " ".join(outcome.detail for outcome in admission.refused)
    assert _snapshot(client=client) == before
    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is None


def test_a_disabled_rework_admission_writes_nothing_to_the_ledger(tmp_path: Path) -> None:
    """Before the cutover the rework leg takes its lock and leaves the row alone."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    item, client, token = _marked_row()
    before = _snapshot(client=client)
    journal = _journal(repo=repo)

    reworked = _reworked(repo=repo, item=item, journal=journal)

    assert reworked == [_ITEM_ID]
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert live_dispatch_lock(repo=repo, work_item_id=_ITEM_ID) is not None
    assert "dispatch-claim-stamp-pending" not in _stages(journal=journal)


# --- C3: a terminal-completion recovery that loses its token is a hold ------------------------


def _stranded_claim(*, name_a_token: bool = True) -> tuple[WorkItem, FakeBeadsClient, str]:
    """An `active` claim stamped with a run that ended with no Dispatcher watching."""
    item = _item(status="active", assignee="fabro")
    append_work_item(path=_config(), item=item)
    record_claim_stamp(path=_config(), work_item_id=_ITEM_ID, stamp=_first_dispatch_stamp())
    client = _tenant()
    token = _name_a_token(client=client) if name_a_token else create_claim_token(client=client)
    return item, client, token


def _terminal(*, status: str) -> TerminalObservation:
    return TerminalObservation(
        outcome=DispatchOutcome(
            work_item_id=_ITEM_ID,
            status=status,
            stage="fabro-run",
            pr_number=None,
            merge_sha=None,
            detail="the sandbox vanished mid-run",
            fabro_run_id=_FIRST_RUN,
            fabro_factory_name=_FACTORY,
            needs_human_kind=STAGE_FAILURE if status == "blocked" else None,
        )
    )


def _complete_terminal(*, repo: Path, item: WorkItem) -> object:
    return recover_claim(
        repo=repo,
        journal=_journal(repo=repo),
        request=ClaimRecoveryRequest(
            item=item,
            run_id=_FIRST_RUN,
            factory_name=_FACTORY,
            factory_server_url=_SERVER,
            action="terminal-run-completion",
            terminal=_terminal(status="failed"),
        ),
        now_iso=_NOW,
    )


def _cause_comments() -> list[str]:
    return [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith(NEEDS_HUMAN_CAUSE_MARKER)
    ]


def test_a_terminal_completion_that_loses_the_token_is_held_as_claim_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It wrote nothing to the item, so it must not report the claim recovered."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _stranded_claim()
    before = _snapshot(client=client)
    _lose_contest(client=client, monkeypatch=monkeypatch)

    outcome = _complete_terminal(repo=repo, item=item)

    assert getattr(outcome, "hold_reason", None) == "claim-changed"
    assert getattr(outcome, "effects_written", None) is None
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER
    # No account of a rest that did not happen is left on the item.
    assert _cause_comments() == []


def test_a_terminal_completion_refused_for_any_other_reason_is_effect_unobservable(
    tmp_path: Path,
) -> None:
    """An item naming no token is refused as `claim-token-missing`, which is not a lost race."""
    repo = _repo(tmp_path=tmp_path)
    item, client, _ = _stranded_claim(name_a_token=False)
    before = _snapshot(client=client)

    outcome = _complete_terminal(repo=repo, item=item)

    assert getattr(outcome, "hold_reason", None) == "effect-unobservable"
    assert _snapshot(client=client) == before
    assert _cause_comments() == []


def test_a_terminal_route_refused_on_a_row_another_writer_moved_reports_the_refusal(
    tmp_path: Path,
) -> None:
    """The row no longer reads as this claim, which is not evidence that a route landed."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _stranded_claim()
    client.update_issue(issue_id=_ITEM_ID, status="ready", clear_assignee=True)
    before = _snapshot(client=client)

    applied = apply_terminal_disposition(
        repo=repo,
        item=item,
        observation=_terminal(status="blocked"),
        journal=_journal(repo=repo),
        now_iso=_NOW,
    )

    assert getattr(applied, "outcome", None) == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert _cause_comments() == []


def test_a_terminal_completion_that_wins_the_token_rests_the_item_and_reports_it(
    tmp_path: Path,
) -> None:
    """The other half: the recovery that wins is still the one writer that acts."""
    repo = _repo(tmp_path=tmp_path)
    item, client, token = _stranded_claim()

    outcome = _complete_terminal(repo=repo, item=item)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert getattr(outcome, "hold_reason", None) is None
    assert getattr(outcome, "effects_written", None) == (
        "journal-record",
        "terminal-routing",
        "needs-human-rest",
    )
    assert record["status"] == "blocked"
    assert _close_of(client=client, token=token).get("successor") == _current_token(client=client)
    assert len(_cause_comments()) == 1


# --- C4: the groom apply seam closes the original only under a won token ----------------------


def _plan_text(*, repo: Path) -> str:
    return (
        "livespec-groom-plan | approver=thewoolleyman | route=resolve-blocked ready valve"
        f" ;; slice={_SLICE} | tier=factory | repo={repo.name}"
        " | acceptance=The Dispatcher files the cut. | blockers=none | spec=no"
        " | scope=Read the plan off the terminated run and file it."
    )


def _apply(*, repo: Path, item: WorkItem, journal: JournalFile) -> bool:
    return file_groom_plan(
        repo=repo,
        item=item,
        text=_plan_text(repo=repo),
        variant=_GROOM_VARIANT,
        run_id=_FIRST_RUN,
        journal=journal,
    )


def _filed_slice_ids() -> list[str]:
    return [item.id for item in read_work_items(path=_config()) if item.title == _SLICE]


def test_an_enabled_apply_wins_the_successor_token_before_it_closes_the_original(
    tmp_path: Path,
) -> None:
    """The release names a successor, and the close is made only after winning that one."""
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active", assignee="dispatcher")
    client, token = _file(item=item)
    journal = _journal(repo=repo)

    filed = _apply(repo=repo, item=item, journal=journal)

    release = _close_of(client=client, token=token)
    hold = _close_of(client=client, token=str(release.get("successor")))
    assert filed is True
    assert release.get("intent") == "groom-apply-release"
    assert (hold.get("writer"), hold.get("intent")) == ("dispatcher-terminal", "groom-apply-close")
    assert hold.get("successor") == _current_token(client=client)
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "closed"
    assert _stages(journal=journal) == ["groom-cut-filed"]


def test_an_enabled_apply_that_loses_the_closing_token_leaves_the_original_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another writer took the original while the slices were filed, so it is not closed."""
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="active", assignee="dispatcher")
    client, _ = _file(item=item)
    _lose_contest(client=client, monkeypatch=monkeypatch, contest=2)
    journal = _journal(repo=repo)

    filed = _apply(repo=repo, item=item, journal=journal)

    record = client.show_issue(issue_id=_ITEM_ID)
    detail = " ".join(
        str(row.get("detail"))
        for row in _rows(journal=journal)
        if row.get("stage") == "groom-cut-refused"
    )
    filed_ids = _filed_slice_ids()
    assert filed is False
    assert (record["status"], record.get("assignee")) == ("backlog", None)
    assert _stages(journal=journal) == [_REFUSED_STAGE, "groom-cut-refused"]
    assert "claim-changed" in detail
    # The slices were filed before the close was contested, and the refusal names them.
    assert len(filed_ids) == 1
    assert filed_ids[0] in detail


def test_a_disabled_apply_closes_the_original_without_touching_any_token(tmp_path: Path) -> None:
    """Before the cutover neither the release nor the close contests a token."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    item = _item(status="active", assignee="dispatcher")
    client, token = _file(item=item)
    journal = _journal(repo=repo)

    filed = _apply(repo=repo, item=item, journal=journal)

    assert filed is True
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "closed"
    assert _current_token(client=client) == token
    assert client.show_issue(issue_id=token)["status"] != "closed"
    assert _stages(journal=journal) == ["groom-cut-filed"]

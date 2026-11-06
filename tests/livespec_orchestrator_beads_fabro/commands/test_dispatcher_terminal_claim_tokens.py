"""Every Dispatcher terminal transition of a claim wins the item's token first.

`SPECIFICATION/contracts.md` ("Dispatcher policy settings" -> "Stranded claim
release" -> "Claim tokens") makes "a Dispatcher terminal write" one of the
writers of a dispatch claim: while `dispatcher.claim_tokens` is `true` it may
change the item only after winning the item's current token, naming the
successor in that one write, and a writer that does not win writes nothing to
the item.

One table row per terminal writer, driven through that writer's own public
entry point against the in-memory tenant, and each row is run four ways:

- WON: the item lands where the disposition says, the former token's close
  reason names this writer and its intent, and the item names the successor
  that reason names.
- LOST: another writer's close of the token landed first. The item's record
  (status, assignee, labels, metadata) is exactly what it was, the refusal is
  journaled as `claim-write-refused`, and the disposition's own success record
  is absent. A ledger COMMENT a disposition writes ahead of its transition is
  not part of that record: it is the account of what the run did, and the
  contract orders it before the transition.

- TWICE ON ONE READ: two Dispatchers, each with its own journal, were handed
  the same read of the item, and the second runs only after the first has
  finished. The first's successor is open and the second could win it. It must
  stand down as `claim-changed`, uncontested, leaving the item exactly as the
  first left it.
- ANOTHER RUN'S CLAIM: the item is where the disposition expects it, but its
  claim stamp names a different run. A disposition of one particular run is
  refused; a disposition that never knew a run is not, because its decision
  rested on the claim alone.

The post-merge acceptance valve has more than one write, so it has its own
cases below the table.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
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
from livespec_orchestrator_beads_fabro.commands import _dispatcher_completion
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_result import (
    outcome_after_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_rework import (
    rework_or_block_failed_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
    complete_and_accept,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import NON_CONVERGED_MARKER
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_disposition import (
    dispose_provider_limit_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_disposition import (
    dispose_run_wall_budget_cancel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget_records import (
    RUN_WALL_BUDGET_EXCEEDED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    dispose_stall_cancel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_routing import (
    dispose_terminal_routing,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-terminal"
_RUN_ID = "01TERMINALRUN"
_NOW = "2026-11-06T09:00:00Z"
_WRITER = "dispatcher-terminal"
_ANOTHER_WRITER = "another writer won this token"
_REFUSED_STAGE = "claim-write-refused"
_STALL_CANCEL_ROW = json.dumps({"stage": "watchdog-stall-cancel", "work_item_id": _ITEM_ID})


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


def _journal(
    *, repo: Path, lines: tuple[str, ...] = (), name: str = "journal.jsonl"
) -> JournalFile:
    path = repo / name
    _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return JournalFile(path=path)


def _stages(*, journal: JournalFile) -> list[object]:
    return [
        json.loads(line).get("stage")
        for line in journal.path.read_text(encoding="utf-8").splitlines()
    ]


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice reaching its terminal",
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
    )
    return replace(base, **overrides)


def _seed(
    *, item: WorkItem, metadata: dict[str, object] | None = None
) -> tuple[FakeBeadsClient, str]:
    """File the claim and give it an open current token, as the migration pass does."""
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    merged = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    merged.update(metadata or {})
    merged[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=merged)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    return copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))


def _current_token(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _won_intent(*, client: FakeBeadsClient, token: str) -> object:
    """The intent `token` was won with; asserts the winner was a terminal write.

    The successor the close reason names is returned to the caller through the
    token chain, so a disposition of two writes can be followed link by link.
    """
    won = json.loads(client.show_issue(issue_id=token)["close_reason"])
    assert won["writer"] == _WRITER
    return won["intent"]


def _successor_of(*, client: FakeBeadsClient, token: str) -> str:
    return json.loads(client.show_issue(issue_id=token)["close_reason"])["successor"]


def _lose_contest(
    *, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch, contest: int = 1
) -> None:
    """Let another writer win the item's current token on its `contest`-th contest.

    A contest is a close of whichever token the item names at that moment, so
    the second contest of a two-write disposition is the close of the successor
    its first write named.
    """
    close = client.close_issue_without_verdict
    contests: list[str] = []

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == _current_token(client=client):
            contests.append(issue_id)
            if len(contests) == contest:
                close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _outcome(*, status: str, stage: str = "fabro-run", **fields: object) -> DispatchOutcome:
    base = DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage=stage,
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id=_RUN_ID,
        fabro_factory_name="hp",
    )
    return replace(base, **fields)


def _provider_limit_release() -> ProviderLimitRelease:
    return ProviderLimitRelease(
        factory="hp",
        run_id=_RUN_ID,
        node_attempt="implement",
        matched=None,
        executed=AcpCandidateIdentity(
            display_name="Claude ACP primary",
            candidate_key="claude-primary",
            availability_key="anthropic-team",
        ),
        legacy_provider="anthropic",
        recovery_source=f"the tree was preserved on refs/heads/needs-human/{_RUN_ID}",
    )


_ACTIVE_CLAIM = _item()


@dataclass(frozen=True, kw_only=True)
class _Writer:
    """One routed terminal writer: how to drive it, and where a win leaves the item."""

    intent: str
    run: Callable[[Path, WorkItem, JournalFile], None]
    lands: tuple[str, str | None]
    success_stage: str | None
    # Whether the disposition is of one particular run. A release made before
    # any run was learned, and a failing-pass disposition, are not.
    rests_on_run: bool = True
    item: WorkItem = _ACTIVE_CLAIM
    metadata: tuple[tuple[str, object], ...] = ()
    journal_lines: tuple[str, ...] = ()


_WRITERS = (
    _Writer(
        intent="needs-human-block",
        run=lambda repo, item, journal: escalate_needs_human_block(
            repo=repo, item=item, outcome=_outcome(status="blocked"), journal=journal
        ),
        lands=("blocked", "fabro"),
        success_stage="needs-human-blocked",
    ),
    _Writer(
        intent="pre-run-release",
        run=lambda repo, item, journal: release_pre_run_claim_if_needed(
            repo=repo,
            item=item,
            outcome=_outcome(status="failed", stage="run-config-overlay", fabro_run_id=None),
            journal=journal,
        ),
        lands=("ready", None),
        success_stage="ledger-admit-release",
        rests_on_run=False,
    ),
    _Writer(
        intent="provider-limit-release",
        run=lambda repo, item, journal: dispose_provider_limit_release(
            repo=repo,
            item=item,
            outcome=_outcome(
                status="provider-limit-release",
                stage="provider-limit-release",
                provider_limit_release=_provider_limit_release(),
            ),
            journal=journal,
            now_iso=_NOW,
        ),
        lands=("ready", None),
        # The release record is written BEFORE the transition, by the clause's
        # own order, so it is present on both arms and is not a success record.
        success_stage=None,
    ),
    _Writer(
        intent="run-wall-budget-rest",
        run=lambda repo, item, journal: dispose_run_wall_budget_cancel(
            repo=repo,
            item=item,
            outcome=_outcome(status=RUN_WALL_BUDGET_EXCEEDED_STAGE),
            journal=journal,
        ),
        lands=("blocked", "fabro"),
        success_stage="run-wall-budget-needs-human",
    ),
    _Writer(
        intent="stall-release",
        run=lambda repo, item, journal: dispose_stall_cancel(
            repo=repo, item=item, outcome=_outcome(status="stalled-no-progress"), journal=journal
        ),
        lands=("ready", None),
        success_stage="stall-cancel-release",
    ),
    _Writer(
        intent="stall-repeat-rest",
        run=lambda repo, item, journal: dispose_stall_cancel(
            repo=repo, item=item, outcome=_outcome(status="stalled-no-progress"), journal=journal
        ),
        lands=("blocked", "fabro"),
        success_stage="stall-cancel-needs-human",
        journal_lines=(_STALL_CANCEL_ROW, _STALL_CANCEL_ROW),
    ),
    _Writer(
        intent="external-cancel-rest",
        run=lambda repo, item, journal: dispose_terminal_routing(
            repo=repo,
            item=item,
            outcome=_outcome(status="cancelled"),
            journal=journal,
            now_iso=_NOW,
        ),
        lands=("blocked", "fabro"),
        success_stage=None,
    ),
    _Writer(
        intent="acceptance-rework-return",
        run=lambda repo, item, journal: rework_or_block_failed_acceptance(
            repo=repo, item=item, policy="ai-only", merged=False, journal=journal
        ),
        lands=("active", "fabro"),
        success_stage="acceptance-auto-rework",
        rests_on_run=False,
        item=_item(status="acceptance"),
    ),
    _Writer(
        intent="acceptance-rework-cap-block",
        run=lambda repo, item, journal: rework_or_block_failed_acceptance(
            repo=repo, item=item, policy="ai-only", merged=True, journal=journal
        ),
        lands=("blocked", "fabro"),
        success_stage="acceptance-rework-cap-exceeded",
        rests_on_run=False,
        item=_item(status="acceptance"),
        metadata=(("acceptance_failed_ai_passes", 9),),
    ),
    _Writer(
        intent="non-convergence-bounce",
        run=lambda repo, item, journal: bounce_non_convergence_to_backlog(
            repo=repo,
            item=item,
            outcome=_outcome(status="failed", detail=f"{NON_CONVERGED_MARKER}: cap hit"),
            journal=journal,
        ),
        lands=("backlog", "fabro"),
        success_stage="non-convergence-bounce",
    ),
)
_WRITER_IDS = [writer.intent for writer in _WRITERS]


@pytest.mark.parametrize("writer", _WRITERS, ids=_WRITER_IDS)
def test_a_terminal_writer_that_wins_the_token_lands_its_transition_and_names_the_successor(
    writer: _Writer, tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=writer.item, metadata=dict(writer.metadata))
    journal = _journal(repo=repo, lines=writer.journal_lines)

    writer.run(repo, writer.item, journal)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert (record["status"], record["assignee"]) == writer.lands
    assert _won_intent(client=client, token=token) == writer.intent
    assert _current_token(client=client) == _successor_of(client=client, token=token)
    assert _REFUSED_STAGE not in _stages(journal=journal)


@pytest.mark.parametrize("writer", _WRITERS, ids=_WRITER_IDS)
def test_a_terminal_writer_that_loses_the_token_writes_nothing_to_the_item(
    writer: _Writer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=writer.item, metadata=dict(writer.metadata))
    before = _snapshot(client=client)
    _lose_contest(client=client, monkeypatch=monkeypatch)
    journal = _journal(repo=repo, lines=writer.journal_lines)

    writer.run(repo, writer.item, journal)

    stages = _stages(journal=journal)
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER
    assert _REFUSED_STAGE in stages
    assert writer.success_stage not in stages


@pytest.mark.parametrize("writer", _WRITERS, ids=_WRITER_IDS)
def test_a_terminal_writer_run_twice_on_one_read_writes_the_item_exactly_once(
    writer: _Writer, tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=writer.item, metadata=dict(writer.metadata))
    second_journal = _journal(repo=repo, lines=writer.journal_lines, name="second.jsonl")

    writer.run(repo, writer.item, _journal(repo=repo, lines=writer.journal_lines))
    as_first_left_it = _snapshot(client=client)
    writer.run(repo, writer.item, second_journal)

    first_successor = _successor_of(client=client, token=token)
    second_stages = _stages(journal=second_journal)
    assert _snapshot(client=client) == as_first_left_it
    # The second writer contested nothing: the item still names the first
    # writer's successor, and that successor is still open.
    assert _current_token(client=client) == first_successor
    assert client.show_issue(issue_id=first_successor)["status"] != "closed"
    assert _REFUSED_STAGE in second_stages
    assert writer.success_stage not in second_stages


@pytest.mark.parametrize("writer", _WRITERS, ids=_WRITER_IDS)
def test_a_terminal_writer_meeting_another_runs_claim_writes_only_if_it_never_knew_a_run(
    writer: _Writer, tmp_path: Path
) -> None:
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=writer.item, metadata=dict(writer.metadata))
    record_claim_stamp(
        path=_config(),
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id="01ANOTHERDISPATCH",
            dispatching_host="another-host",
            run_id="01ANOTHERRUN",
            factory_name="hp",
            factory_server=None,
        ),
    )
    before = _snapshot(client=client)

    writer.run(repo, writer.item, _journal(repo=repo, lines=writer.journal_lines))

    contested = client.show_issue(issue_id=token)["status"] == "closed"
    assert contested is not writer.rests_on_run
    assert (_snapshot(client=client) == before) is writer.rests_on_run


def test_a_won_rework_return_carries_the_failed_pass_count_in_the_claiming_write(
    tmp_path: Path,
) -> None:
    """The count is not a write of its own once the key is true: it rides the won one."""
    repo = _repo(tmp_path=tmp_path)
    item = _item(status="acceptance")
    client, _ = _seed(item=item)

    rework_or_block_failed_acceptance(
        repo=repo, item=item, policy="ai-only", merged=False, journal=_journal(repo=repo)
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert record["metadata"]["acceptance_failed_ai_passes"] == 1
    assert "rework:pending" in record["labels"]


@dataclass(frozen=True, kw_only=True)
class _AcceptancePass:
    """The post-merge acceptance pass, standing in at its verdict."""

    verdict: str
    proof: None = None
    absent_evidence: tuple[str, ...] = ()

    def journal_record(self, *, work_item_id: str, policy: str) -> dict[str, object]:
        return {
            "stage": "acceptance-ai-pass",
            "work_item_id": work_item_id,
            "verdict": self.verdict,
            "acceptance_policy": policy,
        }


def _green_outcome() -> DispatchOutcome:
    return _outcome(status="green", stage="done", pr_number=11, merge_sha="feed01", detail="merged")


def _accept(
    *,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    verdict: str,
    monkeypatch: pytest.MonkeyPatch,
) -> DispatchOutcome:
    """Run the valve with the pass standing in, and report it as a dispatch would."""
    monkeypatch.setattr(
        _dispatcher_completion, "run_acceptance_pass", lambda **_: _AcceptancePass(verdict=verdict)
    )
    outcome = _green_outcome()
    return outcome_after_acceptance(
        outcome=outcome,
        disposition=complete_and_accept(repo=repo, item=item, outcome=outcome, journal=journal),
    )


@pytest.mark.parametrize(
    ("verdict", "close_intent"),
    [("PASS", "close-completed"), ("NO_CHANGE_NEEDED", "close-no-change-needed")],
)
def test_a_won_acceptance_close_wins_the_completion_token_and_then_its_successor(
    verdict: str, close_intent: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    client, token = _seed(item=item)
    journal = _journal(repo=repo)

    reported = _accept(
        repo=repo, item=item, journal=journal, verdict=verdict, monkeypatch=monkeypatch
    )

    held = _successor_of(client=client, token=token)
    assert (reported.status, reported.stage, reported.verdict) == ("green", "done", verdict)
    assert client.show_issue(issue_id=_ITEM_ID)["status"] == "closed"
    assert _won_intent(client=client, token=token) == "complete"
    assert _won_intent(client=client, token=held) == close_intent
    assert _REFUSED_STAGE not in _stages(journal=journal)


def test_a_completion_that_loses_the_token_writes_nothing_and_never_runs_the_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    client, _ = _seed(item=item)
    before = _snapshot(client=client)
    _lose_contest(client=client, monkeypatch=monkeypatch)
    journal = _journal(repo=repo)

    reported = _accept(
        repo=repo, item=item, journal=journal, verdict="PASS", monkeypatch=monkeypatch
    )

    assert _snapshot(client=client) == before
    assert _stages(journal=journal) == [_REFUSED_STAGE]
    assert (reported.status, reported.stage, reported.verdict) == (
        "needs-attention",
        "acceptance",
        None,
    )
    assert "claim-changed" in reported.detail


@pytest.mark.parametrize("verdict", ["PASS", "NO_CHANGE_NEEDED"])
def test_a_close_that_loses_the_token_leaves_the_item_in_acceptance_and_unclosed(
    verdict: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The completion won; the close's own contest, for the successor, was lost."""
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    client, token = _seed(item=item)
    _lose_contest(client=client, monkeypatch=monkeypatch, contest=2)
    journal = _journal(repo=repo)

    reported = _accept(
        repo=repo, item=item, journal=journal, verdict=verdict, monkeypatch=monkeypatch
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    stages = _stages(journal=journal)
    assert record["status"] == "acceptance"
    # The item still names the token the completion write named: the close's
    # hold wrote nothing, so no successor replaced it.
    assert _current_token(client=client) == _successor_of(client=client, token=token)
    assert _REFUSED_STAGE in stages
    assert {"ledger-accept", "ledger-accept-no-change-needed"}.isdisjoint(stages)
    assert (reported.status, reported.stage, reported.verdict) == (
        "needs-attention",
        "acceptance",
        verdict,
    )


def test_a_second_valve_handed_the_same_read_completes_nothing_and_never_runs_the_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sequential, not racing: the first valve closed the item; the second stands down."""
    repo = _repo(tmp_path=tmp_path)
    item = _item()
    client, token = _seed(item=item)
    second_journal = _journal(repo=repo, name="second.jsonl")

    first = _accept(
        repo=repo, item=item, journal=_journal(repo=repo), verdict="PASS", monkeypatch=monkeypatch
    )
    as_first_left_it = _snapshot(client=client)
    second = _accept(
        repo=repo, item=item, journal=second_journal, verdict="PASS", monkeypatch=monkeypatch
    )

    held = _successor_of(client=client, token=token)
    last = _successor_of(client=client, token=held)
    assert (first.stage, second.stage, second.status) == ("done", "acceptance", "needs-attention")
    assert _snapshot(client=client) == as_first_left_it
    assert client.show_issue(issue_id=last)["status"] != "closed"
    assert _stages(journal=second_journal) == [_REFUSED_STAGE]

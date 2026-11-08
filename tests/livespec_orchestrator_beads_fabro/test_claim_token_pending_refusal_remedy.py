"""A `claim-transition-pending` refusal names its remedy, for a valve and for intake.

`SPECIFICATION/contracts.md` ("Claim tokens") lets a writer take over a token
whose winner never wrote the item only after that writer has itself watched the
unapplied transition for the takeover wait. A valve press and an intake call
are one process each: each waits out that wait itself and writes once more, and
the second answer is final. When that answer is `claim-transition-pending`
again, the operator has to be told how the item gets written after all, which
is a Dispatcher pass on it: the Dispatcher loop keeps its sightings from one
pass to the next.

Each end-to-end case drives the public entry point against the in-memory
tenant, `drive.run_action` for the valve and `apply_intake_dor` for intake, on
an item left the way production leaves it: a first writer wins the item's
token and its item write then fails. While the refused writer waits, that
first write lands after all and a second writer strands the item again, so the
wait ends on a transition this process has only just seen. No case sleeps:
the wait is replaced by one on a clock the case owns.

The remedy is one wording for both writers, and only a pending transition
carries it: a writer that lost its token has nothing to wait for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands import _intake_valve_claim_writes as writes
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_INTAKE,
    ClaimWrite,
    TakeoverWait,
    resting_at,
    valve_claim_refusal,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_ITEM_ID = "bd-ib-pendingremedy"
_HEADING = "## Effective acceptance criteria"
_PENDING = "claim-transition-pending"
_LOST = "claim-changed"
_REMEDY = (
    f"Remedy: wait for or trigger a Dispatcher pass on {_ITEM_ID}. A Dispatcher loop keeps "
    "its first sighting of an unapplied transition from one pass to the next, and takes the "
    "transition over on a pass made after the takeover wait."
)
_NOT_WRITTEN = f"the status and claim of {_ITEM_ID} were not written."
_NOTHING_WRITTEN = f"nothing was written to {_ITEM_ID}."
_CONNECTION = {
    "tenant": "livespec-impl-beads",
    "prefix": "bd-ib",
    "server_user": "livespec-impl-beads",
    "database": "livespec-impl-beads",
    "bd_path": "bd",
    "fake": True,
}


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    TRANSITION_OBSERVATIONS.clear()
    yield
    TRANSITION_OBSERVATIONS.clear()
    reset_fake_singleton()


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A repository with a readable spec tree, cut over to claim tokens."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    block = {"connection": _CONNECTION, "dispatcher": {"claim_tokens": True}}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="backlog",
        title="A slice whose claim transition was left unapplied",
        description=(
            "Do the thing.\n\n## Definition of Done\n\n"
            f"- The dispatched slice lands its change.\n\nReferences: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-06T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )


def _seed() -> FakeBeadsClient:
    """File the `backlog` item through a descriptor naming no repository, naming an open token."""
    append_work_item(path=_config(), item=_item())
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    _name(client=client, token=create_claim_token(client=client))
    return client


def _name(*, client: FakeBeadsClient, token: str) -> None:
    metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
    metadata[CLAIM_TOKEN_METADATA_KEY] = token
    client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)


def _named(*, client: FakeBeadsClient) -> str:
    return client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]


def _stranded_successor(*, client: FakeBeadsClient) -> str:
    """The successor the item's closed current token was won with."""
    reason = client.show_issue(issue_id=_named(client=client))["close_reason"]
    return json.loads(reason)["successor"]


def _stored_status() -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID].status


def _move_to_ready(*, repo: Path) -> dict[str, object]:
    """One operator press of the `move` valve, through the surface an operator uses."""
    return run_action(
        repo=repo,
        action_id=f"move:{_ITEM_ID}:ready",
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
    )


def _strand_a_transition(
    *, client: FakeBeadsClient, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `move` press wins the item's current token, and its item write then fails."""
    real = client.update_issue

    def _failing_on_the_item(**fields: object) -> None:
        if fields["issue_id"] == _ITEM_ID:
            raise BeadsCommandError(command="bd update", exit_code=1, stderr="server gone")
        real(**fields)

    with monkeypatch.context() as patched:
        patched.setattr(client, "update_issue", _failing_on_the_item)
        with pytest.raises(BeadsCommandError):
            _ = _move_to_ready(repo=repo)


@dataclass(kw_only=True)
class _Stranding:
    """A clock a case owns, whose one sleep is when the item is stranded a second time.

    During the sleep the first winner's item write lands after all, and another
    writer wins the successor it named and fails in its turn. The sleep also
    ages this process's recorded sightings by the time slept, which is all a
    real sleep does to what the protocol measures.
    """

    client: FakeBeadsClient
    repo: Path
    monkeypatch: pytest.MonkeyPatch
    now: float = 0.0
    slept: list[float] = field(default_factory=list)

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        for observation in TRANSITION_OBSERVATIONS:
            TRANSITION_OBSERVATIONS[observation] -= seconds
        _name(client=self.client, token=_stranded_successor(client=self.client))
        _strand_a_transition(client=self.client, repo=self.repo, monkeypatch=self.monkeypatch)


def _stranded_twice(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, _Stranding]:
    """A cut-over repository whose item names a closed token, and the wait that re-strands it."""
    repo = _repo(tmp_path=tmp_path)
    client = _seed()
    _strand_a_transition(client=client, repo=repo, monkeypatch=monkeypatch)
    clock = _Stranding(client=client, repo=repo, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        writes, "TakeoverWait", lambda: TakeoverWait(clock=clock.clock, sleep=clock.sleep)
    )
    return repo, clock


def test_a_valve_press_refused_as_still_pending_names_the_dispatcher_pass_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1: the press waited, wrote once more, and says how the item gets written."""
    repo, clock = _stranded_twice(tmp_path=tmp_path, monkeypatch=monkeypatch)

    result = _move_to_ready(repo=repo)

    assert (result["status"], result["domain_error"]) == ("failed", _PENDING)
    assert clock.slept == [180.0]
    assert _stored_status() == "backlog"
    assert result["summary"] == (
        f"move refused: the claim-token protocol reported {_PENDING}, after this press "
        f"waited out the takeover wait and tried once more; {_NOTHING_WRITTEN} {_REMEDY}"
    )


def test_an_intake_call_refused_as_still_pending_names_the_same_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2: the refusal intake answers with reads as a message, and carries the remedy."""
    repo, clock = _stranded_twice(tmp_path=tmp_path, monkeypatch=monkeypatch)
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=False,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )

    result = apply_intake_dor(path=_config(repo_root=repo), item_id=_ITEM_ID, checklist=checklist)

    assert not is_successful(result)
    refused = unsafe_perform_io(result.failure())
    assert clock.slept == [180.0]
    assert _stored_status() == "backlog"
    assert str(refused) == (
        f"intake (route:backlog) refused: the claim-token protocol reported {_PENDING}, after "
        f"this call waited out the takeover wait and tried once more; {_NOT_WRITTEN} {_REMEDY}"
    )


def test_a_pending_refusal_after_a_side_effect_still_says_what_stands_before_the_remedy() -> None:
    """A valve that acted before its write keeps that sentence; the remedy follows it."""
    refusal = valve_claim_refusal(
        aid=f"resolve-blocked:{_ITEM_ID}:ready",
        wid=_ITEM_ID,
        verb="resolve-blocked",
        outcome=_PENDING,
        already_done="the answer was already written to the item",
    )

    assert refusal["domain_error"] == _PENDING
    assert refusal["summary"] == (
        f"resolve-blocked refused: the claim-token protocol reported {_PENDING}, after this "
        "press waited out the takeover wait and tried once more; the answer was already "
        f"written to the item; {_NOT_WRITTEN} {_REMEDY}"
    )


@pytest.mark.parametrize("outcome", [_LOST, "claim-token-missing", "claim-tokens-unreadable"])
def test_a_refusal_that_is_not_pending_reads_as_a_message_and_names_no_remedy(
    outcome: str,
) -> None:
    """Only an unapplied transition has a Dispatcher pass to wait for."""
    intake = ClaimWrite(
        path=_config(),
        item_id=_ITEM_ID,
        writer=WRITER_INTAKE,
        intent="route:ready",
        still_as_decided=resting_at(status="backlog"),
    ).refused(outcome=outcome)
    valve = valve_claim_refusal(
        aid=f"move:{_ITEM_ID}:ready", wid=_ITEM_ID, verb="move", outcome=outcome
    )

    assert str(intake) == (
        f"intake (route:ready) refused: the claim-token protocol reported {outcome}; "
        f"{_NOT_WRITTEN}"
    )
    assert valve["summary"] == (
        f"move refused: the claim-token protocol reported {outcome}; {_NOTHING_WRITTEN}"
    )

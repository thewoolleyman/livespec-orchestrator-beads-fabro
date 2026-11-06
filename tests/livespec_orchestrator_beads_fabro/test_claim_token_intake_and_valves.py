"""Intake and the human valves under the claim-token cutover.

`SPECIFICATION/contracts.md` ("Claim tokens") names intake and a human valve
among the writers of a dispatch claim: while the committed key
`dispatcher.claim_tokens` is `true`, each may change an item's status only
after winning the item's current token, and "a writer that does not win MUST
write nothing to the item, MUST discard S, and MUST report `claim-changed`".
Scenario 263 adds the race: "intake and a move valve both try to move it to
ready ... exactly one of them wins T and writes the item".

Every case drives a public entry point against the in-memory tenant:
`drive.run_action`, the operator surface, for the valves, and `apply_intake_dor`
for intake. The valves are the five the human-valve router dispatches and the
`driver-dispatch` door, which is routed beside it and moves a `ready` item to
`active`.

HOW A LOST TOKEN IS MADE. A writer reads the item's current token, mints its
successor, and only then closes the token. The cases below step in at that
close. `_lose_the_token` has an unnamed writer close the token first.
`_race` runs a REAL second writer to completion at that instant, so both
writers have read the same open token, which is the race the scenario names.

THE TWO WRITERS NEED NOT OVERLAP. A writer can decide on a read of the item,
and write only after another writer has finished. The token alone does not stop
it: it reads the token afresh and would win the successor the first writer
named. What stops it is the fact its decision rested on, the status it read,
which no longer holds. The two sequential cases bind that: the second writer
reports `claim-changed`, writes nothing, and the item still names the first
writer's successor, still open.

WHY THE ITEM IS SEEDED THROUGH A DESCRIPTOR WITH NO REPOSITORY. The store names
a first token itself on an item created in a cut-over repository. Seeding
through a descriptor that names no repository keeps the token each case
contests the one the case minted.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import intake_dor
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    TRANSITION_OBSERVATIONS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_policy_valves import move_item
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_item_comments,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

_ITEM_ID = "bd-ib-claimvalve"
_HEADING = "## Effective acceptance criteria"
_ANOTHER_WRITER = "another writer won this token"
_JUDGEMENT_MARKER = "dod-judgement:recorded"
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


def _repo(*, tmp_path: Path, claim_tokens: object = True) -> Path:
    """A repository with a readable spec tree and the given committed key."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    block = {"connection": _CONNECTION, "dispatcher": {"claim_tokens": claim_tokens}}
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": block}), encoding="utf-8"
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="backlog",
        title="A slice two writers want to move",
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
    return replace(base, **overrides)


def _seed(*, item: WorkItem, name_a_token: bool = True) -> tuple[FakeBeadsClient, str]:
    """File the item and, unless told otherwise, have it name a fresh open token."""
    append_work_item(path=_config(), item=item)
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    token = create_claim_token(client=client)
    if name_a_token:
        metadata = dict(client.show_issue(issue_id=_ITEM_ID)["metadata"])
        metadata[CLAIM_TOKEN_METADATA_KEY] = token
        client.update_issue(issue_id=_ITEM_ID, metadata=metadata, names_claim_token=True)
    return client, token


def _snapshot(*, client: FakeBeadsClient) -> dict[str, object]:
    """The item's whole record, less the marker a pre-admission judgement leaves.

    `approve` records that the Definition-of-Done judgement ran before it
    reaches its transition, whoever then wins the token. That marker is a label
    and changes no status, assignee or run stamp, so it is not a claim-changing
    write and a refused valve has still left it.
    """
    record = copy.deepcopy(client.show_issue(issue_id=_ITEM_ID))
    record["labels"] = [label for label in record["labels"] if label != _JUDGEMENT_MARKER]
    return record


def _won(*, client: FakeBeadsClient, token: str) -> dict[str, str]:
    """The recorded close reason of a token that a claim writer closed."""
    record = client.show_issue(issue_id=token)
    assert record["status"] == "closed", "no writer contested the item's current token"
    return json.loads(record["close_reason"])


def _status_writes(*, client: FakeBeadsClient, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every write that carries a status to the item, in the order it was sent."""
    real = client.update_issue
    sent: list[str] = []

    def _spy(**fields: object) -> None:
        if fields["issue_id"] == _ITEM_ID and fields.get("status") is not None:
            sent.append(str(fields["status"]))
        real(**fields)

    monkeypatch.setattr(client, "update_issue", _spy)
    return sent


def _lose_the_token(
    *, client: FakeBeadsClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    close = client.close_issue_without_verdict

    def _raced(*, issue_id: str, reason: str) -> None:
        if issue_id == token:
            close(issue_id=issue_id, reason=_ANOTHER_WRITER)
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _raced)


def _race(
    *,
    client: FakeBeadsClient,
    token: str,
    rival: Callable[[], object],
    monkeypatch: pytest.MonkeyPatch,
) -> list[object]:
    """Run `rival` to completion at the instant the first writer closes `token`."""
    close = client.close_issue_without_verdict
    finished: list[object] = []
    started: list[str] = []

    def _closing(*, issue_id: str, reason: str) -> None:
        if issue_id == token and not started:
            started.append(issue_id)
            finished.append(rival())
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _closing)
    return finished


def _press(*, repo: Path, action_id: str) -> dict[str, object]:
    """One operator press of a valve, through the surface an operator uses."""
    return run_action(
        repo=repo,
        action_id=action_id,
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
    )


def _checklist(**gates: bool) -> DefinitionOfReadyChecklist:
    passing = {
        "single_coherent_done": True,
        "autonomously_verifiable": True,
        "autonomy_tiered": True,
        "dependency_linked": True,
        "repo_targeted": True,
        "above_floor": True,
    }
    return DefinitionOfReadyChecklist(**(passing | gates))


def _intake(*, repo: Path, **gates: bool) -> object:
    return apply_intake_dor(
        path=_config(repo_root=repo), item_id=_ITEM_ID, checklist=_checklist(**gates)
    )


@dataclass(frozen=True, kw_only=True)
class _Valve:
    """One valve press: the item it is pressed on and where the item should land."""

    action_id: str
    intent: str
    lands_on: str
    status: str
    blocked_reason: str | None = None
    factory_safety: str | None = None

    def seed(self) -> tuple[FakeBeadsClient, str]:
        return _seed(
            item=_item(
                status=self.status,
                blocked_reason=self.blocked_reason,
                factory_safety=self.factory_safety,
            )
        )


_VALVES = [
    _Valve(
        action_id=f"approve:{_ITEM_ID}",
        intent="approve",
        lands_on="ready",
        status="pending-approval",
    ),
    _Valve(action_id=f"accept:{_ITEM_ID}", intent="accept", lands_on="closed", status="acceptance"),
    _Valve(
        action_id=f"reject:{_ITEM_ID}:rework",
        intent="reject:rework",
        lands_on="active",
        status="acceptance",
    ),
    _Valve(
        action_id=f"move:{_ITEM_ID}:ready", intent="move:ready", lands_on="ready", status="backlog"
    ),
    _Valve(
        action_id=f"resolve-blocked:{_ITEM_ID}:ready",
        intent="resolve-blocked:ready",
        lands_on="ready",
        status="blocked",
        blocked_reason="needs-human",
    ),
    _Valve(
        action_id=f"driver-dispatch:{_ITEM_ID}",
        intent="driver-dispatch",
        lands_on="active",
        status="ready",
        factory_safety="mutates-host-machinery",
    ),
]
_VALVE_IDS = [valve.intent for valve in _VALVES]


@pytest.mark.parametrize("valve", _VALVES, ids=_VALVE_IDS)
def test_a_valve_writes_the_item_only_after_winning_its_current_token(
    valve: _Valve, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2, the winning half: one write, made under the won token."""
    repo = _repo(tmp_path=tmp_path)
    client, token = valve.seed()
    writes = _status_writes(client=client, monkeypatch=monkeypatch)

    result = _press(repo=repo, action_id=valve.action_id)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert result["status"] == "green"
    assert (won["writer"], won["intent"]) == ("human-valve", valve.intent)
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == valve.lands_on
    assert writes == [valve.lands_on]


@pytest.mark.parametrize("valve", _VALVES, ids=_VALVE_IDS)
def test_a_valve_that_loses_its_token_reports_claim_changed_and_writes_nothing(
    valve: _Valve, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 2, the losing half."""
    repo = _repo(tmp_path=tmp_path)
    client, token = valve.seed()
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = _press(repo=repo, action_id=valve.action_id)

    assert result["status"] == "failed"
    assert result["domain_error"] == "claim-changed"
    assert _snapshot(client=client) == before
    assert client.show_issue(issue_id=token)["close_reason"] == _ANOTHER_WRITER


@pytest.mark.parametrize("valve", _VALVES, ids=_VALVE_IDS)
def test_a_valve_writes_as_it_always_did_while_the_key_is_false(
    valve: _Valve, tmp_path: Path
) -> None:
    """Before the cutover no token is read, closed or named."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    client, token = valve.seed()

    result = _press(repo=repo, action_id=valve.action_id)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert result["status"] == "green"
    assert record["status"] == valve.lands_on
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert client.show_issue(issue_id=token)["status"] != "closed"


@pytest.mark.parametrize(
    ("claim_tokens", "name_a_token", "outcome"),
    [(True, False, "claim-token-missing"), ("yes", True, "claim-tokens-unreadable")],
)
def test_a_valve_that_cannot_contest_a_token_refuses_and_does_not_write_blind(
    *, claim_tokens: object, name_a_token: bool, outcome: str, tmp_path: Path
) -> None:
    """An item naming no token, and a key this host cannot read, each refuse."""
    repo = _repo(tmp_path=tmp_path, claim_tokens=claim_tokens)
    client, _ = _seed(item=_item(), name_a_token=name_a_token)
    before = _snapshot(client=client)

    result = _press(repo=repo, action_id=f"move:{_ITEM_ID}:ready")

    assert result["status"] == "failed"
    assert result["domain_error"] == outcome
    assert _snapshot(client=client) == before


@pytest.mark.parametrize(
    ("gates", "routed", "label"),
    [
        ({}, "ready", "intake:triaged"),
        ({"autonomously_verifiable": False}, "blocked", "blocked-reason:needs-human"),
        ({"single_coherent_done": False}, "backlog", "intake:triaged"),
    ],
)
def test_intake_routes_an_item_only_after_winning_its_current_token(
    gates: dict[str, bool],
    routed: str,
    label: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD 1, the winning half: the routing write is made under the won token."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item(status="pending-approval"))
    writes = _status_writes(client=client, monkeypatch=monkeypatch)

    result = _intake(repo=repo, **gates)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert unsafe_perform_io(result.unwrap()) == routed
    assert (won["writer"], won["intent"]) == ("intake", f"route:{routed}")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert record["status"] == routed
    assert label in record["labels"]
    assert writes == [routed]


def test_intake_that_loses_its_token_routes_nothing_and_records_no_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 1, the losing half, on an item whose finding a routed intake would record."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item(description="Just prose, no section at all."))
    before = _snapshot(client=client)
    _lose_the_token(client=client, token=token, monkeypatch=monkeypatch)

    result = _intake(repo=repo)

    assert not is_successful(result)
    refused = unsafe_perform_io(result.failure())
    assert (refused.writer, refused.outcome) == ("intake", "claim-changed")
    assert _snapshot(client=client) == before
    assert not [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM_ID)
        if comment.text.startswith("definition-of-done finding")
    ]


def test_a_capture_filed_after_the_cutover_is_routed_under_the_token_the_store_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store names a first token on the item it creates, and intake wins that one.

    A capture filed in a cut-over repository is therefore routed, and is never
    refused as `claim-token-missing` for want of a migration pass.
    """
    repo = _repo(tmp_path=tmp_path)
    client = make_beads_client(config=_config())
    close = client.close_issue_without_verdict
    closed: list[tuple[str, str]] = []

    def _closing(*, issue_id: str, reason: str) -> None:
        closed.append((issue_id, json.loads(reason)["writer"]))
        close(issue_id=issue_id, reason=reason)

    monkeypatch.setattr(client, "close_issue_without_verdict", _closing)

    result = file_captured_work_item(
        path=_config(repo_root=repo), item=_item(), checklist=_checklist()
    )

    record = client.show_issue(issue_id=_ITEM_ID)
    assert is_successful(result), "intake refused the item it had just filed"
    assert unsafe_perform_io(result.unwrap()) == "ready"
    assert (record["status"], "intake:triaged" in record["labels"]) == ("ready", True)
    assert [writer for _, writer in closed] == ["intake"]
    assert (
        _won(client=client, token=closed[0][0])["successor"]
        == (record["metadata"][CLAIM_TOKEN_METADATA_KEY])
    )


def test_intake_routes_as_it_always_did_while_the_key_is_false(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path, claim_tokens=False)
    client, token = _seed(item=_item())

    result = _intake(repo=repo)

    record = client.show_issue(issue_id=_ITEM_ID)
    assert unsafe_perform_io(result.unwrap()) == "ready"
    assert record["status"] == "ready"
    assert record["metadata"][CLAIM_TOKEN_METADATA_KEY] == token
    assert client.show_issue(issue_id=token)["status"] != "closed"


def _row_after(
    *,
    seed: Callable[[], tuple[FakeBeadsClient, str]],
    press: Callable[[Path], object],
    tmp_path: Path,
    claim_tokens: bool,
) -> dict[str, object]:
    """The row one write leaves in a fresh tenant, less what only a token or a clock decides."""
    reset_fake_singleton()
    client, _ = seed()
    _ = press(_repo(tmp_path=tmp_path / f"claim-tokens-{claim_tokens}", claim_tokens=claim_tokens))
    row = _snapshot(client=client)
    metadata = dict(row["metadata"])
    del metadata[CLAIM_TOKEN_METADATA_KEY]
    if "ready_since" in metadata:
        metadata["ready_since"] = "the instant it became ready"
    return row | {"metadata": metadata}


@pytest.mark.parametrize("valve", _VALVES, ids=_VALVE_IDS)
def test_a_guarded_valve_write_leaves_the_row_the_unguarded_write_leaves(
    valve: _Valve, tmp_path: Path
) -> None:
    """The token is the only difference the cutover makes to what a valve writes."""
    rows = [
        _row_after(
            seed=valve.seed,
            press=lambda repo: _press(repo=repo, action_id=valve.action_id),
            tmp_path=tmp_path,
            claim_tokens=claim_tokens,
        )
        for claim_tokens in (True, False)
    ]

    assert rows[0] == rows[1]
    assert rows[0]["status"] == valve.lands_on


@pytest.mark.parametrize(
    "gates", [{}, {"autonomously_verifiable": False}, {"single_coherent_done": False}]
)
def test_a_guarded_intake_route_leaves_the_row_the_unguarded_route_leaves(
    gates: dict[str, bool], tmp_path: Path
) -> None:
    rows = [
        _row_after(
            seed=lambda: _seed(item=_item(status="pending-approval")),
            press=lambda repo: _intake(repo=repo, **gates),
            tmp_path=tmp_path,
            claim_tokens=claim_tokens,
        )
        for claim_tokens in (True, False)
    ]

    assert rows[0] == rows[1]
    assert "intake:triaged" in rows[0]["labels"]


def _move_to_ready(*, repo: Path) -> object:
    return _press(repo=repo, action_id=f"move:{_ITEM_ID}:ready")


def test_the_move_valve_wins_the_race_to_ready_and_intake_stands_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: both read the backlog item's open token, and the valve closes it first."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item())
    writes = _status_writes(client=client, monkeypatch=monkeypatch)
    moved = _race(
        client=client, token=token, rival=lambda: _move_to_ready(repo=repo), monkeypatch=monkeypatch
    )

    routed = _intake(repo=repo)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert [result["status"] for result in moved] == ["green"]
    assert not is_successful(routed)
    assert unsafe_perform_io(routed.failure()).outcome == "claim-changed"
    assert (won["writer"], won["intent"]) == ("human-valve", "move:ready")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert writes == ["ready"]


def test_intake_wins_the_race_to_ready_and_the_move_valve_stands_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3, the other way round: intake closes the shared token first."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item())
    writes = _status_writes(client=client, monkeypatch=monkeypatch)
    routed = _race(
        client=client, token=token, rival=lambda: _intake(repo=repo), monkeypatch=monkeypatch
    )

    moved = _move_to_ready(repo=repo)

    won = _won(client=client, token=token)
    record = client.show_issue(issue_id=_ITEM_ID)
    assert [unsafe_perform_io(result.unwrap()) for result in routed] == ["ready"]
    assert (moved["status"], moved["domain_error"]) == ("failed", "claim-changed")
    assert (won["writer"], won["intent"]) == ("intake", "route:ready")
    assert won["successor"] == record["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert writes == ["ready"]


def _first_writer_stands(*, client: FakeBeadsClient, token: str) -> dict[str, str]:
    """The reason the first writer won `token` with, its successor still named and open."""
    won = _won(client=client, token=token)
    named = client.show_issue(issue_id=_ITEM_ID)["metadata"][CLAIM_TOKEN_METADATA_KEY]
    assert won["successor"] == named
    assert client.show_issue(issue_id=named)["status"] != "closed"
    return won


def test_a_move_decided_before_intake_finished_writes_nothing_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3, sequential: the valve read the backlog item, intake routed it, then the valve wrote."""
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item())
    writes = _status_writes(client=client, monkeypatch=monkeypatch)
    as_the_valve_read_it = materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]
    routed = _intake(repo=repo)

    moved = move_item(
        config=_config(repo_root=repo),
        item=as_the_valve_read_it,
        aid=f"move:{_ITEM_ID}:ready",
        target_status="ready",
    )

    won = _first_writer_stands(client=client, token=token)
    assert unsafe_perform_io(routed.unwrap()) == "ready"
    assert (moved["status"], moved["domain_error"]) == ("failed", "claim-changed")
    assert (won["writer"], won["intent"]) == ("intake", "route:ready")
    assert writes == ["ready"]


def test_intake_decided_before_a_move_finished_routes_nothing_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3, sequential, the other way round: intake read the item, then the valve moved it.

    Intake grades its findings after it has read the item and before it
    writes, so the valve is run to completion from there.
    """
    repo = _repo(tmp_path=tmp_path)
    client, token = _seed(item=_item())
    writes = _status_writes(client=client, monkeypatch=monkeypatch)
    grade = intake_dor.filing_findings
    moved: list[object] = []

    def _move_then_grade(**graded: object) -> object:
        moved.append(_move_to_ready(repo=repo))
        return grade(**graded)

    monkeypatch.setattr(intake_dor, "filing_findings", _move_then_grade)

    routed = _intake(repo=repo)

    assert not is_successful(routed)
    assert unsafe_perform_io(routed.failure()).outcome == "claim-changed"
    won = _first_writer_stands(client=client, token=token)
    assert [result["status"] for result in moved] == ["green"]
    assert (won["writer"], won["intent"]) == ("human-valve", "move:ready")
    assert writes == ["ready"]

"""Scenario 147 — the first budget survives every sanctioned pointer rewrite.

`contracts.md` section "Required result, budget and progress epoch": "Routine
handoffs, supervisor handoffs and direct set_next_action calls MUST NOT reset
the deadline or count", and "While a known-unsatisfied obligation has budget
remaining, an accepted handoff consumes one handoff unit; direct pointer writes
consume none but cannot reset either limit."

THE HAZARD IS THAT THE BUDGET USED TO LIVE WHERE THE WRITER COULD REACH IT. The
pointer is one metadata object rewritten wholesale on every write, so a caller
handing a later deadline simply got one — and nothing in the result distinguished
a preserved obligation from a silently extended one, because the pointer a resume
then read was perfectly well-formed either way. The durable authority therefore
has to be the epoch chain, which no writer can hand a value to without committing
a transition the server serializes.

EVERY CASE HERE HANDS A LATER DEADLINE AND A LARGER max_handoffs. That is what
makes the assertions discriminating: a writer that merely stored what it was
given would pass a test whose fixtures asked for the original values, so the
fixtures ask for different ones and the assertions demand the originals back.

The required result is an `item_status` target naming a ledger item that stands
at `ready` while the obligation expects `done`, so the result is genuinely
UNSATISFIED through the ordinary reader on every call, with no stub and no
double — which is the state the whole clause is about.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_handoff import (
    append_handoff,
    append_supervisor_handoff,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_METADATA_KEY,
    NextAction,
    plan_record_metadata,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relaybudget"
_TARGET_ID = "bd-ib-budgettarget"
_ORIGINAL_DEADLINE = "2026-10-20T09:00:00Z"
_LATER_DEADLINE = "2099-01-01T00:00:00Z"
_ORIGINAL_MAX = 5
_LARGER_MAX = 99
_NOW = "2026-10-13T09:00:00Z"


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Bind every case to the in-memory tenant.

    There is no shared conftest at this tier, so this file owns its backend
    isolation. The singleton is reset BOTH before and after, because these cases
    seed the same epic and token ids and the accumulation within one invocation
    is exactly what the chain relies on.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _project(*, tmp_path: Path) -> Path:
    """A project root whose directory name is the canonical repository identity."""
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _fake(*, config: StoreConfig) -> FakeBeadsClient:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _required_result() -> dict[str, object]:
    """A target the seeded fixtures demonstrably do NOT meet."""
    return {
        "repo": _PROJECT_NAME,
        "item_status": {"item_id": _TARGET_ID, "status": "done"},
    }


def _action(*, deadline: str, max_handoffs: int, text: str = "Keep going.") -> NextAction:
    return NextAction(
        kind="impl",
        ref=_TARGET_ID,
        text=text,
        required_result=_required_result(),
        budget={"deadline": deadline, "max_handoffs": max_handoffs},
    )


def _seed(*, tmp_path: Path) -> tuple[Path, StoreConfig]:
    """A plan epic holding a genesis chain, beside the unmet target item."""
    reset_fake_singleton()
    repo = _project(tmp_path=tmp_path)
    config = store_config(repo=repo)
    fake = _fake(config=config)
    for issue_id, status in ((_EPIC_ID, "active"), (_TARGET_ID, "ready")):
        _ = fake.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type="epic" if issue_id == _EPIC_ID else "feature",
                title=issue_id,
                description="Definition of Done\n\n- A thing holds.",
                assignee=None,
                created_at="2026-10-13T08:00:00Z",
                metadata={"rank": "a0"},
            )
        )
        fake.update_issue(issue_id=issue_id, status=status)
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC_ID,
        metadata=chain_cache_metadata(
            existing_metadata={"rank": "a0"},
            latest_closed=None,
            current=genesis,
        ),
    )
    return repo, config


def _head(*, config: StoreConfig) -> ChainHead:
    head = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(head, ChainHead), head
    return head


def _establish(*, config: StoreConfig) -> None:
    """The first sanctioned write, which is what sets the original budget."""
    refusal = set_next_action(
        config=config,
        epic_id=_EPIC_ID,
        action=_action(deadline=_ORIGINAL_DEADLINE, max_handoffs=_ORIGINAL_MAX),
        session="relay-session",
        now=_NOW,
    )
    assert refusal is None, refusal


def test_the_first_write_records_the_original_budget_as_durable_authority(
    tmp_path: Path,
) -> None:
    """Until the chain carries it, nothing has preserved anything.

    This is the positive control for every case below: if the establishing
    write did not durably record the deadline and the ceiling, a later
    assertion that they are "unchanged" would hold trivially over two absent
    values.
    """
    _, config = _seed(tmp_path=tmp_path)

    _establish(config=config)

    authority = _head(config=config).authority
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == _ORIGINAL_MAX
    assert authority.consumed_handoffs == 0


def test_an_accepted_handoff_consumes_one_unit_and_moves_neither_limit(
    tmp_path: Path,
) -> None:
    """A handoff is the one write that spends budget, and it spends exactly one."""
    _, config = _seed(tmp_path=tmp_path)
    _establish(config=config)

    refusal = append_handoff(
        config=config,
        epic_id=_EPIC_ID,
        body="Progress, but the target is not met.",
        author="relay-session",
        now=_NOW,
        next_action=_action(deadline=_LATER_DEADLINE, max_handoffs=_LARGER_MAX),
    )

    assert refusal is None, refusal
    authority = _head(config=config).authority
    assert authority.consumed_handoffs == 1
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == _ORIGINAL_MAX


def test_a_supervisor_handoff_consumes_a_unit_and_moves_neither_limit(
    tmp_path: Path,
) -> None:
    """The supervisor writer is sanctioned too, so it is bound by the same budget."""
    _, config = _seed(tmp_path=tmp_path)
    _establish(config=config)

    refusal = append_supervisor_handoff(
        config=config,
        epic_id=_EPIC_ID,
        slug="relay-delivery-and-progress-deadline",
        body="Supervisor review; the target is still not met.",
        now=_NOW,
        next_action=_action(deadline=_LATER_DEADLINE, max_handoffs=_LARGER_MAX),
    )

    assert refusal is None, refusal
    authority = _head(config=config).authority
    assert authority.consumed_handoffs == 1
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == _ORIGINAL_MAX


def test_a_direct_pointer_write_consumes_no_unit_and_moves_neither_limit(
    tmp_path: Path,
) -> None:
    """Rewording the pointer is activity, not progress, so it spends nothing.

    The candidate also asks for a later deadline and a larger ceiling, which is
    the cosmetic-rewrite-as-extension shape the clause names explicitly.
    """
    _, config = _seed(tmp_path=tmp_path)
    _establish(config=config)

    refusal = set_next_action(
        config=config,
        epic_id=_EPIC_ID,
        action=_action(
            deadline=_LATER_DEADLINE,
            max_handoffs=_LARGER_MAX,
            text="Keep going, but worded differently.",
        ),
        session="relay-session",
        now=_NOW,
    )

    assert refusal is None, refusal
    authority = _head(config=config).authority
    assert authority.consumed_handoffs == 0
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == _ORIGINAL_MAX


def test_repeated_mixed_writes_accumulate_only_their_handoff_units(
    tmp_path: Path,
) -> None:
    """The whole sequence the scenario describes, run end to end.

    Two ordinary handoffs, one supervisor handoff and two direct pointer writes,
    every one of them asking for a later deadline and a larger ceiling. Three
    units are owed and neither limit may move.
    """
    _, config = _seed(tmp_path=tmp_path)
    _establish(config=config)
    extended = _action(deadline=_LATER_DEADLINE, max_handoffs=_LARGER_MAX)

    for index in range(2):
        assert (
            append_handoff(
                config=config,
                epic_id=_EPIC_ID,
                body=f"Handoff {index}; target still unmet.",
                author="relay-session",
                now=_NOW,
                next_action=extended,
            )
            is None
        )
    assert (
        append_supervisor_handoff(
            config=config,
            epic_id=_EPIC_ID,
            slug="relay-delivery-and-progress-deadline",
            body="Supervisor handoff; target still unmet.",
            now=_NOW,
            next_action=extended,
        )
        is None
    )
    for index in range(2):
        assert (
            set_next_action(
                config=config,
                epic_id=_EPIC_ID,
                action=_action(
                    deadline=_LATER_DEADLINE,
                    max_handoffs=_LARGER_MAX,
                    text=f"Reworded {index}.",
                ),
                session="relay-session",
                now=_NOW,
            )
            is None
        )

    authority = _head(config=config).authority
    assert authority.consumed_handoffs == 3
    assert authority.original_deadline == _ORIGINAL_DEADLINE
    assert authority.max_handoffs == _ORIGINAL_MAX


def test_the_persisted_pointer_projects_the_original_budget_not_the_candidate(
    tmp_path: Path,
) -> None:
    """The pointer is a PROJECTION, so a resume reading it sees the original.

    Asserting only the chain would leave the surface every consumer actually
    reads free to carry the extension the chain refused.
    """
    _, config = _seed(tmp_path=tmp_path)
    _establish(config=config)

    assert (
        append_handoff(
            config=config,
            epic_id=_EPIC_ID,
            body="One handoff.",
            author="relay-session",
            now=_NOW,
            next_action=_action(deadline=_LATER_DEADLINE, max_handoffs=_LARGER_MAX),
        )
        is None
    )

    record = _fake(config=config).show_issue(issue_id=_EPIC_ID)
    pointer = plan_record_metadata(record=record)[NEXT_ACTION_METADATA_KEY]
    assert isinstance(pointer, dict)
    budget = pointer["budget"]
    assert isinstance(budget, dict)
    assert budget["deadline"] == _ORIGINAL_DEADLINE
    assert budget["max_handoffs"] == _ORIGINAL_MAX
    assert budget["handoff_count"] == 1

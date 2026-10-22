"""A RETAINED misderived obligation stays supersedable.

`bd-ib-4hznqp`, the half of Scenario 211 the first build could not reach. A
misderived plan-level obligation is only supersedable while NO sanctioned write
has happened since it was derived: `validate_causal_supersession` requires the
supersession to name the chain's current epoch, and the evidence reader then
required the deriving operation's own transition to sit at that same epoch — so
one retaining write made the obligation permanently unsupersedable.

Measured 2026-10-22 on plan epic `bd-ib-fyozyd`. The plan-resume actor wrote the
derived obligation in operation `plan-write-6a4ff4449997b98c` (epoch 99 -> 100)
while nine ordinal-6 carriers were open; a human pointer written nine minutes
later retained that obligation and advanced the chain to epoch 101 — the very
fallback the derivation gate prescribes. Both supersessions were then refused:
naming epoch 101, "the deriving operation ... resolves to no transition recorded
at epoch 101"; naming epoch 100, "the supersession names previous epoch 100, but
the chain stands at epoch 101".

THE RETAINING WRITE IS A REAL `set_next_action` HUMAN POINTER, not a
hand-committed transition, because that is the write the incident turned on and
the one the derivation gate prescribes for an open carrier. The derivation itself
IS hand-committed, because a derivation recorded while a mapped carrier was open
is the state the gate now prevents — so the only honest way to reach it is to
seed the ledger a pre-gate build left behind, which is exactly the population
this repair exists to unlock.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    CommittedTransition,
    TransitionRequest,
    commit_transition,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    chain_cache_metadata,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import create_token
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NextAction,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference
from livespec_orchestrator_beads_fabro.commands._plan_supersession import CausalSupersession
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-10-22T07:00:00Z"
# Later than every seeded transition, which is what makes "the carrier was open
# WHEN the derivation was recorded" a question about two instants rather than one.
_LATER = "2026-10-22T09:00:00Z"
_DESCRIPTION = "## Definition of Done\n\n- The plan reaches its archive.\n"
_DEADLINE = "2099-10-10T12:00:00Z"
_MAX_HANDOFFS = 4
_CONSUMED_HANDOFFS = 2
_EPIC = "bd-ib-plan"
_OWN = "repo"
_OWN_PREFIX = "bd-ib"
_CARRIER_REPO = "carrier-repo"
_CARRIER_PREFIX = "cr"
_OPEN_CARRIER = f"{_CARRIER_PREFIX}-open"
_DERIVING_OPERATION = "op-derived-while-the-carrier-was-open"
_PLAN_RESUME_ACTOR = "plan-resume"
_SESSION = "plan-session"
# The obligation the false derivation persisted: the plan's own proof record.
_SUPERSEDED_RESULT: dict[str, object] = {
    "repo": _OWN,
    "item_comment": {"item_id": _EPIC, "marker": PLAN_PROOF_RECORD_TITLE},
}
_CARRIER_RESULT: dict[str, object] = {
    "repo": _CARRIER_REPO,
    "item_status": {"item_id": _OPEN_CARRIER, "status": "closed"},
}


def _identity(*, required_result: dict[str, object]) -> str:
    """The canonical result identity, ASKED OF the production reference parse.

    Not transcribed: a literal written here would keep passing after the
    rendering had changed, which is a green that is no longer about anything.
    """
    parsed = parse_result_reference(value=required_result)
    assert isinstance(parsed, ResultReference), parsed
    return parsed.identity


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix=_OWN_PREFIX,
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        repo_root=repo,
        fake=True,
    )


def _fake(*, repo: Path) -> FakeBeadsClient:
    client = make_beads_client(config=_config(repo=repo))
    assert isinstance(client, FakeBeadsClient)
    return client


def _connection(*, prefix: str) -> dict[str, object]:
    return {"livespec-orchestrator-beads-fabro": {"connection": {"prefix": prefix}}}


def _project(*, tmp_path: Path) -> Path:
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix=_OWN_PREFIX))
    configured["cross_repo_targets"] = {
        _CARRIER_REPO: {"github_url": f"https://github.com/thewoolleyman/{_CARRIER_REPO}"}
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    carrier = tmp_path / _CARRIER_REPO
    carrier.mkdir()
    _ = (carrier / ".livespec.jsonc").write_text(
        json.dumps(_connection(prefix=_CARRIER_PREFIX)), encoding="utf-8"
    )
    return repo


def _open_carrier(*, repo: Path) -> None:
    _ = _fake(repo=repo).create_issue(
        draft=IssueDraft(
            issue_id=_OPEN_CARRIER,
            issue_type="task",
            title=_OPEN_CARRIER,
            description="a carrier of one plan assertion, in a sibling tenant",
            assignee=None,
            created_at=_NOW,
        )
    )


def _derived_pointer() -> dict[str, object]:
    return {
        "kind": "proof",
        "ref": f"capture:{_EPIC}",
        "text": f"Capture the plan Proof of Done record for {_EPIC}.",
        "required_result": _SUPERSEDED_RESULT,
        "budget": {
            "deadline": _DEADLINE,
            "max_handoffs": _MAX_HANDOFFS,
            "epoch": "1",
            "handoff_count": _CONSUMED_HANDOFFS,
        },
    }


def _seed(*, repo: Path, transitions: tuple[tuple[str, dict[str, object]], ...]) -> int:
    """An epic whose chain records one transition per named operation, in order.

    Every transition is recorded under the `plan-resume` actor, because the
    derivation condition is not what any case here is about: each case differs
    only in WHICH obligation each transition recorded. Returns the epoch the
    chain stands at, which is the epoch a supersession must name.
    """
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_EPIC,
            issue_type="epic",
            title=_EPIC,
            description=_DESCRIPTION,
            assignee=None,
            created_at=_NOW,
            metadata={
                "next_action": _derived_pointer(),
                "last_session": f"{_PLAN_RESUME_ACTOR} at {_NOW}",
            },
        )
    )
    genesis = create_token(client=fake)
    fake.update_issue(
        issue_id=_EPIC,
        metadata=chain_cache_metadata(
            existing_metadata=dict(fake.show_issue(issue_id=_EPIC)["metadata"]),
            latest_closed=None,
            current=genesis,
        ),
    )
    config = _config(repo=repo)
    epoch = 0
    for operation_id, required_result in transitions:
        head = read_chain_head(config=config, epic_id=_EPIC)
        assert isinstance(head, ChainHead), head
        committed = commit_transition(
            config=config,
            epic_id=_EPIC,
            request=TransitionRequest(
                operation_id=operation_id,
                observed_head=head,
                authority=AuthorityState(
                    required_result=required_result,
                    original_deadline=_DEADLINE,
                    max_handoffs=_MAX_HANDOFFS,
                    consumed_handoffs=_CONSUMED_HANDOFFS,
                ),
                event_kind="pointer",
                author=_PLAN_RESUME_ACTOR,
                now=_NOW,
            ),
        )
        assert isinstance(committed, CommittedTransition), committed
        epoch = committed.payload.new_epoch
    fake.add_comment(
        issue_id=_EPIC,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author=_SESSION,
            now=_NOW,
            body=f"carriers:\n- 1: {_OPEN_CARRIER}",
        ),
    )
    return epoch


def _replacement() -> NextAction:
    """The await the supersession replaces the falsely derived step with."""
    return NextAction(
        kind="await",
        ref=f"item:{_OPEN_CARRIER}",
        text=f"Wait for plan carrier {_OPEN_CARRIER} to close in {_CARRIER_REPO}.",
        required_result=_CARRIER_RESULT,
        budget={"deadline": _DEADLINE, "max_handoffs": _MAX_HANDOFFS},
    )


def _supersession(*, epoch: int, operation_id: str = _DERIVING_OPERATION) -> CausalSupersession:
    return CausalSupersession(
        superseded_result_identity=_identity(required_result=_SUPERSEDED_RESULT),
        previous_epoch=epoch,
        cause="misderived",
        deriving_operation_id=operation_id,
        open_carrier_id=_OPEN_CARRIER,
        writer=_SESSION,
    )


def _pointer(*, repo: Path) -> dict[str, object]:
    return dict(_fake(repo=repo).show_issue(issue_id=_EPIC)["metadata"]["next_action"])


def _chain_obligation(*, repo: Path) -> object:
    """The obligation the CHAIN holds, which is the authority the pointer projects."""
    head = read_chain_head(config=_config(repo=repo), epic_id=_EPIC)
    assert isinstance(head, ChainHead), head
    return head.authority.required_result


def test_an_obligation_retained_by_a_later_pointer_write_is_still_supersedable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The measured shape: a human pointer retained the obligation, so the chain moved.

    The supersession names the chain's CURRENT epoch — the only epoch
    `validate_causal_supersession` admits — together with the deriving operation
    identity, whose own transition sits one epoch back. Every other misderived
    condition holds: the derivation is the `plan-resume` actor, the carrier the
    epic's latest carrier-map event names was open when it was recorded, and it
    is open still.

    The deadline and the consumed handoff count are read off the PERSISTED
    pointer, because that is what the next resume grades its budget against: a
    build preserving the authority while projecting the candidate's own budget
    would hand the plan a fresh clock with every surface still reading correct.
    The replaced obligation is read off the CHAIN as well, because the pointer is
    a projection every writer rewrites wholesale while the chain is the authority
    the next write grades against.
    """
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _open_carrier(repo=repo)
    derived_epoch = _seed(repo=repo, transitions=((_DERIVING_OPERATION, _SUPERSEDED_RESULT),))

    retained = set_next_action(
        config=_config(repo=repo),
        epic_id=_EPIC,
        action=NextAction(
            kind="human",
            ref=f"open-carrier:{_OPEN_CARRIER}",
            text=f"Decide what to do about the open carrier {_OPEN_CARRIER}.",
            required_result=None,
            budget=None,
        ),
        session=_SESSION,
        now=_LATER,
    )
    assert retained is None, retained
    head = read_chain_head(config=_config(repo=repo), epic_id=_EPIC)
    assert isinstance(head, ChainHead), head
    assert head.epoch > derived_epoch
    assert _chain_obligation(repo=repo) == _SUPERSEDED_RESULT

    refusal = set_next_action(
        config=_config(repo=repo),
        epic_id=_EPIC,
        action=_replacement(),
        session=_SESSION,
        now=_LATER,
        supersession=_supersession(epoch=head.epoch),
    )

    assert refusal is None, refusal
    pointer = _pointer(repo=repo)
    assert pointer["kind"] == "await"
    assert pointer["required_result"] == _CARRIER_RESULT
    budget = cast("dict[str, object]", pointer["budget"])
    assert budget["deadline"] == _DEADLINE
    assert budget["handoff_count"] == _CONSUMED_HANDOFFS
    assert budget["max_handoffs"] == _MAX_HANDOFFS
    assert _chain_obligation(repo=repo) == _CARRIER_RESULT

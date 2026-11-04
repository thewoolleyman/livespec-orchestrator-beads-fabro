"""A `plan-level proof` carrier entry is discharged by the plan's own record.

`bd-ib-evrynu`, the third half of the carrier gate, bound through the production
`resume_directive`. The plan Definition-of-Done clause gives a carrier line two
forms: `- <ordinal>: <work-item-id>[, ...]`, and `- <ordinal>: plan-level proof`
for an assertion NO child carries — the literal the clause reserves for "the
plan's own Proof of Done record is what will discharge it".

WHY THE GATE MUST NOT TREAT IT AS A CARRIER. `plan-level proof` is not a
work-item id and never resolves to a tenant, so the gate's own unplaceable
reading reports it and the resume rests the plan on a `human` pointer — asking a
maintainer to configure the repository that mints an item called
`plan-level proof`, which no repository does and none ever will. Worse, the
assertion it marks is EXACTLY the one the proof leg exists to discharge, so the
gate would be holding the plan's proof step behind the plan's proof step.

WHY THIS IS A CARVE-OUT AT THE PARSE AND NOT A FILTER AT THE GATE. The entry is
not a carrier that happens to be unplaceable; it is the clause's way of saying
this assertion has NO work-item carrier. A reader that returned it and left the
gate to recognise it would make every later consumer of the carrier set
responsible for the same recognition, and the one that forgot would be the one
that stalled a plan.

WHY THE FIXTURE MIXES THE TWO FORMS. An epic whose map named only
`plan-level proof` would pass against a reader that dropped the whole block, and
one naming only work-item carriers says nothing about the literal. So the map
below carries both, and the assertions are a pair: the open work-item carrier is
still waited on, and the plan-level entry contributes nothing.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import PLAN_LEVEL_PROOF
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
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_SCOPE_PREFIX,
    plan_comment_body,
)
from livespec_orchestrator_beads_fabro.commands.plan import resume_directive
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-10-22T07:00:00Z"
_DESCRIPTION = (
    "## Definition of Done\n\n- A child carries this one.\n- The plan's own proof carries this.\n"
)
_DEADLINE = "2099-10-10T12:00:00Z"
_MAX_HANDOFFS = 4
_BUDGET: dict[str, object] = {
    "deadline": _DEADLINE,
    "max_handoffs": _MAX_HANDOFFS,
    "epoch": "epoch-1",
    "handoff_count": 1,
}
_EPIC = "bd-ib-plan"
_OWN = "repo"
_OWN_PREFIX = "bd-ib"
_CARRIER_REPO = "carrier-repo"
_CARRIER_PREFIX = "cr"
_SATISFIED_ITEM = f"{_OWN_PREFIX}-landed"
_PROOF_MARKER = "Plan Proof of Done"


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


def _item(*, repo: Path, item_id: str, closed: bool) -> None:
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="task",
            title=item_id,
            description="a carrier of one plan assertion",
            assignee=None,
            created_at=_NOW,
        )
    )
    if closed:
        fake.close_issue(issue_id=item_id, reason="the carrier landed")


def _seed(*, repo: Path, carriers: tuple[str, ...]) -> None:
    """A chain-tracked epic whose obligation is satisfied, plus its carrier map."""
    required_result: dict[str, object] = {
        "repo": _OWN,
        "item_status": {"item_id": _SATISFIED_ITEM, "status": "closed"},
    }
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
                "next_action": {
                    "kind": "impl",
                    "ref": _SATISFIED_ITEM,
                    "text": "Take the recorded next step.",
                    "required_result": required_result,
                    "budget": _BUDGET,
                },
                "last_session": f"plan-session at {_NOW}",
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
    head = read_chain_head(config=config, epic_id=_EPIC)
    assert isinstance(head, ChainHead), head
    committed = commit_transition(
        config=config,
        epic_id=_EPIC,
        request=TransitionRequest(
            operation_id="op-seed",
            observed_head=head,
            authority=AuthorityState(
                required_result=required_result,
                original_deadline=_DEADLINE,
                max_handoffs=_MAX_HANDOFFS,
                consumed_handoffs=1,
            ),
            event_kind="handoff",
            author="plan-session",
            now=_NOW,
        ),
    )
    assert isinstance(committed, CommittedTransition), committed
    fake.add_comment(
        issue_id=_EPIC,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author="plan-session",
            now=_NOW,
            body="carriers:\n" + "\n".join(f"- {one}" for one in carriers),
        ),
    )


def _pointer(*, repo: Path) -> dict[str, object]:
    return dict(_fake(repo=repo).show_issue(issue_id=_EPIC)["metadata"]["next_action"])


def test_a_plan_level_proof_entry_is_never_waited_on_as_an_open_work_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With its work-item carrier closed, the plan-level entry derives the proof leg.

    The one assertion the map leaves to the plan's own record is exactly the one
    the proof leg discharges, so a gate reading `plan-level proof` as a carrier
    would hold the proof step behind itself — and because that literal resolves
    to no tenant, the state it would rest in is a `human` pointer asking a
    maintainer to configure the repository that mints an item called
    `plan-level proof`.
    """
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _item(repo=repo, item_id=_SATISFIED_ITEM, closed=True)
    _item(repo=repo, item_id="cr-child", closed=True)
    _seed(repo=repo, carriers=("1: cr-child", f"2: {PLAN_LEVEL_PROOF}"))

    directive = resume_directive(config=_config(repo=repo), epic_id=_EPIC, unattended=True)

    assert directive.next_action == f"proof:capture:{_EPIC}"
    assert _pointer(repo=repo)["required_result"] == {
        "repo": _OWN,
        "item_comment": {"item_id": _EPIC, "marker": _PROOF_MARKER},
    }


def test_the_work_item_carrier_beside_it_is_still_waited_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The carve-out drops the literal and nothing else.

    The CONTROL for the case above: a reader that dropped the whole `carriers:`
    block, or stopped at the plan-level line, would satisfy it while retiring the
    gate entirely. Here the same map's work-item carrier is open, and the resume
    must still wait on it.
    """
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _item(repo=repo, item_id=_SATISFIED_ITEM, closed=True)
    _item(repo=repo, item_id="cr-child", closed=False)
    _seed(repo=repo, carriers=(f"1: {PLAN_LEVEL_PROOF}", "2: cr-child"))

    directive = resume_directive(config=_config(repo=repo), epic_id=_EPIC, unattended=True)

    assert directive.next_action == "await:item:cr-child"
    assert _pointer(repo=repo)["required_result"] == {
        "repo": _CARRIER_REPO,
        "item_status": {"item_id": "cr-child", "status": "closed"},
    }

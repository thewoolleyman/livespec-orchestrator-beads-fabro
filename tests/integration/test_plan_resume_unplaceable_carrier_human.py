"""Every open carrier in a repository nothing resolves rests the plan on a human.

`bd-ib-evrynu`, the second half of the carrier gate, bound through the
production `resume_directive`. `test_plan_resume_open_carrier_await.py` covers
the carrier the result reader CAN resolve: the resume waits on it, and the
obligation it records is observable on the next resume. This module is the case
where no carrier can be placed at all, and the two have different right answers
rather than two shades of one.

WHY AN UNPLACEABLE CARRIER CANNOT BE WAITED ON. An `await` names a required
result, a required result names a repository identity, and an identity no
configured target resolves is REFUSED at the write — and would be
`unobservable` at every later read if it were not. So the gate has nothing to
wait on and must not pretend otherwise; and it equally must not derive the
plan-level step, because the carrier map names a carrier of one of the plan's
own assertions and nothing has established that it is closed. The honest rest
state is the one the clause already has for a question no unattended session can
answer: a `human` pointer naming the carriers.

WHY THE POINTER NAMES THE CARRIERS RATHER THAN THE CONFIGURATION. What a
maintainer has to decide is per-carrier — configure the sibling, re-assign the
assertion, or record that the carrier is done — and the ids are the only thing
that says which carriers are in question. A pointer saying "a carrier is
unplaceable" would send its reader back to the carrier-map event to work out
which.

WHY THIS IS NOT A WEAKER FORM OF THE AWAIT CASE, which is the one thing to hold
on to before editing either module. A build that reported every unplaceable
carrier as OPEN would satisfy this module's premise and fail the sibling's
`passed over` case; a build that passed over every unplaceable carrier and then
derived the plan-level step would satisfy that case and fail here. The two
readings pull in opposite directions, and only the pair pins the gate.
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
_DESCRIPTION = "## Definition of Done\n\n- The plan reaches its archive.\n"
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
_SATISFIED_ITEM = f"{_OWN_PREFIX}-landed"
# Two carriers whose prefixes no configured target declares, which is what an
# epic mapped to tenants this checkout has never been told about looks like.
_UNPLACEABLE = ("ob-5qlusq", "hl-pu2xr6")


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


def _project(*, tmp_path: Path) -> Path:
    """The plan's own checkout, configuring no sibling at all."""
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = {
        "livespec-orchestrator-beads-fabro": {"connection": {"prefix": _OWN_PREFIX}}
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    return repo


def _seed(*, repo: Path, carriers: tuple[str, ...]) -> None:
    """A chain-tracked epic whose obligation is satisfied, plus its carrier map."""
    required_result: dict[str, object] = {
        "repo": _OWN,
        "item_status": {"item_id": _SATISFIED_ITEM, "status": "closed"},
    }
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=_SATISFIED_ITEM,
            issue_type="task",
            title=_SATISFIED_ITEM,
            description="the item the plan's last obligation named",
            assignee=None,
            created_at=_NOW,
        )
    )
    fake.close_issue(issue_id=_SATISFIED_ITEM, reason="landed")
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


def test_carriers_in_unresolvable_repositories_rest_the_plan_on_a_human_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The persisted pointer is `human`, names both carriers, and tracks nothing.

    No proof, review or archive step is derived: the carrier map names carriers
    of this plan's own assertions and nothing has established that either is
    closed, so a plan-level record would assert what no read supports. The
    tracking fields are explicit nulls, which is what the clause requires of a
    `human` pointer and what keeps the unmet obligation in the progress history
    rather than discharging it by pointing somewhere else.
    """
    repo = _project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _seed(repo=repo, carriers=(f"1: {_UNPLACEABLE[0]}, {_UNPLACEABLE[1]}",))

    directive = resume_directive(config=_config(repo=repo), epic_id=_EPIC, unattended=True)

    assert directive.observation is not None
    assert directive.observation.status == "satisfied"
    pointer = _pointer(repo=repo)
    assert pointer["kind"] == "human"
    assert pointer["required_result"] is None
    assert pointer["budget"] is None
    text = pointer["text"]
    assert isinstance(text, str)
    for carrier in _UNPLACEABLE:
        assert carrier in text
    assert directive.next_action is None

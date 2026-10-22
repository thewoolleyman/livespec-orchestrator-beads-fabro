"""A plan resume waits on an OPEN carrier instead of deriving its proof leg.

`bd-ib-evrynu`, bound through the production `resume_directive` entry point and
the real store seam. The plan Definition-of-Done clause records which child, or
which plan-level proof, carries each plan assertion ONLY in the epic's
carrier-map scope event, and a plan's Proof of Done cannot be true while a
work-item carrier of one of its assertions is still open. The advance read
neither: `_plan_resume_advance._derived_action` asked `_next_ready_child_id` for
the epic's OWN children and then fell through to the plan-level leg, so a plan
whose carriers are all CROSS-TENANT — every carrier of the measured plan was —
had its child check come back empty on every resume and derived the proof step
while nine carriers sat open in other tenants.

WHY THE FIXTURE IS A CROSS-TENANT CARRIER RATHER THAN A CHILD OF THE EPIC. A
carrier filed in the plan's own tenant as a child of the epic is already caught:
it is a ready child, and the advance derives an `impl` step for it. The carrier
relation exists precisely for the case the child edge cannot express — a carrier
filed in a sibling tenant under the cross-tenant execution mirror — so a fixture
whose carrier is a local child would pass against the unrepaired build and
assert nothing about the gap. Measured 2026-10-22 00:57Z on plan epic
`bd-ib-fyozyd`: nine carriers of ordinal 6 open across five sibling tenants, the
epic's own child check empty, and the pointer advanced to
`proof:capture:bd-ib-fyozyd`.

WHY THE SECOND CASE IS NOT A RESTATEMENT OF THE FIRST, and why both live in one
module. The first case can be satisfied by a gate that awaits SOMETHING on every
carrier-mapped plan, which would stop every plan at its last carrier for ever.
The second case is the same fixture with the carrier CLOSED and a closed child of
the epic beside it, and it asserts the proof leg is derived exactly as before —
so it is the control that tells "the gate reads the carrier's status" apart from
"the gate blocks whenever a carrier map exists". Splitting them across modules is
how a later edit moves the boundary between them with neither file noticing.

EVERY EPIC HERE IS CHAIN-TRACKED, for the reason
`tests/integration/test_plan_resume_plan_own_repository.py` records: a resume
settles the durable-progress question off the epic's authority chain and returns
before it reaches the pointer, so a chainless epic never exercises the advance
this module is about.
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
_CONSUMED_HANDOFFS = 1
_BUDGET: dict[str, object] = {
    "deadline": _DEADLINE,
    "max_handoffs": _MAX_HANDOFFS,
    "epoch": "epoch-1",
    "handoff_count": _CONSUMED_HANDOFFS,
}
_EPIC = "bd-ib-plan"
# The plan's own repository, which is the invoking checkout's directory name: a
# tmp-path fixture is no git clone, so neither an origin remote nor a recorded
# primary path names it.
_OWN = "repo"
_OWN_PREFIX = "bd-ib"
# The sibling tenant a carrier of one plan assertion was filed in. Its clone is
# configured AND present and it resolves a tenant connection of its own, so the
# carrier's status is a real cross-tenant reading rather than a resolution
# failure wearing a satisfied label.
_CARRIER_REPO = "carrier-repo"
_CARRIER_PREFIX = "cr"
_OPEN_CARRIER = f"{_CARRIER_PREFIX}-open"
# The item the plan's last obligation named, already closed, which is what makes
# the pointer stale and drives the advance under test.
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


def _governed_project(*, tmp_path: Path) -> Path:
    """The plan's own checkout, beside a configured sibling carrier tenant."""
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


def _seed_epic(*, repo: Path) -> None:
    """A chain-tracked plan epic whose recorded obligation is already satisfied.

    The obligation is committed as the chain's AUTHORITY and only then projected
    onto the pointer, because `resume_directive` reads the chain first and
    returns on its verdict: an epic whose obligation lived in the pointer alone
    is graded `plan-progress-tracking: missing` and never reaches the advance.
    """
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
                consumed_handoffs=_CONSUMED_HANDOFFS,
            ),
            event_kind="handoff",
            author="plan-session",
            now=_NOW,
        ),
    )
    assert isinstance(committed, CommittedTransition), committed


def _carrier_map_event(*, repo: Path, carriers: tuple[str, ...]) -> None:
    """Append the epic's carrier-map scope event, in the primitive's own shape."""
    lines = "\n".join(f"- {one}" for one in carriers)
    _fake(repo=repo).add_comment(
        issue_id=_EPIC,
        body=plan_comment_body(
            prefix=PLAN_SCOPE_PREFIX,
            author="plan-session",
            now=_NOW,
            body=(
                "Requirement carriers:\n- the plan reaches its archive\n\n"
                f"Explicit deferrals:\n- none\n\ncarriers:\n{lines}"
            ),
        ),
    )


def _pointer(*, repo: Path) -> dict[str, object]:
    return dict(_fake(repo=repo).show_issue(issue_id=_EPIC)["metadata"]["next_action"])


def test_an_open_cross_tenant_carrier_is_awaited_instead_of_the_proof_leg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The derived step waits on the carrier, in the carrier's own repository.

    The plan's recorded obligation is satisfied and the epic has no ready child,
    so the unrepaired advance derives `proof:capture:<epic>` — a step whose
    record would assert the whole Definition of Done while the carrier of one of
    its assertions is still open. The repaired advance waits on that carrier, and
    the obligation it records names the carrier's OWN repository: the carrier
    lives in that tenant, so an obligation naming the plan's repository would be
    unobservable on the very next resume.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _item(repo=repo, item_id=_SATISFIED_ITEM, closed=True)
    _item(repo=repo, item_id=_OPEN_CARRIER, closed=False)
    _seed_epic(repo=repo)
    _carrier_map_event(repo=repo, carriers=(f"1: {_OPEN_CARRIER}",))

    directive = resume_directive(config=_config(repo=repo), epic_id=_EPIC, unattended=True)

    assert directive.observation is not None
    assert directive.observation.status == "satisfied"
    assert directive.next_action == f"await:item:{_OPEN_CARRIER}"
    assert _pointer(repo=repo)["required_result"] == {
        "repo": _CARRIER_REPO,
        "item_status": {"item_id": _OPEN_CARRIER, "status": "closed"},
    }


def test_a_carrier_map_whose_carriers_are_all_closed_still_derives_the_proof_leg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With every carrier closed and every child closed, the proof leg stands.

    The CONTROL for the case above: a gate that blocked whenever a carrier map
    existed would satisfy that case and stop every carrier-mapped plan at its
    last carrier for ever. The epic carries a closed child as well as a closed
    carrier, so both of the conditions the plan-level leg now rests on are
    exercised rather than one of them holding vacuously.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _item(repo=repo, item_id=_SATISFIED_ITEM, closed=True)
    _item(repo=repo, item_id=f"{_EPIC}.1", closed=True)
    _item(repo=repo, item_id=_OPEN_CARRIER, closed=True)
    _seed_epic(repo=repo)
    _carrier_map_event(repo=repo, carriers=(f"1: {_OPEN_CARRIER}",))

    directive = resume_directive(config=_config(repo=repo), epic_id=_EPIC, unattended=True)

    assert directive.next_action == f"proof:capture:{_EPIC}"
    assert _pointer(repo=repo)["required_result"] == {
        "repo": _OWN,
        "item_comment": {"item_id": _EPIC, "marker": _PROOF_MARKER},
    }

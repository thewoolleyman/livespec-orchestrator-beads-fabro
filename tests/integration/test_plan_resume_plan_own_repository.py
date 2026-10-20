"""A plan's OWN obligations name, and are read from, the plan's own repository.

Both halves of `bd-ib-woacnk`, bound through the production `resume_directive`
entry point and the real store seam: the pointer the advance WRITES, and the
obligation the resume READS.

WHY A FOREIGN CARRIER IS THE FIXTURE RATHER THAN A DETAIL. A plan's last
satisfied obligation legitimately names another repository — a carrier child
filed in a sibling tenant under the cross-tenant execution mirror — and the
derived proof, review and archive steps all target the PLAN EPIC, which lives in
the plan's own tenant whatever the previous carrier's repository was. Carrying
the satisfied obligation's repository forward therefore stamps a repository the
epic does not live in, and the next resume reads the epic against the wrong
tenant: `plan-progress-tracking: unobservable`, dispatch withheld, and the plan
locked behind a pointer no sanctioned write can replace because replacing an
unobservable obligation is refused by design.

WHY THE SECOND CASE IS NOT A RESTATEMENT OF THE FIRST. Fixing the WRITE leaves
every plan whose pointer was already poisoned exactly as locked as before, so
the READ has to recognise an obligation that names the plan epic itself and
resolve it against the plan's own tenant. The control that distinguishes "reads
it from the right tenant" from merely "reports something observable" is the
POSITIVE one: the epic's own closed status is a record only the plan's own
tenant holds, so a satisfied reading is reachable from no other tenant.

EVERY EPIC HERE IS CHAIN-TRACKED, and that is load-bearing rather than
incidental. `resume_directive` settles the DURABLE-PROGRESS question first, off
the epic's authority chain, and returns before it ever reaches the pointer — so
on a chainless epic the progress gate reports `missing` with dispatch PERMITTED
and the read under test is never the read that decides anything. Measured
2026-10-20 on the chainless fixture this module shipped with: the second case
passed against a build whose redirect the locked plan could not reach, which is
the wrong-population trap this repository's verification discipline catalogues.
The plan locked in production (`bd-ib-fyozyd`) carries a chain, so the fixture
carries one too, with the obligation recorded as the chain's own authority.

WHY THE TENANT DISCRIMINATION RIDES ON THE ARCHIVE LEG'S STATUS AND NOT ON THE
PROOF LEG'S MARKER. A committed chain transition writes a `plan-progress-event`
comment on the epic whose payload embeds the obligation verbatim — marker
included — so an `item_comment` obligation naming the epic is satisfied by the
very event that recorded it, whichever tenant answers. That makes the marker
shape unable to tell a right tenant from a wrong one. The archive leg's
`item_status` on the epic is immune: a status is a field of the record rather
than text in a comment, so `active` and `closed` are readings of the plan's own
tenant and nothing else.

WHY A THIRD CASE IS OWED ON A LEG THAT DOES DERIVE A SUCCESSOR. That same
archive leg is the ONE leg `_plan_resume_advance._plan_level_action` derives no
next step for, so its satisfied reading reports a terminal state and never
attempts a replacement pointer — and the sanctioned WRITE that persists one
reads the prior obligation a THIRD time, in `_plan_tracked_write`, where an
unobservable reading refuses the replacement outright. A plan is therefore still
stopped if that read is not redirected too: not locked behind a diagnosable
pointer, but answering with no further step at all, which under an unattended
resume is silence. So the third case is the measured plan's own leg — a `proof`
leg, whose successor the advance does derive — and it asserts the derived step
and the pointer that step's obligation landed in.
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
from livespec_orchestrator_beads_fabro.commands.plan import resume_directive
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-10-20T12:00:00Z"
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
# The plan's own repository, which is the invoking checkout's directory name: a
# tmp-path fixture is no git clone, so neither an origin remote nor a recorded
# primary path names it.
_OWN = "repo"
# The sibling that carried the plan's last satisfied obligation. Its clone is
# configured AND present, and it resolves a tenant connection of its own, so the
# satisfied reading that drives the advance is a real cross-tenant observation
# rather than a resolution failure wearing a satisfied label.
_CARRIER_REPO = "carrier-repo"
_CARRIER_ITEM = "bd-ib-carrier-child"
# A sibling whose clone exists but which configures no tenant of its own, so a
# read aimed at it is UNOBSERVABLE — the state the locked plan was measured in.
_STRANGER_REPO = "stranger-repo"
_PROOF_MARKER = "Plan Proof of Done"
_REVIEW_MARKER = "plan-completeness-review-evidence"


@pytest.fixture(autouse=True)
def _hermetic_tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
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
    """The plan's own checkout, beside a configured carrier and a configured stranger."""
    repo = tmp_path / _OWN
    repo.mkdir()
    configured: dict[str, object] = dict(_connection(prefix="bd-ib"))
    configured["cross_repo_targets"] = {
        name: {"github_url": f"https://github.com/thewoolleyman/{name}"}
        for name in (_CARRIER_REPO, _STRANGER_REPO)
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(configured), encoding="utf-8")
    carrier = tmp_path / _CARRIER_REPO
    carrier.mkdir()
    _ = (carrier / ".livespec.jsonc").write_text(
        json.dumps(_connection(prefix="bd-ib")), encoding="utf-8"
    )
    (tmp_path / _STRANGER_REPO).mkdir()
    return repo


def _seed_epic(
    *,
    repo: Path,
    epic_id: str,
    kind: str,
    ref: str,
    required_result: dict[str, object],
) -> None:
    """A plan epic whose AUTHORITY CHAIN records `required_result`, plus its pointer.

    The obligation is committed as the chain's authority and only then projected
    onto the pointer, because `resume_directive` reads the chain first and
    returns on it: an epic whose obligation lived in the pointer alone would be
    graded `plan-progress-tracking: missing` and would never exercise the read
    that locks a real plan.
    """
    fake = _fake(repo=repo)
    _ = fake.create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title=epic_id,
            description=_DESCRIPTION,
            assignee=None,
            created_at=_NOW,
            metadata={
                "next_action": {
                    "kind": kind,
                    "ref": ref,
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
        issue_id=epic_id,
        metadata=chain_cache_metadata(
            existing_metadata=dict(fake.show_issue(issue_id=epic_id)["metadata"]),
            latest_closed=None,
            current=genesis,
        ),
    )
    config = _config(repo=repo)
    head = read_chain_head(config=config, epic_id=epic_id)
    assert isinstance(head, ChainHead), head
    committed = commit_transition(
        config=config,
        epic_id=epic_id,
        request=TransitionRequest(
            operation_id=f"op-seed-{epic_id}",
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


def _pointer(*, repo: Path, epic_id: str) -> dict[str, object]:
    return dict(_fake(repo=repo).show_issue(issue_id=epic_id)["metadata"]["next_action"])


def test_a_derived_plan_step_names_the_plans_own_repository_not_the_carriers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The advance stamps the epic's own repository, whatever carried the last leg.

    The satisfied obligation names a sibling tenant, and the plan has no ready
    child left, so the advance derives the plan's proof leg. That leg's required
    result is a comment on the plan epic, which lives in the plan's own tenant —
    so the pointer must name the plan's own repository rather than the one the
    satisfied carrier happened to live in.

    It is also the NEGATIVE control for the read half below: this obligation's
    own target is the carrier CHILD rather than the epic, so it is read against
    the carrier exactly as recorded. A redirect that fired on anything less
    specific than "the target is the plan epic" would report `repo` as the
    plan's own here and read the carrier's result from the wrong tenant.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _ = _fake(repo=repo).create_issue(
        draft=IssueDraft(
            issue_id=_CARRIER_ITEM,
            issue_type="task",
            title="a carrier child in a sibling tenant",
            description="The plan's last satisfied obligation.",
            assignee=None,
            created_at=_NOW,
        )
    )
    _fake(repo=repo).close_issue(issue_id=_CARRIER_ITEM, reason="the carrier landed")
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-plan",
        kind="impl",
        ref=_CARRIER_ITEM,
        required_result={
            "repo": _CARRIER_REPO,
            "item_status": {"item_id": _CARRIER_ITEM, "status": "closed"},
        },
    )

    directive = resume_directive(config=_config(repo=repo), epic_id="bd-ib-plan", unattended=True)

    assert directive.observation is not None
    assert directive.observation.status == "satisfied"
    assert directive.observation.repo == _CARRIER_REPO
    assert directive.next_action == "proof:capture:bd-ib-plan"
    assert _pointer(repo=repo, epic_id="bd-ib-plan")["required_result"] == {
        "repo": _OWN,
        "item_comment": {"item_id": "bd-ib-plan", "marker": _PROOF_MARKER},
    }


def test_an_obligation_naming_the_plan_epic_elsewhere_is_read_from_the_plans_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pointer already poisoned must still be observable, or the plan stays locked.

    Both epics carry a recorded archive obligation on THEMSELVES under a sibling
    whose clone resolves and whose tenant does not, which is the state the
    measured plan was found in: the read fails, `resume_directive` reports
    `plan-progress-tracking: unobservable`, withholds dispatch in favour of a
    diagnosis, and no sanctioned write can replace an unobservable obligation. A
    plan epic lives in the plan's own tenant whatever its pointer says, so the
    read resolves there.

    The POSITIVE control is what separates "observable" from "read from the right
    tenant": the second epic is CLOSED, and its closed status is a record only
    the plan's own tenant holds, so the satisfied reading is reachable from no
    other tenant. Its unmet sibling reports `unsatisfied` rather than
    `unobservable`, which is the same discrimination from the other side.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    for epic_id in ("bd-ib-pointed", "bd-ib-proved"):
        _seed_epic(
            repo=repo,
            epic_id=epic_id,
            kind="archive",
            ref=epic_id,
            required_result={
                "repo": _STRANGER_REPO,
                "item_status": {"item_id": epic_id, "status": "closed"},
            },
        )
    _fake(repo=repo).close_issue(issue_id="bd-ib-proved", reason="the plan archived")

    unmet = resume_directive(config=_config(repo=repo), epic_id="bd-ib-pointed", unattended=True)
    met = resume_directive(config=_config(repo=repo), epic_id="bd-ib-proved", unattended=True)

    assert unmet.findings == ()
    assert unmet.observation is not None
    assert unmet.observation.status == "unsatisfied"
    assert unmet.observation.repo == _OWN
    assert unmet.next_action == "archive:bd-ib-pointed"
    # The READ redirects; it does not repair. The recorded pointer still names
    # the stranger, and the advance in the sibling case above is what replaces a
    # pointer with the plan's own repository — so neither half of this fix
    # stands in for the other.
    assert _pointer(repo=repo, epic_id="bd-ib-pointed")["required_result"] == {
        "repo": _STRANGER_REPO,
        "item_status": {"item_id": "bd-ib-pointed", "status": "closed"},
    }

    assert met.observation is not None
    assert met.observation.status == "satisfied"
    assert met.observation.repo == _OWN


def test_the_replacement_pointer_lands_when_the_prior_obligation_names_the_epic_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A satisfied plan leg must reach its NEXT leg, which takes a THIRD read.

    The case above establishes that both READING surfaces resolve the epic
    against the plan's own tenant, and stops there: its obligation is the archive
    leg's, and the archive leg is the one leg `_plan_level_action` derives no
    successor for, so the advance reports a terminal state and never attempts a
    replacement pointer. The sanctioned WRITE that persists one reads the prior
    obligation a third time, inside `_plan_tracked_write._prior_observation`, and
    that read decides whether the write is admitted at all: an unobservable prior
    obligation cannot be replaced by design, so the derived pointer is refused
    and the resume answers with no further step — a plan that silently stops
    under an unattended resume, where the locked state it replaces at least
    named a diagnosis.

    So this case is the measured plan's own leg. Its obligation is the proof
    leg's, which `_plan_level_action` DOES derive a successor for, and the
    assertions are the two halves no earlier case can reach: the derived review
    step is what the resume answers, and the recorded pointer now carries that
    step's own obligation under the plan's own repository.

    THE SATISFIED READING IS NOT THIS CASE'S DISCRIMINATOR, and saying so is
    what keeps it honest. A committed chain transition writes a
    `plan-progress-event` comment on the epic whose payload embeds the obligation
    verbatim — marker included — so ANY `item_comment` obligation naming the epic
    is satisfied by the event that recorded it, in whichever tenant answers; the
    epic's real proof record is seeded beside it so the fixture is a plan whose
    proof leg genuinely landed rather than one resting on that echo, but the echo
    is the earlier comment and is what the reading cites. What discriminates here
    is therefore the OTHER answer: the stranger repository resolves a clone and
    no tenant, so every read aimed at it is `unobservable`, which is exactly the
    reading that refuses the replacement write. The case above is the one that
    separates the plan's own tenant from any other, and it carries that claim for
    both.
    """
    repo = _governed_project(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    _seed_epic(
        repo=repo,
        epic_id="bd-ib-proofleg",
        kind="proof",
        ref="capture:bd-ib-proofleg",
        required_result={
            "repo": _STRANGER_REPO,
            "item_comment": {"item_id": "bd-ib-proofleg", "marker": _PROOF_MARKER},
        },
    )
    _fake(repo=repo).add_comment(
        issue_id="bd-ib-proofleg",
        body=f"{_PROOF_MARKER} — captured — the plan's proof leg landed.",
    )

    directive = resume_directive(
        config=_config(repo=repo), epic_id="bd-ib-proofleg", unattended=True
    )

    assert directive.observation is not None
    assert directive.observation.status == "satisfied"
    assert directive.observation.repo == _OWN
    assert directive.next_action == "review:bd-ib-proofleg"
    assert _pointer(repo=repo, epic_id="bd-ib-proofleg")["required_result"] == {
        "repo": _OWN,
        "item_comment": {"item_id": "bd-ib-proofleg", "marker": _REVIEW_MARKER},
    }

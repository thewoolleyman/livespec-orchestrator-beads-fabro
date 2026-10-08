"""Every mismatch a resume refuses on, named in the clause's own order.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" lists eight refusals and then adds the rule that makes the
list more than a list: "When more than one refusal applies, the refusal MUST name
EVERY applicable mismatch, in the order listed, each with its remedy; a refusal
that names only the first does not satisfy this clause." Scenario 143 exercises
each arm and then exercises the conjunction.

WHY THE CONJUNCTION IS ASSERTED AND NOT JUST EACH ARM. A ladder of early returns
passes every single-mismatch test perfectly well and fails the clause: an item
`active` under a live claim is refused on the status bullet AND the live-run
bullet together, and an operator told only "not ready" would run
`resolve-blocked` and dispatch straight into the live run. So this file asserts
the full tuple for a multiply-mismatched observation, in order.

WHY AN UNOBSERVABLE MEASUREMENT IS A REFUSAL AND NOT A SKIP. The clause: "it MUST
NOT proceed on an unobservable answer." A forge that cannot report the head and a
forge reporting a head that matches produce opposite decisions, and nothing
downstream can tell them apart once the comparison has been skipped — the
fail-open direction here resumes on a tree no record describes. The two
unobservables sit where the measurement they replace would have sat, so the
order an operator reads is the order the questions were asked.

WHY THE MERGED PULL REQUEST HAS ITS OWN REMEDY. A closed pull request's remedy is
a plain dispatch, but a MERGED one's is `reconcile-merged --item`, which "requires
a real merge and stays the only valve for one". Reporting a plain dispatch for a
merged pull request would send an operator to cut an empty branch against work
that has already landed, and spend an `acceptance_rework_cap` attempt to fail.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_refusals.py"
)

_HEAD = "a" * 40
_MOVED_HEAD = "b" * 40
_ITEM = "bd-ib-fngpwg"


def _refusals_module() -> Any:
    """Import the refusal ladder, proving the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _observation(**overrides: Any) -> Any:
    """A fully-conforming observation, overridden one field at a time.

    The default is the state a resume PROCEEDS from, so every assertion below
    changes exactly one thing and the refusal it earns is attributable to that
    thing alone.
    """
    module = _refusals_module()
    fields: dict[str, Any] = {
        "work_item_id": _ITEM,
        "status": "ready",
        "blocked_reason": None,
        "anchor_head": _HEAD,
        "pull_request": 2639,
        "pull_request_state": module.PR_STATE_OPEN,
        "pull_request_head": _HEAD,
        "live_runs": (),
        "liveness_observed": True,
        "lock_age_seconds": None,
        "changed_assertions": (),
        "earlier_resumes": (),
    }
    fields.update(overrides)
    return module.ResumeObservation(**fields)


def test_a_conforming_observation_refuses_nothing() -> None:
    """The control: without it, a ladder that refuses everything would pass."""
    module = _refusals_module()
    assert module.resume_refusals(observation=_observation()) == ()


def test_a_not_ready_item_is_refused_naming_its_status_and_remedy() -> None:
    """A resume never steps around the ledger's human decision."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(status="blocked", blocked_reason="needs-human")
    )
    assert len(refusals) == 1
    assert "blocked" in refusals[0]
    assert f"resolve-blocked:{_ITEM}:ready" in refusals[0]


def test_a_stranded_active_claim_is_refused_naming_reconcile_runs() -> None:
    """An `active` item with no live run is a stranded claim, not a human decision."""
    module = _refusals_module()
    refusals = module.resume_refusals(observation=_observation(status="active"))
    assert len(refusals) == 1
    assert "reconcile-runs" in refusals[0]


def test_nothing_to_resume_from_is_refused_naming_what_is_missing() -> None:
    """No open pull request, or no record naming a head, is one refusal each."""
    module = _refusals_module()
    no_pr = module.resume_refusals(observation=_observation(pull_request=None))
    assert len(no_pr) == 1
    assert "no open pull request" in no_pr[0]
    assert "dispatch" in no_pr[0]
    no_head = module.resume_refusals(observation=_observation(anchor_head=None))
    assert len(no_head) == 1
    assert "names a publish-branch head" in no_head[0]


def test_a_moved_head_is_refused_naming_both_shas() -> None:
    """Proof verified on one tree is not proof of another."""
    module = _refusals_module()
    refusals = module.resume_refusals(observation=_observation(pull_request_head=_MOVED_HEAD))
    assert len(refusals) == 1
    assert _HEAD in refusals[0]
    assert _MOVED_HEAD in refusals[0]
    assert "dispatch" in refusals[0]


def test_an_unreportable_head_is_refused_naming_the_measurement() -> None:
    """A forge that cannot answer is not a forge answering that it matches."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(pull_request_head=None, pull_request_state=None)
    )
    assert len(refusals) == 1
    assert "could not report" in refusals[0]


def test_a_changed_definition_of_done_is_refused_naming_the_difference() -> None:
    """The inherited records must prove the assertions the resume is graded on."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(changed_assertions=("The valve holds when blinded.",))
    )
    assert len(refusals) == 1
    assert "The valve holds when blinded." in refusals[0]


def test_a_live_earlier_run_is_refused_naming_the_run_and_its_status() -> None:
    """A resume of a run that has not ended would race its own publish branch."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(live_runs=(module.LiveRun(run_id="01M4LIVE", status="blocked"),))
    )
    assert len(refusals) == 1
    assert "01M4LIVE" in refusals[0]
    assert "blocked" in refusals[0]


def test_an_unobservable_factory_is_refused_naming_the_measurement() -> None:
    """A factory that cannot be asked is not a factory answering that nothing runs."""
    module = _refusals_module()
    refusals = module.resume_refusals(observation=_observation(liveness_observed=False))
    assert len(refusals) == 1
    assert "liveness" in refusals[0]


def test_a_live_ownership_lock_is_refused_naming_its_age() -> None:
    """The same lock `reconcile-merged` refuses on, refused on the same terms."""
    module = _refusals_module()
    refusals = module.resume_refusals(observation=_observation(lock_age_seconds=42.0))
    assert len(refusals) == 1
    assert "42" in refusals[0]


def test_a_closed_pull_request_is_refused_naming_a_plain_dispatch() -> None:
    """There is no open pull request left for a resumed run to finish."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(pull_request_state=module.PR_STATE_CLOSED)
    )
    assert len(refusals) == 1
    assert "dispatch" in refusals[0]
    assert "reconcile-merged" not in refusals[0]


def test_a_merged_pull_request_is_refused_naming_reconcile_merged() -> None:
    """A merged pull request's one valve is the one that requires a real merge."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(pull_request_state=module.PR_STATE_MERGED)
    )
    assert len(refusals) == 1
    assert "reconcile-merged" in refusals[0]


def test_a_third_resume_is_refused_naming_both_earlier_resumes() -> None:
    """The per-run proof-loop caps are bounded on the host by this refusal."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(earlier_resumes=("01M4ONE", "01M4TWO"))
    )
    assert len(refusals) == 1
    assert "01M4ONE" in refusals[0]
    assert "01M4TWO" in refusals[0]


def test_every_applicable_mismatch_is_named_in_the_clause_order() -> None:
    """The conjunction rule: a refusal naming only the first does not satisfy it."""
    module = _refusals_module()
    refusals = module.resume_refusals(
        observation=_observation(
            status="active",
            live_runs=(module.LiveRun(run_id="01M4LIVE", status="running"),),
        )
    )
    assert len(refusals) == 2
    assert "active" in refusals[0]
    assert "01M4LIVE" in refusals[1]

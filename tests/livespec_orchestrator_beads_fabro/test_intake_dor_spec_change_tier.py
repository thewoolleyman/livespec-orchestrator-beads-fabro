"""Tests for intake HOLDING a spec-change-tier item and RELEASING it on ratification.

The clause: a spec-change-tier item "MUST be held out of `ready`" until both
conditions hold, and then "the next intake or drain pass MUST release the hold
with no human valve and route the item exactly as its effective
`admission_policy` decides, so `auto` admission routes it to `ready` and
`manual` admission rests it at `pending-approval` for the `approve` valve, as it
would any other item." Scenario 206 carries both release arms as separate
scenarios, and both are graded here.

THE HOLD AND ITS CONTROL DIFFER IN ONE INPUT. "The item did not reach `ready`"
is satisfied by a build that withholds `ready` from everything, so the held
filing sits beside an identical one carrying no recorded classification, over
one store and one spec tree.

THE TWO RELEASE ARMS DIFFER IN ONE INPUT TOO — the item's own admission label —
because "released" and "routed by the admission policy" are two claims and a
build that routed every released item to `ready` would satisfy the first while
auto-approving work a human asked to hold.

THE RELEASE IS ASSERTED WITH NO HUMAN VALVE ANYWHERE IN IT: the same
`apply_intake_dor` call that holds an unratified item releases a ratified one,
with nothing between them but the ratification and the fresh verdict.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierVerdict,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.unsafe import unsafe_perform_io

_HEADING = "## Effective acceptance criteria"
_TOPIC = "spec-stated-judgement-and-spec-change-tier"
_ITEM = "bd-ib-57ss2n"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    reset_fake_singleton()
    yield
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


def _repo(*, tmp_path: Path, ratified: bool = False, connected: bool = True) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    if connected:
        _ = (repo / ".livespec.jsonc").write_text(
            '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
            encoding="utf-8",
        )
    if ratified:
        directory = spec / "history" / "v205" / "proposed_changes"
        directory.mkdir(parents=True)
        _ = (directory / f"{_TOPIC}-revision.md").write_text(
            f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
        )
    return repo


def _seed(*, admission: str = "auto") -> None:
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=_ITEM,
            issue_type="task",
            title="The spec-change tier is decided by the spec-stated judgement",
            description=(
                f"## Definition of Done\n\n- The tier is decided.\n\nReferences: {_HEADING}\n"
            ),
            priority=2,
            assignee=None,
            created_at="2026-10-24T00:00:00Z",
            labels=[f"admission:{admission}", f"proposal-topic:{_TOPIC}"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )


def _record_held() -> None:
    append_work_item_comment(
        path=_config(),
        work_item_id=_ITEM,
        body=spec_change_tier_comment(
            item_id=_ITEM,
            stage="pre-admission",
            verdict=SpecChangeTierVerdict(
                item_class="feature",
                stated_kind="unstated",
                generalization_target=_HEADING,
                linked_proposal_topic=_TOPIC,
            ),
        ),
    )


def _checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


class _Reader:
    """A `SpecChangeTierReader` double returning one fixed fresh verdict."""

    def __init__(self, *, verdict: SpecChangeTierVerdict | None) -> None:
        self.verdict = verdict

    def __call__(
        self, *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        _ = (item, repo, linked_topic, topic_ratified)
        return self.verdict


def _route(*, repo: Path, reader: _Reader | None = None) -> str:
    """One intake pass, naming the reader seam only where a case supplies one.

    The seam does not exist when this module's Red is authored, so a call that
    always named it would make every case here die on a `TypeError` — proving
    only that a parameter is absent. The HOLD case therefore reaches intake
    through its unchanged signature and fails on a genuine routing assertion.
    """
    config = _config(repo_root=repo)
    routed = (
        apply_intake_dor(path=config, item_id=_ITEM, checklist=_checklist())
        if reader is None
        else apply_intake_dor(
            path=config, item_id=_ITEM, checklist=_checklist(), spec_change_reader=reader
        )
    )
    return unsafe_perform_io(routed.unwrap())


def _released_reader() -> _Reader:
    return _Reader(
        verdict=SpecChangeTierVerdict(
            item_class="feature",
            stated_kind="stated",
            linked_proposal_topic=_TOPIC,
            topic_ratified=True,
        )
    )


def test_a_spec_change_tier_item_is_not_routed_to_ready_by_intake(tmp_path: Path) -> None:
    """The hold, at the surface that would otherwise approve the item onward."""
    _seed()
    _record_held()

    assert _route(repo=_repo(tmp_path=tmp_path)) == "pending-approval"


def test_an_item_carrying_no_spec_change_record_still_reaches_ready(tmp_path: Path) -> None:
    """The control: the same filing, differing only in the recorded classification."""
    _seed()

    assert _route(repo=_repo(tmp_path=tmp_path)) == "ready"


def test_ratification_and_a_stated_verdict_release_the_item_to_ready(tmp_path: Path) -> None:
    """Both conditions met under `auto` admission, with no human valve."""
    _seed()
    _record_held()

    assert (
        _route(repo=_repo(tmp_path=tmp_path, ratified=True), reader=_released_reader()) == "ready"
    )


def test_a_released_item_under_manual_admission_rests_at_pending_approval(
    tmp_path: Path,
) -> None:
    """The second release arm: the spec hold lifts and the approve valve stands."""
    _seed(admission="manual")
    _record_held()

    assert (
        _route(repo=_repo(tmp_path=tmp_path, ratified=True), reader=_released_reader())
        == "pending-approval"
    )


def test_a_rejected_proposal_leaves_the_item_held_however_the_judgement_reads(
    tmp_path: Path,
) -> None:
    """Scenario 206's rejected proposal, reached through intake.

    The fresh verdict reports `stated`, so a build that released on the
    judgement alone would route this to `ready` — the topic is simply never
    ratified, and the hold is the one the mechanical read makes.
    """
    _seed()
    _record_held()

    assert _route(repo=_repo(tmp_path=tmp_path), reader=_released_reader()) == "pending-approval"


def test_a_repository_with_no_resolvable_connection_routes_as_it_did_before(
    tmp_path: Path,
) -> None:
    """The labels the linked topic rides on are a ledger read that can fail.

    It is resolved from the repository rather than from the connection intake
    already holds, so an unconfigured repository raised from inside the gate —
    a bug-class escape on the path whose whole job is routing a filed item.
    """
    _seed()

    assert _route(repo=_repo(tmp_path=tmp_path, connected=False)) == "ready"

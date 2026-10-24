"""Tests for RECORDING that the spec-change-tier classification did not run.

The clause: "When the classification cannot run (no eligible model, a timeout,
or an unparseable verdict), intake MUST record that on the item and route it as
it would without the classification".

BOTH HALVES ARE GRADED, and they pull apart. The ROUTING half is a fail-open —
an unlabelled item the classification could not reach must not be held — and the
RECORD half is what keeps that fail-open honest, because an outage that leaves
no trace is indistinguishable at every surface from a classification that ran
and found nothing.

THE RECORD IS CAPPED PER CAUSE, mirroring the Definition-of-Done judgement's own
did-not-run cap for the same reason: this runs on every intake and every
dispatch path, so an uncapped write appends one comment per pass to an
append-only sidecar for as long as the outage lasts. The cap is asserted by
driving TWO passes and counting, which a build writing unconditionally fails
while satisfying every single-pass assertion.

THE CAP IS BOUNDED BY THE NEXT CLASSIFICATION, not by the item's lifetime. A
cause recorded before a classification that ran describes an outage that
classification disproves, so a later recurrence must record again — otherwise
one early outage silences the item about a judging path that has since stopped
working.

THE MARKER IS SPELLED AS A LITERAL AND BOUND TO THE EXPORTED NAME, because this
module's Red predates the constant and a Red's test bytes are fixed across its
Red-to-Green pair.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands import _spec_change_tier
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SpecChangeTierVerdict
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    spec_change_tier_hold,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MARKER = "livespec-spec-change-tier-unavailable"
_ITEM = "bd-ib-57ss2n"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
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
        fake=True,
        repo_root=repo,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="feature",
        status="ready",
        title="The spec-change tier is decided by the spec-stated judgement",
        description="## Definition of Done\n\n- The tier is decided.\n\nReferences: ## Other\n",
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-24T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True, exist_ok=True)
    return repo


class _Reader:
    """A reader that answers a fixed verdict, or none at all."""

    def __init__(self, *, verdict: SpecChangeTierVerdict | None) -> None:
        self.verdict = verdict

    def __call__(
        self, *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        _ = (item, repo, linked_topic, topic_ratified)
        return self.verdict


def _filed(*, repo: Path) -> StoreConfig:
    config = _config(repo=repo)
    append_work_item(path=config, item=_item())
    return config


def _hold(*, config: StoreConfig, repo: Path, reader: _Reader) -> object:
    return spec_change_tier_hold(
        item=_item(), repo=repo, path=config, stage="pre-admission", reader=reader
    )


def _unavailable_records(*, config: StoreConfig) -> tuple[str, ...]:
    return tuple(
        comment.text
        for comment in read_work_item_comments(path=config, work_item_id=_ITEM)
        if comment.text.startswith(_MARKER)
    )


def test_a_classification_that_cannot_run_records_the_cause_on_the_item(
    tmp_path: Path,
) -> None:
    """The record half, and the one the clause names in as many words."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo)

    _ = _hold(config=config, repo=repo, reader=_Reader(verdict=None))

    records = _unavailable_records(config=config)
    assert len(records) == 1
    assert _ITEM in records[0]


def test_an_item_the_classification_could_not_reach_is_routed_as_it_is_today(
    tmp_path: Path,
) -> None:
    """The routing half: an unlabelled item is not held by an outage."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo)

    assert _hold(config=config, repo=repo, reader=_Reader(verdict=None)) is None


def test_a_recurring_outage_records_its_cause_at_most_once(tmp_path: Path) -> None:
    """The cap, read off a SECOND pass over the same unchanged item."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo)
    reader = _Reader(verdict=None)

    _ = _hold(config=config, repo=repo, reader=reader)
    _ = _hold(config=config, repo=repo, reader=reader)

    assert len(_unavailable_records(config=config)) == 1


def test_an_outage_after_a_classification_that_ran_is_recorded_again(tmp_path: Path) -> None:
    """The cap is bounded by the next classification, not by the item's lifetime.

    Without this the first outage silences the item for ever, and a judging
    path that stops working months later leaves no trace at all.
    """
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo)

    _ = _hold(config=config, repo=repo, reader=_Reader(verdict=None))
    _ = _hold(
        config=config, repo=repo, reader=_Reader(verdict=SpecChangeTierVerdict(item_class="chore"))
    )
    _ = _hold(config=config, repo=repo, reader=_Reader(verdict=None))

    assert len(_unavailable_records(config=config)) == 2


def test_a_classification_that_ran_records_no_did_not_run_cause(tmp_path: Path) -> None:
    """The control: a build recording the cause unconditionally fails here."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo)

    _ = _hold(
        config=config, repo=repo, reader=_Reader(verdict=SpecChangeTierVerdict(item_class="bug"))
    )

    assert _unavailable_records(config=config) == ()


def test_the_marker_this_module_reads_is_the_one_the_package_exports() -> None:
    """Binds the literal above to the exported name, which the Red predates."""
    assert getattr(_spec_change_tier, "SPEC_CHANGE_TIER_UNAVAILABLE_MARKER") == _MARKER  # noqa: B009

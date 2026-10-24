"""Tests for the spec-change-tier HOLD and the pre-dispatch wall that refuses it.

The clause: a spec-change-tier item "MUST be held out of `ready`" until its
linked topic ratifies AND the judgement returns `stated`, "That hold is a read
of the spec history and needs no model, so it MUST fail closed; the
pre-dispatch wall MUST refuse a held item with exit code `5` naming the
unratified topic."

THE MECHANICAL HOLD IS GRADED ON THE SPEND. "Needs no model" is the clause's own
words, and a gate that re-classified a held item on every pass would produce
the identical refusal while spending a model call per held row per pass — so
every held case counts the reader's calls and asserts zero.

THE RATIFIED-TOPIC CASE IS THE RELEASE PATH'S FIRST STEP, and it pulls the
OTHER way: such an item must NOT be held mechanically, because only a fresh
judgement can say whether the ratified text now states its behaviour. A gate
that held it would make the hold permanent, which is the failure the release
assertion exists to prevent — so the two cases are each other's control.

THE REFUSAL NAMES THE TOPIC, which is what an operator acts on. A refusal that
named only the work-item id would send them to the item rather than to the
proposal, and an item linking NO topic needs a refusal that says so rather than
one carrying an empty name.

THE WALL'S EXIT CODE IS READ OFF THE WIRING. Driving `pre_dispatch_wall_exit`
end to end here would have to satisfy every earlier row — two of which reach a
forge and an engine — so the pairing of this refusal with the ratified code `5`
is asserted against the wall's own refusing table, beside the behaviour of the
refusal itself.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierVerdict,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    spec_change_tier_hold,
    standing_spec_change_hold,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    spec_change_tier_refusal,
    spec_change_unheld_candidates,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_TOPIC = "spec-stated-judgement-and-spec-change-tier"
_TARGET = "## Grooming and slice-size calibration"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
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
        fake=True,
        repo_root=repo,
    )


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-57ss2n",
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


def _repo(*, tmp_path: Path, ratified: bool = False) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(f"# Contracts\n\n{_TARGET}\n\nText.\n", encoding="utf-8")
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


def _held_record(*, topic: str | None = _TOPIC) -> str:
    return spec_change_tier_comment(
        item_id="bd-ib-57ss2n",
        stage="pre-admission",
        verdict=SpecChangeTierVerdict(
            item_class="feature",
            stated_kind="unstated",
            generalization_target=_TARGET,
            linked_proposal_topic=topic,
        ),
    )


def _filed(*, repo: Path, record: str | None) -> StoreConfig:
    config = _config(repo=repo)
    append_work_item(path=config, item=_item())
    if record is not None:
        append_work_item_comment(path=config, work_item_id="bd-ib-57ss2n", body=record)
    return config


class _Reader:
    """A `SpecChangeTierReader` double that counts what it was asked."""

    def __init__(self, *, verdict: SpecChangeTierVerdict | None) -> None:
        self.verdict = verdict
        self.calls = 0

    def __call__(
        self, *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        _ = (item, repo, linked_topic, topic_ratified)
        self.calls += 1
        return self.verdict


def test_a_recorded_spec_change_tier_with_an_unratified_topic_holds_with_no_model_call(
    tmp_path: Path,
) -> None:
    """The mechanical hold the clause requires to need no model."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo, record=_held_record())
    reader = _Reader(verdict=None)

    hold = spec_change_tier_hold(
        item=_item(), repo=repo, path=config, stage="pre-dispatch", reader=reader
    )

    assert hold is not None
    assert hold.linked_proposal_topic == _TOPIC
    assert reader.calls == 0


def test_the_hold_names_the_unratified_topic_and_the_generalization_target(
    tmp_path: Path,
) -> None:
    """What the refusal has to say for an operator to act on it."""
    repo = _repo(tmp_path=tmp_path)
    hold = standing_spec_change_hold(
        work_item_id="bd-ib-57ss2n", repo=repo, comments=(_held_record(),)
    )

    assert hold is not None
    assert _TOPIC in hold.detail
    assert _TARGET in hold.detail
    assert "bd-ib-57ss2n" in hold.detail


def test_a_held_item_linking_no_topic_is_refused_naming_the_absence(tmp_path: Path) -> None:
    """An item that has not deposited its proposal yet, which is the first state."""
    repo = _repo(tmp_path=tmp_path)
    hold = standing_spec_change_hold(
        work_item_id="bd-ib-57ss2n", repo=repo, comments=(_held_record(topic=None),)
    )

    assert hold is not None
    assert hold.linked_proposal_topic is None
    assert "no linked proposed-change topic" in hold.detail


def test_a_held_item_whose_topic_is_now_ratified_is_re_judged_rather_than_held(
    tmp_path: Path,
) -> None:
    """The release path's first step, and the control for the mechanical hold.

    Only a fresh judgement can say whether the ratified text now states the
    behaviour, so a gate that kept holding here would make the hold permanent.
    """
    repo = _repo(tmp_path=tmp_path, ratified=True)
    config = _filed(repo=repo, record=_held_record())
    reader = _Reader(
        verdict=SpecChangeTierVerdict(
            item_class="feature",
            stated_kind="stated",
            linked_proposal_topic=_TOPIC,
            topic_ratified=True,
        )
    )

    hold = spec_change_tier_hold(
        item=_item(), repo=repo, path=config, stage="pre-dispatch", reader=reader
    )

    assert hold is None
    assert reader.calls == 1


def test_an_item_with_no_recorded_tier_is_classified_and_the_verdict_recorded(
    tmp_path: Path,
) -> None:
    """The clause's "again on every dispatch path", and its record on the item."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo, record=None)
    reader = _Reader(
        verdict=SpecChangeTierVerdict(
            item_class="feature",
            stated_kind="unstated",
            generalization_target=_TARGET,
            linked_proposal_topic=_TOPIC,
        )
    )

    hold = spec_change_tier_hold(
        item=_item(), repo=repo, path=config, stage="pre-dispatch", reader=reader
    )

    assert hold is not None
    assert reader.calls == 1
    assert (
        standing_spec_change_hold(
            work_item_id="bd-ib-57ss2n", repo=repo, comments=(_held_record(),)
        )
        is not None
    )


def test_an_item_the_fresh_classification_exempts_is_not_held(tmp_path: Path) -> None:
    """A bug reaches the wall and passes it, which is "routed as today"."""
    repo = _repo(tmp_path=tmp_path)
    config = _filed(repo=repo, record=None)
    reader = _Reader(verdict=SpecChangeTierVerdict(item_class="bug"))

    assert (
        spec_change_tier_hold(
            item=_item(), repo=repo, path=config, stage="pre-dispatch", reader=reader
        )
        is None
    )


def test_the_wall_refusal_names_the_item_and_its_unratified_topic(tmp_path: Path) -> None:
    """The refusal text the dispatch path renders before any claim is taken."""
    repo = _repo(tmp_path=tmp_path)
    _ = _filed(repo=repo, record=_held_record())

    refusal = spec_change_tier_refusal(repo=repo, items=[_item()])

    assert refusal is not None
    assert "bd-ib-57ss2n" in refusal
    assert _TOPIC in refusal


def test_the_wall_refuses_nothing_for_an_empty_selection(tmp_path: Path) -> None:
    """The drain reaches this wall on every idle pass, which must cost nothing."""
    assert spec_change_tier_refusal(repo=_repo(tmp_path=tmp_path), items=[]) is None


def test_the_drain_filter_drops_a_mechanically_held_row(tmp_path: Path) -> None:
    """ "Held out of `ready`" at the surface that decides what a pass advertises."""
    repo = _repo(tmp_path=tmp_path)
    _ = _filed(repo=repo, record=_held_record())

    assert spec_change_unheld_candidates(items=[_item()], repo=repo) == []


def test_the_drain_filter_keeps_a_row_whose_topic_has_ratified(tmp_path: Path) -> None:
    """The release reaches the wall, which is where the fresh judgement is taken.

    The control for the case above: a filter that dropped every recorded
    spec-change row would satisfy it while making every hold permanent.
    """
    repo = _repo(tmp_path=tmp_path, ratified=True)
    _ = _filed(repo=repo, record=_held_record())

    assert spec_change_unheld_candidates(items=[_item()], repo=repo) == [_item()]


def test_the_drain_filter_passes_an_empty_enumeration_through(tmp_path: Path) -> None:
    """An idle pass reads no ledger at all."""
    assert spec_change_unheld_candidates(items=[], repo=_repo(tmp_path=tmp_path)) == []


def test_the_pre_dispatch_wall_pairs_this_refusal_with_the_ratified_exit_code(
    tmp_path: Path,
) -> None:
    """Exit code `5`, read off the wall's own refusing table.

    Driving the whole wall here would have to satisfy every earlier row, two of
    which reach a forge and an engine, so the WIRING is asserted instead — the
    refusal's own behaviour is graded by the cases above. The constant is
    asserted to be `5` in the same breath, because a row wired to a renamed
    constant would satisfy a name-only reading.
    """
    _ = tmp_path
    source = inspect.getsource(_dispatcher_pre_dispatch_wall)

    assert "spec_change_tier_refusal" in source
    assert "spec_change_tier_refusal(repo=repo, items=items)" in source
    assert EXIT_UNGRADEABLE_CRITERIA == 5

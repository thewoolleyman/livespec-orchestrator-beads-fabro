"""The arms of the spec-change-tier hold that a well-formed tenant cannot reach.

A sibling of `test_spec_change_tier_wall.py`, which carries the DECISION. These
are the degraded and exempt states both surfaces run inside a pass composed of
many others, so each one's wrong answer is a traceback or a silently emptied
queue rather than a visible refusal. They sit in their own module because they
were found by a coverage measurement taken after that module's Red was
authored, and a Red's test bytes are fixed across its Red-to-Green pair.

EVERY DEGRADED ARM IS PAIRED WITH A LEG THAT DOES HOLD. "The selection was not
refused" and "the row came back" are both satisfied by a build with the whole
tier removed, so each case runs over a store holding one recorded spec-change
classification and differs from the holding leg in exactly one input.

THE FALL-BACK ARM IS THE ONE THAT PULLS AGAINST THE RELEASE. A held item whose
topic has ratified is re-judged rather than held — but when that re-judgement
cannot be TAKEN, the recorded hold still stands, because a label is a standing
measurement an outage in the judging path does not retire. The clause's
fail-open covers the CLASSIFICATION of an unlabelled item, never the hold.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierVerdict,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    spec_change_tier_hold,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import (
    spec_change_tier_refusal,
    spec_change_unheld_candidates,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_TOPIC = "spec-stated-judgement-and-spec-change-tier"
_TARGET = "## Grooming and slice-size calibration"
_GROOM_VARIANT = "groom-cut"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
_GROOM_WORKFLOW_TOML = (
    '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n'
)


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


def _item(*, item_id: str = "bd-ib-57ss2n") -> WorkItem:
    return WorkItem(
        id=item_id,
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


def _spec_tree(*, repo: Path, ratified: bool) -> Path:
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(f"# Contracts\n\n{_TARGET}\n\nText.\n", encoding="utf-8")
    if ratified:
        directory = spec / "history" / "v205" / "proposed_changes"
        directory.mkdir(parents=True)
        _ = (directory / f"{_TOPIC}-revision.md").write_text(
            f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
        )
    return repo


def _connected_repo(*, tmp_path: Path, ratified: bool = False) -> Path:
    repo = _spec_tree(repo=tmp_path / "connected", ratified=ratified)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _unresolvable_repo(*, tmp_path: Path) -> Path:
    """A repository declaring no `connection.prefix` at all."""
    return _spec_tree(repo=tmp_path / "unresolvable", ratified=False)


def _groom_registering_repo(*, tmp_path: Path) -> Path:
    """A connected repository that also REGISTERS a groom-kind variant."""
    repo = _spec_tree(repo=tmp_path / "groom", ratified=False)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"workflows": {_GROOM_VARIANT: _GROOM_DIR}},
                }
            }
        ),
        encoding="utf-8",
    )
    variant = repo / _GROOM_DIR
    variant.mkdir(parents=True)
    _ = (variant / "workflow.toml").write_text(_GROOM_WORKFLOW_TOML, encoding="utf-8")
    return repo


def _held_record(*, item_id: str = "bd-ib-57ss2n") -> str:
    return spec_change_tier_comment(
        item_id=item_id,
        stage="pre-admission",
        verdict=SpecChangeTierVerdict(
            item_class="feature",
            stated_kind="unstated",
            generalization_target=_TARGET,
            linked_proposal_topic=_TOPIC,
        ),
    )


def _file_held(*, repo: Path, item_id: str = "bd-ib-57ss2n") -> StoreConfig:
    config = _config(repo=repo)
    append_work_item(path=config, item=_item(item_id=item_id))
    append_work_item_comment(path=config, work_item_id=item_id, body=_held_record(item_id=item_id))
    return config


class _Absent:
    """A `SpecChangeTierReader` double that can take no classification."""

    def __call__(
        self, *, item: WorkItem, repo: Path, linked_topic: str | None, topic_ratified: bool
    ) -> SpecChangeTierVerdict | None:
        _ = (item, repo, linked_topic, topic_ratified)
        return None


def test_an_item_whose_comment_sidecar_cannot_be_read_is_not_held(tmp_path: Path) -> None:
    """Nothing can be concluded about an item whose record cannot be reached.

    Paired with a filed item on the same store, so the case differs from the
    holding leg in nothing but whether the row exists to be read.
    """
    repo = _connected_repo(tmp_path=tmp_path)
    config = _file_held(repo=repo)

    assert (
        spec_change_tier_hold(
            item=_item(item_id="bd-ib-never-filed"),
            repo=repo,
            path=config,
            stage="pre-dispatch",
            reader=_Absent(),
        )
        is None
    )
    assert (
        spec_change_tier_hold(
            item=_item(), repo=repo, path=config, stage="pre-dispatch", reader=_Absent()
        )
        is not None
    )


def test_a_classification_that_cannot_run_leaves_a_recorded_hold_standing(
    tmp_path: Path,
) -> None:
    """A label is a standing measurement an outage in the judging path cannot retire.

    The topic HAS ratified here, so the mechanical hold has already stepped
    aside and the decision rests entirely on the fresh classification — which
    is exactly the state in which an absent one must not release the item.
    """
    repo = _connected_repo(tmp_path=tmp_path, ratified=True)
    config = _file_held(repo=repo)

    hold = spec_change_tier_hold(
        item=_item(), repo=repo, path=config, stage="pre-dispatch", reader=_Absent()
    )

    assert hold is not None
    assert hold.linked_proposal_topic == _TOPIC


def test_a_repository_with_no_resolvable_connection_refuses_nothing(tmp_path: Path) -> None:
    """No classification can be read from or written to such a repository."""
    assert (
        spec_change_tier_refusal(repo=_unresolvable_repo(tmp_path=tmp_path), items=[_item()])
        is None
    )


def test_a_repository_with_no_resolvable_connection_drops_no_row(tmp_path: Path) -> None:
    """The filter's own half of the same degradation."""
    repo = _unresolvable_repo(tmp_path=tmp_path)

    assert spec_change_unheld_candidates(items=[_item()], repo=repo) == [_item()]


def test_a_row_the_store_does_not_hold_is_kept_by_the_filter(tmp_path: Path) -> None:
    """An unreadable sidecar is the absence of evidence that a hold stands."""
    repo = _connected_repo(tmp_path=tmp_path)
    _ = _file_held(repo=repo)
    absent = _item(item_id="bd-ib-never-filed")

    assert spec_change_unheld_candidates(items=[absent], repo=repo) == [absent]
    assert spec_change_unheld_candidates(items=[_item()], repo=repo) == []


def test_a_groom_variant_target_is_exempt_at_both_surfaces(tmp_path: Path) -> None:
    """A groom target is not an implement-kind item, so the tier is out of scope.

    It carries a recorded spec-change classification, so a build without the
    exemption would both refuse its dispatch and drop it from the drain — which
    closes the groom door on exactly the decomposition that would retire the
    classification.
    """
    repo = _groom_registering_repo(tmp_path=tmp_path)
    config = _file_held(repo=repo)
    record_dispatch_workflow(path=config, work_item_id="bd-ib-57ss2n", workflow=_GROOM_VARIANT)

    assert spec_change_tier_refusal(repo=repo, items=[_item()]) is None
    assert spec_change_unheld_candidates(items=[_item()], repo=repo) == [_item()]


def test_an_unheld_row_lets_the_refusal_walk_on_to_the_next(tmp_path: Path) -> None:
    """The selection is scanned to its end, not stopped at its first clean row."""
    repo = _connected_repo(tmp_path=tmp_path)
    config = _config(repo=repo)
    append_work_item(path=config, item=_item(item_id="bd-ib-clean"))
    _ = _file_held(repo=repo)

    assert spec_change_tier_refusal(repo=repo, items=[_item(item_id="bd-ib-clean")]) is None
    refusal = spec_change_tier_refusal(repo=repo, items=[_item(item_id="bd-ib-clean"), _item()])

    assert refusal is not None
    assert "bd-ib-57ss2n" in refusal

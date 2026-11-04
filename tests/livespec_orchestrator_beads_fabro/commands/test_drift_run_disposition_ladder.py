"""The disposition ladder's two arms the queue-cap journey cannot reach.

A finding at the cap that NOTHING CAN HOLD is in neither tuple, which is what
leaves its merge unprocessed and stops the frontier there. The queue-cap
journey always commits an anchor, so it cannot observe this arm at all — and
the arm is the one that matters most, because reporting such a finding as held
would advance the frontier past a finding that exists nowhere.

And the attention lane EMPTIES once a held finding is filed, which the journey
cannot observe either: the hold records are append-only, so without this
subtraction a filed finding would sit in the operator's inbox for ever with no
act that could clear it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._drift_run_disposition import (
    DispositionContext,
    dispose_findings,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding
from livespec_orchestrator_beads_fabro.commands._drift_run_held import record_held_finding
from livespec_orchestrator_beads_fabro.commands._needs_attention_held_drift_findings import (
    HELD_DRIFT_FINDINGS_KEY,
    held_drift_finding_items,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_ANCHOR = "bd-ib-anchor"
_IDENTITY = "drift-aaaa"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> Iterator[None]:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="t", prefix="bd-ib", server_user="u", database="d", bd_path="bd", fake=True
    )


def _finding() -> DriftFinding:
    return DriftFinding(
        merge="aaaaaaa1",
        kind="unstated",
        generalization_target="## H",
        statement="a behaviour",
        rationale="because",
        identity=_IDENTITY,
    )


def _seed_anchor() -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_ANCHOR,
            type="task",
            status="backlog",
            title="anchor",
            description="d",
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-01T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            blocked_reason=None,
            factory_safety=None,
            admission_policy=None,
            acceptance_policy=None,
            spec_commitment_hint=None,
        ),
    )


def _spec_root(*, root: Path, open_proposals: int = 0, filed_identity: str | None = None) -> Path:
    spec_root = root / "SPECIFICATION"
    (spec_root / "proposed_changes").mkdir(parents=True)
    (spec_root / "history" / "v001" / "proposed_changes").mkdir(parents=True)
    for index in range(open_proposals):
        _ = (spec_root / "proposed_changes" / f"drift-existing{index}.md").write_text(
            f"---\ndrift_origin: dispatcher-drift-run\n"
            f"finding_identity: drift-existing{index}\n---\n\nbody\n",
            encoding="utf-8",
        )
    if filed_identity is not None:
        _ = (spec_root / "proposed_changes" / f"{filed_identity}.md").write_text(
            f"---\ndrift_origin: dispatcher-drift-run\n"
            f"finding_identity: {filed_identity}\n---\n\nbody\n",
            encoding="utf-8",
        )
    return spec_root


def _context(*, spec_root: Path, anchor: str | None, cap: int) -> DispositionContext:
    return DispositionContext(
        spec_root=spec_root,
        spec_tree={"contracts.md": "## H\n"},
        config=_config(),
        anchor=anchor,
        cap=cap,
        author="a",
        now=lambda: "2026-10-22T00:00:00Z",
    )


def test_a_finding_at_the_cap_that_cannot_be_held_is_in_neither_tuple(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path, open_proposals=1)

    disposition = dispose_findings(
        findings=[_finding()], context=_context(spec_root=spec_root, anchor=None, cap=1)
    )

    assert disposition.filed == ()
    assert disposition.held == ()
    # And nothing was filed either: a finding nobody can hold must not fall
    # through into the queue the cap exists to bound.
    assert sorted(path.name for path in (spec_root / "proposed_changes").glob("*.md")) == [
        "drift-existing0.md"
    ]


def test_the_attention_lane_is_empty_when_nothing_is_held(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path)
    _seed_anchor()

    composed = held_drift_finding_items(
        project_root=tmp_path,
        spec_root=spec_root,
        repo="repo",
        config=_config(),
        anchor=_ANCHOR,
    )

    assert composed == []


def test_a_held_finding_that_has_since_been_filed_is_no_longer_listed(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path, filed_identity=_IDENTITY)
    _seed_anchor()
    assert record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding()) is True

    composed = held_drift_finding_items(
        project_root=tmp_path,
        spec_root=spec_root,
        repo="repo",
        config=_config(),
        anchor=_ANCHOR,
    )

    # The hold record still stands — comments cannot be deleted — so only the
    # subtraction of the filed set keeps this out of the operator's inbox.
    assert [item.id for item in composed] == []


def test_a_still_held_finding_is_listed_with_its_merge(tmp_path: Path) -> None:
    spec_root = _spec_root(root=tmp_path)
    _seed_anchor()
    _ = record_held_finding(path=_config(), anchor=_ANCHOR, finding=_finding())

    composed = held_drift_finding_items(
        project_root=tmp_path,
        spec_root=spec_root,
        repo="repo",
        config=_config(),
        anchor=_ANCHOR,
    )

    assert [item.id for item in composed] == [f"hygiene:{HELD_DRIFT_FINDINGS_KEY}:repo"]
    assert "aaaaaaa1" in composed[0].summary

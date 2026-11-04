"""Scenario 41 — standalone analysis lands in a plan, not a root research tree.

Binds `SPECIFICATION/scenarios.md` "## Scenario 41 — standalone analysis lands
in a plan, not a root research tree" at the integration tier: the plan package's
own `create_thread` primitive is driven through its REAL store seam against the
in-memory `FakeBeadsClient`, and the FILESYSTEM it leaves behind is the
assertion. Nothing here stands in for the write it is grading.

THE MEASUREMENT IS THE WHOLE TREE, not the one path the primitive reports back.
Its return value names the note it wrote, so an assertion that read only that
field would pass for a call that ALSO re-accreted a root `research/` tree beside
it, or dropped a live `handoff.md` into the plan directory — the two placements
the retired-research-tree invariant and the no-mutable-plan-state rule exist to
forbid. Both are ADDITIONS the reported path cannot mention, so the sweep below
compares the tree the call created against the exact set the scenario permits,
and each forbidden placement is ALSO named on its own so a refusal says which
half of the invariant broke rather than merely that a set differed.

WRITE-ONCE IS GRADED BY A SECOND CALL, because write-once is a property of the
SECOND write rather than of the first. A first write lands identically whether
the mode is exclusive or truncating, so a single-call test reports a primitive
that silently overwrites recorded analysis as conforming.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands.plan import create_thread
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    from pathlib import Path

# The scenario's own slug, verbatim: `plan/t/research/` is the placement its
# Gherkin names, so the fixture answers to the same handle.
_SLUG = "t"
_RESEARCH_FILENAME = "001-standalone-analysis.md"
_RESEARCH_TEXT = "The standalone analysis this maintainer recorded.\n"

# Every path the scenario permits `create_thread` to create, relative to the
# project root. The anchor is IN the set because it is a re-derivable POINTER to
# the plan's epic rather than plan state: it is itself write-once, mirrors no
# children, status, handoff, readiness or archive fact, and the plan-identity
# contract requires it. Nothing else may appear.
_PERMITTED_CREATED_PATHS = frozenset(
    {
        "plan",
        "plan/t",
        "plan/t/associated_work_item_id",
        "plan/t/research",
        f"plan/t/research/{_RESEARCH_FILENAME}",
    }
)

# The mutable plan-state files the scenario names outright. Checked by name as
# well as through the set sweep, so a refusal reads as "a live handoff was
# created" rather than as an unexplained set difference.
_FORBIDDEN_PLAN_STATE_FILENAMES = ("handoff.md", "supervisor-handoff.md")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _definition_of_done() -> PlanDefinitionOfDone:
    return PlanDefinitionOfDone(
        statement="Done when standalone analysis is recorded in the plan store.",
        assertions=("The recorded analysis lands as write-once plan research.",),
    )


def _record_standalone_analysis(*, project_root: Path) -> dict[str, str]:
    """Record standalone analysis for the scenario's slug through the plan package."""
    return create_thread(
        project_root=project_root,
        config=_config(),
        slug=_SLUG,
        title="Standalone analysis placement",
        research_filename=_RESEARCH_FILENAME,
        research_text=_RESEARCH_TEXT,
        now="2026-10-24T09:00:00Z",
        definition_of_done=_definition_of_done(),
    )


def _relative_paths(*, project_root: Path) -> frozenset[str]:
    """Every path under the project root, as posix paths relative to it."""
    return frozenset(path.relative_to(project_root).as_posix() for path in project_root.rglob("*"))


def test_scenario41_standalone_analysis_lands_as_write_once_plan_research(
    tmp_path: Path,
) -> None:
    """The note lands under `plan/t/research/` and a second write is refused."""
    reset_fake_singleton()

    created = _record_standalone_analysis(project_root=tmp_path)

    note = tmp_path / "plan" / _SLUG / "research" / _RESEARCH_FILENAME
    assert created["research_path"] == f"plan/{_SLUG}/research/{_RESEARCH_FILENAME}"
    assert note.is_file()
    assert _RESEARCH_TEXT in note.read_text(encoding="utf-8")
    # Write-once: the recorded analysis is refused a second writer rather than
    # being replaced, and the bytes already on disk survive the refusal.
    with pytest.raises(FileExistsError):
        _ = _record_standalone_analysis(project_root=tmp_path)
    assert _RESEARCH_TEXT in note.read_text(encoding="utf-8")


def test_scenario41_no_root_research_tree_is_created_anywhere(tmp_path: Path) -> None:
    """The retired root `research/` tree does not re-accrete beside the plan."""
    reset_fake_singleton()

    _ = _record_standalone_analysis(project_root=tmp_path)

    assert not (tmp_path / "research").exists()
    research_directories = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("research")
        if path.is_dir()
    )
    assert research_directories == [f"plan/{_SLUG}/research"]


def test_scenario41_no_mutable_plan_state_file_is_created(tmp_path: Path) -> None:
    """No live handoff, supervisor handoff, or other mutable plan-state file appears."""
    reset_fake_singleton()

    _ = _record_standalone_analysis(project_root=tmp_path)

    plan_directory = tmp_path / "plan" / _SLUG
    for filename in _FORBIDDEN_PLAN_STATE_FILENAMES:
        assert not (plan_directory / filename).exists()
    # The set sweep is what covers "or any other mutable plan-state file": a
    # placement nobody thought to name by hand still has to be absent.
    assert _relative_paths(project_root=tmp_path) == _PERMITTED_CREATED_PATHS

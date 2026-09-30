"""The shared acceptance-eligibility decision filters EVERY candidate enumeration.

The `next` ranking algorithm of `SPECIFICATION/contracts.md` makes the shared
variant-aware acceptance-eligibility decision step 1 of candidate identification,
and names the four surfaces that MUST consume "this same filtered set so none can
advertise an `impl:<id>` action the wall will refuse": `next`, the
`needs-attention` implementation item composed from `next`, the idle-factory
handoff, and the Dispatcher drain. The pre-dispatch-wall clause states the
migration posture for the population that predates the wall — an affected physical
`ready` row "stays in place, is excluded from every dispatch-candidate
enumeration, and is surfaced by the `hygiene:unrunnable-acceptance:<work-item-id>`
fact until repaired" — and the idle-factory clause repeats it for its own count,
first-ranked id and handoff.

THIS FILE IS THE WIRING TEST, not a second copy of the decision's own tests.
`test_dispatcher_acceptance_eligibility.py` owns what the decision DECIDES; what
is asserted here is that each enumeration consumes it, which is a different
failure: a surface that never asks the question looks completely healthy from
inside the decision's own tests.

EVERY EXCLUSION ASSERTION IS PAIRED WITH AN ADMITTING CONTROL on the same
surface, with only the Definition of Done section differing. A filter that
excluded everything would satisfy every exclusion assertion here perfectly, and
from the exclusion side alone that is indistinguishable from a working filter.

WHY THE DRAIN IS ASSERTED AT ITS SELECTION SEAM. The wall already refuses a
malformed item with exit 5 for the hand-picked `dispatch --item` path, and it
stays in place; what the migration clause adds is that the AUTONOMOUS enumeration
never selects such a row in the first place. Those are different behaviours of one
command, and only the selection seam can tell them apart: an exit code cannot say
whether the wave was empty or refused.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import candidates
from livespec_orchestrator_beads_fabro.commands._needs_attention_idle_factory import (
    idle_factory_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_unrunnable_acceptance import (
    unrunnable_acceptance_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import impl_next
from livespec_orchestrator_beads_fabro.commands.next import main as next_main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.cross_repo.types import CrossRepoManifest

_SPEC_HEADING = "## Effective acceptance criteria"
_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The candidate enumerations consume the shared eligibility decision.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)
_UNRUNNABLE_ID = "bd-ib-nodod"
_CONFORMING_ID = "bd-ib-hasdod"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, id_: str, rank: str = "a1", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-09-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _project(root: Path) -> Path:
    """A governed project root: a connection block, a wip cap, and a spec tree."""
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib", "fake": True},
                    "dispatcher": {"wip_cap": 5},
                }
            }
        ),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text("", encoding="utf-8")
    return root


def _next_payload(*, project_root: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    rc = next_main(argv=["--json", "--project-root", str(project_root)])
    assert rc == 0
    return json.loads(capsys.readouterr().out)


def _drain_args(*, requested: list[str] | None = None) -> argparse.Namespace:
    return argparse.Namespace(items=requested, workflow_name=None)


# --- `next` ------------------------------------------------------------------


def test_next_excludes_a_ready_item_that_carries_no_definition_of_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_root = _project(tmp_path)
    append_work_item(path=_config(), item=_item(id_=_UNRUNNABLE_ID))

    payload = _next_payload(project_root=project_root, capsys=capsys)

    assert payload["candidates"] == []
    # The pagination total is the FULL ranked count before slicing, so an
    # excluded row that still counted would advertise work that is not there.
    assert payload["pagination"] == {"offset": 0, "limit": 5, "total": 0, "has_more": False}


def test_next_keeps_a_ready_item_carrying_a_valid_definition_of_done(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The discriminating control for the exclusion above.
    project_root = _project(tmp_path)
    append_work_item(path=_config(), item=_item(id_=_CONFORMING_ID, description=_SECTION))

    payload = _next_payload(project_root=project_root, capsys=capsys)

    refs = [candidate["work_item_ref"] for candidate in payload["candidates"]]  # pyright: ignore[reportIndexIssue, reportGeneralTypeIssues]
    assert refs == [_CONFORMING_ID]
    assert payload["pagination"] == {"offset": 0, "limit": 5, "total": 1, "has_more": False}


def test_next_ranks_only_the_conforming_row_when_both_rest_in_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The unrunnable row outranks the conforming one, so a surface that filtered
    # only the FIRST candidate, or filtered after slicing, still passes the two
    # single-item cases above and fails here.
    project_root = _project(tmp_path)
    append_work_item(path=_config(), item=_item(id_=_UNRUNNABLE_ID, rank="a1"))
    append_work_item(
        path=_config(), item=_item(id_=_CONFORMING_ID, rank="a2", description=_SECTION)
    )

    payload = _next_payload(project_root=project_root, capsys=capsys)

    refs = [candidate["work_item_ref"] for candidate in payload["candidates"]]  # pyright: ignore[reportIndexIssue, reportGeneralTypeIssues]
    assert refs == [_CONFORMING_ID]


# --- the `needs-attention` implementation item composed from `next` -----------


def test_the_implementation_item_is_not_composed_from_an_unrunnable_row(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)

    composed = impl_next(
        project_root=project_root,
        items=[_item(id_=_UNRUNNABLE_ID)],
        manifest=CrossRepoManifest(targets={}),
    )

    assert composed is None


def test_the_implementation_item_is_composed_from_a_conforming_row(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)

    composed = impl_next(
        project_root=project_root,
        items=[_item(id_=_CONFORMING_ID, description=_SECTION)],
        manifest=CrossRepoManifest(targets={}),
    )

    assert composed is not None
    assert composed.work_item == _CONFORMING_ID


# --- the Dispatcher drain ----------------------------------------------------


def test_the_autonomous_drain_does_not_select_an_unrunnable_row(tmp_path: Path) -> None:
    project_root = _project(tmp_path)

    selected = candidates(
        args=_drain_args(),
        items=[_item(id_=_UNRUNNABLE_ID)],
        repo=project_root,
    )

    assert [item.id for item in selected] == []


def test_the_autonomous_drain_selects_a_conforming_row(tmp_path: Path) -> None:
    project_root = _project(tmp_path)

    selected = candidates(
        args=_drain_args(),
        items=[_item(id_=_CONFORMING_ID, description=_SECTION)],
        repo=project_root,
    )

    assert [item.id for item in selected] == [_CONFORMING_ID]


def test_an_explicitly_requested_row_still_reaches_the_wall(tmp_path: Path) -> None:
    # The clause keeps the refusal for a hand-picked dispatch "even when candidate
    # enumerations filtered the item earlier", so a NAMED id is narrowed to and
    # left for the wall to refuse with exit 5 rather than silently dropped: a
    # dropped id would report the factory as having nothing to do.
    project_root = _project(tmp_path)

    selected = candidates(
        args=_drain_args(requested=[_UNRUNNABLE_ID]),
        items=[_item(id_=_UNRUNNABLE_ID)],
        repo=project_root,
    )

    assert [item.id for item in selected] == [_UNRUNNABLE_ID]


# --- the idle-factory handoff ------------------------------------------------


def test_the_idle_factory_handoff_excludes_an_unrunnable_row(tmp_path: Path) -> None:
    project_root = _project(tmp_path)

    attention = idle_factory_items(
        project_root=project_root,
        repo="repo",
        items=[_item(id_=_UNRUNNABLE_ID)],
    )

    assert attention == []


def test_the_idle_factory_handoff_names_the_conforming_row(tmp_path: Path) -> None:
    project_root = _project(tmp_path)

    attention = idle_factory_items(
        project_root=project_root,
        repo="repo",
        items=[
            _item(id_=_UNRUNNABLE_ID, rank="a1"),
            _item(id_=_CONFORMING_ID, rank="a2", description=_SECTION),
        ],
    )

    assert len(attention) == 1
    fact = attention[0]
    # The count, the first-ranked id and the handoff all read off the FILTERED
    # set, so the excluded row may not appear in any of the three.
    assert "1 admission-eligible" in fact.summary
    assert _UNRUNNABLE_ID not in fact.summary
    assert fact.handoff.action_id == f"impl:{_CONFORMING_ID}"


# --- the fact that keeps the excluded row visible ----------------------------


def test_exactly_one_fact_names_the_missing_definition_of_done_section(
    tmp_path: Path,
) -> None:
    project_root = _project(tmp_path)

    facts = unrunnable_acceptance_items(
        project_root=project_root,
        repo="repo",
        items=[_item(id_=_UNRUNNABLE_ID)],
    )

    assert len(facts) == 1
    fact = facts[0]
    assert fact.id == f"hygiene:unrunnable-acceptance:{_UNRUNNABLE_ID}"
    assert "Definition of Done" in fact.summary
    # The excluded row is not merely absent from the queue: it is REPORTED, and
    # the handoff is the repair, never an `impl:` the wall would refuse.
    assert fact.handoff.action_id is None

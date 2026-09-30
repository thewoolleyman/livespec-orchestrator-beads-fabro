"""Tests for the unrunnable-acceptance hygiene fact (v111, widened by v114).

The orchestrator-owned-attention-facts clause of `SPECIFICATION/contracts.md`
requires exactly one stable hygiene fact per item that physically rests in
`ready` while FAILING the shared variant-aware acceptance-eligibility decision.
The fact's summary must identify the item as `UNRUNNABLE`, report the resolved
criteria source and gradeable-assertion count, and name the three remedies —
author the Definition of Done section, author gradeable criteria by groom or
edit, or deliberately select `human-only`. Its handoff must be a non-dispatch
inspection or repair handoff and must NOT carry `impl:<work-item-id>`.

THE `human-only` RULE IS THE ONE WITH A TRAP IN IT. `human-only` produces the
fact when, and ONLY when, its Definition of Done section is absent or carries no
valid reference line — never on the gradeable-assertion count alone, because the
human owns that grading. The two cases look identical from the outside (a
`human-only` row in `ready`), so both are asserted here: an implementation that
fired on either would pass a one-sided test and then flood the lane with every
deliberately human-graded item in the tenant.

The fact CONSUMES the shared decision rather than re-deriving eligibility, which
is why the eligible-item and groom-kind controls matter: a lane that re-derived
the rule could agree with the decision on the failing case and disagree on the
passing one, and nothing in the fact's own output would show it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._needs_attention_unrunnable_acceptance import (
    unrunnable_acceptance_items,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REPO_NAME = "livespec-orchestrator-beads-fabro"
_SPEC_HEADING = "## Effective acceptance criteria"
_SECTION = (
    "## Definition of Done\n"
    "\n"
    "- The lane reports an unrunnable ready item exactly once.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)
_EMPTY_SECTION = f"## Definition of Done\n\nReferences: {_SPEC_HEADING}\n"


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-unrunnable",
        type="task",
        status="ready",
        title="A ready but unrunnable task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
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
    return replace(base, **overrides)


def _repo(*, tmp_path: Path) -> Path:
    # Idempotent: a case that probes the lane twice over one `tmp_path` builds the
    # same repository twice, and a second `mkdir` that raised would fail the test
    # for a fixture fault rather than for the behaviour under test.
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib",'
        ' "fake": true}}}',
        encoding="utf-8",
    )
    spec = repo / "SPECIFICATION"
    spec.mkdir(exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _facts(*, tmp_path: Path, items: list[WorkItem]) -> list[object]:
    return unrunnable_acceptance_items(
        project_root=_repo(tmp_path=tmp_path), repo=_REPO_NAME, items=items
    )


def test_a_ready_item_with_no_section_produces_exactly_one_stable_fact(
    tmp_path: Path,
) -> None:
    facts = _facts(tmp_path=tmp_path, items=[_item()])

    assert len(facts) == 1
    fact = facts[0]
    assert fact.id == "hygiene:unrunnable-acceptance:bd-ib-unrunnable"
    assert fact.kind == "hygiene"


def test_the_summary_identifies_the_item_and_names_all_three_remedies(
    tmp_path: Path,
) -> None:
    summary = str(_facts(tmp_path=tmp_path, items=[_item()])[0].summary)

    assert "bd-ib-unrunnable" in summary
    assert "UNRUNNABLE" in summary
    # The resolved source and the gradeable-assertion count, so an operator can
    # tell an item with NO criteria from one whose criteria live in a legacy
    # place — a different repair in each case.
    assert "description-exit-criteria" in summary
    assert "0 gradeable" in summary
    assert "Definition of Done" in summary
    assert "groom" in summary
    assert "human-only" in summary


def test_the_handoff_is_not_a_dispatch(tmp_path: Path) -> None:
    # The clause forbids `impl:<work-item-id>` outright: the Dispatcher would
    # refuse this very item, so a dispatch handoff hands the operator a command
    # that cannot succeed and reads as the factory being broken.
    handoff = _facts(tmp_path=tmp_path, items=[_item()])[0].handoff

    command = str(handoff.command)
    assert "impl:bd-ib-unrunnable" not in command
    assert getattr(handoff, "action_id", None) is None


def test_an_eligible_ready_item_produces_no_fact(tmp_path: Path) -> None:
    # The control. Without it, every assertion above is equally consistent with a
    # lane that reports every ready item in the tenant.
    assert _facts(tmp_path=tmp_path, items=[_item(description=_SECTION)]) == []


def test_an_item_that_has_left_ready_produces_no_fact(tmp_path: Path) -> None:
    # "Physically rests in `ready`" is the trigger, so the fact clears when the
    # item moves — including to `active`, where the dispatch walls no longer gate.
    assert _facts(tmp_path=tmp_path, items=[_item(status="active")]) == []
    assert _facts(tmp_path=tmp_path, items=[_item(status="backlog")]) == []


def test_a_human_only_item_with_no_section_produces_the_fact(tmp_path: Path) -> None:
    facts = _facts(tmp_path=tmp_path, items=[_item(acceptance_policy="human-only")])

    assert len(facts) == 1


def test_a_human_only_item_produces_no_fact_on_the_assertion_count_alone(
    tmp_path: Path,
) -> None:
    # The trap. This item's section is PRESENT and its reference resolves; it
    # simply has no gradeable assertion, which for `human-only` is not a fault —
    # the human, not the AI pass, owns that grading.
    item = _item(acceptance_policy="human-only", description=_EMPTY_SECTION)

    assert _facts(tmp_path=tmp_path, items=[item]) == []


def test_an_ai_dispositive_item_does_produce_the_fact_on_the_assertion_count(
    tmp_path: Path,
) -> None:
    # The discriminating twin of the case above: SAME description, different
    # policy. Without this pair, "no fact" is equally consistent with a lane that
    # never fires on an empty section at all.
    item = _item(acceptance_policy="ai-only", description=_EMPTY_SECTION)

    assert len(_facts(tmp_path=tmp_path, items=[item])) == 1


def test_the_lane_reports_one_fact_per_offending_item(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path=tmp_path,
        items=[
            _item(),
            _item(id="bd-ib-second"),
            _item(id="bd-ib-fine", description=_SECTION),
        ],
    )

    assert sorted(str(fact.id) for fact in facts) == [
        "hygiene:unrunnable-acceptance:bd-ib-second",
        "hygiene:unrunnable-acceptance:bd-ib-unrunnable",
    ]

"""Tests for the advisory-Definition-of-Done hygiene lane (v115).

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
asks for this lane in one sentence: "`needs-attention` SHOULD surface, as hygiene
facts, each `ready` item carrying an advisory Definition-of-Done finding, so that
it is repaired before a sandbox is spent on it."

WHY THE LANE NEEDS ITS OWN ROW RATHER THAN RIDING THE UNRUNNABLE ONE. An advisory
finding does NOT make the item ineligible — the clause forbids it from
withholding `ready` — so the `hygiene:unrunnable-acceptance` fact, which fires on
the shared eligibility decision refusing the item, is structurally incapable of
reporting one. An item with an advisory finding is silent on every other lane in
the snapshot, which is exactly the state this row exists to end.

WHY THE MODULE IS IMPORTED INSIDE EACH TEST BODY. A top-level import of a module
that does not exist yet makes the Red a COLLECTION error, which proves only
unimportability. The shape case asserts the module path first, which fails as a
genuine assertion.

WHY THE CONTROLS ARE THE SAME ITEM WITH ONE ELEMENT CHANGED. A lane that reported
every `ready` item would satisfy the positive case on its own. Each clearing case
differs from the positive one in exactly one element: the status, or the
reference line that makes the finding advisory in the first place.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    DodJudgement,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._needs_attention_definition_of_done"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_needs_attention_definition_of_done.py"
)

_REPO_NAME = "livespec-orchestrator-beads-fabro"
_SPEC_HEADING = "## Effective acceptance criteria"
_SCENARIO_HEADING = (
    "## Scenario 999 — The dispatcher refuses an unresolvable workflow variant"
    " before claiming the item"
)
_GOVERNED_ASSERTION = (
    "The dispatcher refuses an unresolvable workflow variant before claiming the item."
)


def _section(*, references: str) -> str:
    return f"## Definition of Done\n\n- {_GOVERNED_ASSERTION}\n\nReferences: {references}\n"


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-advisory",
        type="task",
        status="ready",
        title="A ready item with an advisory finding",
        description=_section(references=_SPEC_HEADING),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _repo(*, tmp_path: Path) -> Path:
    """A repository whose spec tree carries BOTH a generic H2 and a scenario H2.

    Both are needed: the generic one so the reference line RESOLVES (otherwise the
    item carries a mechanical finding instead and the advisory one is beside the
    point), and the scenario one so a candidate exists to be named.
    """
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    spec = repo / "SPECIFICATION"
    spec.mkdir(exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_SCENARIO_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _facts(*, tmp_path: Path, items: list[WorkItem]) -> list[object]:
    module = importlib.import_module(_MODULE)
    return module.advisory_definition_of_done_items(
        project_root=_repo(tmp_path=tmp_path), repo=_REPO_NAME, items=items
    )


def test_the_lane_is_a_module_of_its_own_exporting_one_public_name() -> None:
    """The shape case, whose first assertion fails before any import is reached."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    # The held lane is this module's second public name, added with the
    # pre-admission and pre-dispatch Definition-of-Done judgement: both lanes
    # report on the same clause's findings and read the same item record, so
    # they are neighbours here rather than a module apart.
    assert module.__all__ == [
        "advisory_definition_of_done_items",
        "held_definition_of_done_items",
    ]


def test_a_ready_item_with_an_advisory_finding_produces_exactly_one_stable_fact(
    tmp_path: Path,
) -> None:
    facts = _facts(tmp_path=tmp_path, items=[_item()])

    assert len(facts) == 1
    fact = facts[0]
    assert fact.id == "hygiene:advisory-definition-of-done:bd-ib-advisory"
    assert fact.kind == "hygiene"


def test_the_summary_names_the_item_and_its_advisory_finding(tmp_path: Path) -> None:
    """The fact has to carry the finding, not merely say one exists.

    An operator handed "this item has an advisory finding" has to go and re-derive
    which one, and the two recognised forms want different edits.
    """
    summary = str(_facts(tmp_path=tmp_path, items=[_item()])[0].summary)

    assert "bd-ib-advisory" in summary
    assert _SCENARIO_HEADING[len("## ") :] in summary


def test_the_handoff_is_not_a_dispatch(tmp_path: Path) -> None:
    """An advisory item IS dispatchable, so the handoff must still be the repair.

    The row exists to get the item repaired "before a sandbox is spent on it", and
    a dispatch handoff is the one command that spends the sandbox instead.
    """
    handoff = _facts(tmp_path=tmp_path, items=[_item()])[0].handoff

    assert "impl:bd-ib-advisory" not in str(handoff.command)
    assert getattr(handoff, "action_id", None) is None


def test_an_item_whose_reference_names_the_scenario_produces_no_fact(tmp_path: Path) -> None:
    """The control: the same item, with the governing scenario on its reference line."""
    assert (
        _facts(tmp_path=tmp_path, items=[_item(description=_section(references=_SCENARIO_HEADING))])
        == []
    )


def test_an_item_that_has_left_ready_produces_no_fact(tmp_path: Path) -> None:
    """The clause scopes the row to `ready`, which is where a sandbox is next spent."""
    assert _facts(tmp_path=tmp_path, items=[_item(status="backlog")]) == []
    assert _facts(tmp_path=tmp_path, items=[_item(status="active")]) == []


def test_the_lane_reports_one_fact_per_offending_item(tmp_path: Path) -> None:
    facts = _facts(
        tmp_path=tmp_path,
        items=[
            _item(),
            _item(id="bd-ib-second"),
            _item(id="bd-ib-fine", description=_section(references=_SCENARIO_HEADING)),
        ],
    )

    assert sorted(str(fact.id) for fact in facts) == [
        "hygiene:advisory-definition-of-done:bd-ib-advisory",
        "hygiene:advisory-definition-of-done:bd-ib-second",
    ]


def test_the_snapshot_composition_carries_the_lane(tmp_path: Path) -> None:
    """The lane has to be WIRED, not merely written.

    A module nothing calls satisfies every case above while the snapshot an
    operator actually reads carries no such row — the failure mode a per-lane test
    cannot see. The composition module is read as source here rather than driven,
    because driving the whole snapshot needs a live tenant; the end-to-end leg
    belongs to the Scenario-140 integration binding.
    """
    _ = tmp_path
    composition = Path(
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/needs_attention.py"
    ).read_text(encoding="utf-8")

    assert "_needs_attention_definition_of_done" in composition
    assert "advisory_definition_of_done_items(" in composition
    # Its neighbour, added with the pre-admission and pre-dispatch judgement.
    assert "held_definition_of_done_items(" in composition


def _executing_rubric_digest() -> str:
    """The digest of the EXECUTING build's rubric, which the held lane reads.

    Taken off the shipped file rather than written as a literal: the lane reads
    the executing payload, so a verdict standing against any other rubric is one
    it would correctly refuse to reuse — and this case's subject is what the lane
    does with a verdict that DOES stand.
    """
    rubric = judgement_rubric()
    assert rubric is not None
    return rubric_digest(rubric=rubric)


def test_the_held_lane_reports_nothing_when_no_ledger_connection_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A snapshot composed from many lanes must not raise out of this one.

    The held lane reads a STANDING verdict off the item's comment sidecar, so a
    repository declaring no `connection.prefix` is one no verdict can be read
    from. The clause's own requirement when the judgement cannot run is that the
    item be treated as it would be without it, and `needs-attention` runs over
    the whole tenant — so an unresolvable connection raising from here would
    take down every other lane in the snapshot with it.

    THE CONTROL IS THE SAME ITEM AND THE SAME RECORDED VERDICT read through a
    repository that DOES declare a connection. Without it, the empty answer is
    equally consistent with a lane that reports nothing for any item, which is
    what a build with the lane removed would also produce.
    """
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    module = importlib.import_module(_MODULE)
    connected = _repo(tmp_path=tmp_path)
    _ = (connected / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    item = _item(description=_section(references=_SCENARIO_HEADING))
    config = StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=connected,
    )
    append_work_item(path=config, item=item)
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=verdict_comment(
            item_id=item.id,
            stage=STAGE_PRE_DISPATCH,
            digest=judgement_subject_digest(item=item, cwd=connected),
            rubric_digest=_executing_rubric_digest(),
            judgement=DodJudgement(
                outcome=JUDGEMENT_HELD,
                findings=("bd-ib-advisory: restate assertion 1 as behaviour.",),
            ),
        ),
    )

    held = module.held_definition_of_done_items(
        project_root=connected, repo=_REPO_NAME, items=[item]
    )
    # The same spec tree with no `.livespec.jsonc` beside it, so the digest the
    # verdict was recorded against is unchanged and only the connection differs.
    bare = tmp_path / "bare"
    bare.mkdir()
    unresolvable = module.held_definition_of_done_items(
        project_root=_repo(tmp_path=bare), repo=_REPO_NAME, items=[item]
    )
    reset_fake_singleton()

    assert len(held) == 1
    assert "restate assertion 1 as behaviour." in str(held[0].summary)
    assert unresolvable == []

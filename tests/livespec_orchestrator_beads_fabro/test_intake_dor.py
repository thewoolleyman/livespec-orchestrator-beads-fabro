"""Paired coverage for intake Definition-of-Ready routing evaluation.

The `evaluate` cases cover the pure six-gate verdict. The rest bind the v115
filing-time duty the Definition-of-Done-and-Proof-of-Done clause of
`SPECIFICATION/contracts.md` adds to the same primitive: "A MECHANICAL finding
... withholds `ready`: an item filed with one outstanding MUST NOT be routed to
`ready` by intake. A test-existence or scenario-reference finding the wall
recognises is ADVISORY: it MUST be displayed and MUST NOT withhold `ready` ...
Either kind MUST be recorded on the filed item as a ledger comment, so it is
repaired where it was made."

WHY THE COMMENTS ARE READ BACK THROUGH THE COMMENT VERB. `bd show --json` carries
`comment_count` and no bodies at all, so verifying an append through it reports
every successful write as lost. The read goes through the store's
`bd comments --json` seam and indexes `text`, never `body`.

WHY THE ADVISORY CASE AND THE MECHANICAL CASE DIFFER IN ONE ELEMENT ONLY. Both
are the same auto-admission filing against the same spec tree; one's reference
line resolves and one's does not. Without that pairing, "the advisory item
reached `ready`" is equally consistent with a build that never graded anything,
and "the mechanical item did not" is equally consistent with one that withholds
`ready` from everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
    evaluate,
)
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.unsafe import unsafe_perform_io

_RESOLVABLE_HEADING = "## Effective acceptance criteria"
_UNRESOLVABLE_HEADING = "## A heading the governed spec tree does not carry"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    """Reset the process-singleton fake tenant before and after each case."""
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo_root: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _repo(*, tmp_path: Path) -> Path:
    """A repository whose governed spec tree is READABLE and carries one H2.

    Readability is load-bearing: the mechanical wall SKIPS its reference check
    against an unreadable tree, so an unresolvable reference would report nothing
    and the mechanical case would pass for the wrong reason.
    """
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_RESOLVABLE_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _description(*, assertion: str, references: str) -> str:
    return f"## Definition of Done\n\n- {assertion}\n\nReferences: {references}\n"


def _seed_issue(*, issue_id: str, description: str) -> None:
    client = make_beads_client(config=_config())
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type="task",
            title=issue_id,
            description=description,
            priority=2,
            assignee=None,
            created_at="2026-10-04T00:00:00Z",
            labels=["admission:auto"],
            metadata={},
            spec_id=None,
            parent_id=None,
        )
    )


def _ready_checklist() -> DefinitionOfReadyChecklist:
    return DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )


def _route(*, issue_id: str, repo: Path) -> str:
    return unsafe_perform_io(
        apply_intake_dor(
            path=_config(repo_root=repo), item_id=issue_id, checklist=_ready_checklist()
        ).unwrap()
    )


def _status(*, issue_id: str) -> str:
    return materialize_work_items(records=read_work_items(path=_config()))[issue_id].status


def _comments(*, issue_id: str) -> tuple[str, ...]:
    return tuple(
        comment.text for comment in read_work_item_comments(path=_config(), work_item_id=issue_id)
    )


def test_evaluate_routes_epic_to_backlog() -> None:
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=False,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )

    assert evaluate(checklist=checklist) == "backlog"


def test_evaluate_routes_complete_slice_to_pending_approval() -> None:
    checklist = DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    )

    assert evaluate(checklist=checklist) == "pending-approval"


def test_a_mechanical_finding_withholds_ready_and_is_recorded_as_a_ledger_comment(
    tmp_path: Path,
) -> None:
    """An unresolvable reference is mechanical, so the auto-admission stops short."""
    _seed_issue(
        issue_id="li-mechanical",
        description=_description(
            assertion="The accept valve refuses an item with no verified record.",
            references=_UNRESOLVABLE_HEADING,
        ),
    )

    verdict = _route(issue_id="li-mechanical", repo=_repo(tmp_path=tmp_path))

    assert verdict == "pending-approval"
    assert _status(issue_id="li-mechanical") == "pending-approval"
    comments = _comments(issue_id="li-mechanical")
    assert len(comments) == 1
    assert comments[0].startswith("definition-of-done finding (mechanical):")
    assert "does not resolve" in comments[0]


def test_an_advisory_finding_is_recorded_and_does_not_withhold_ready(tmp_path: Path) -> None:
    """The same filing with a resolvable reference reaches `ready` and still reports."""
    _seed_issue(
        issue_id="li-advisory",
        description=_description(
            assertion="Regression tests cover the accept valve.",
            references=_RESOLVABLE_HEADING,
        ),
    )

    verdict = _route(issue_id="li-advisory", repo=_repo(tmp_path=tmp_path))

    assert verdict == "ready"
    assert _status(issue_id="li-advisory") == "ready"
    comments = _comments(issue_id="li-advisory")
    assert len(comments) == 1
    assert comments[0].startswith("definition-of-done finding (advisory):")
    assert "regression tests" in comments[0]


def test_a_conforming_filing_reaches_ready_and_records_no_comment(tmp_path: Path) -> None:
    """The control for both cases above: a clean item is neither held nor annotated."""
    _seed_issue(
        issue_id="li-clean",
        description=_description(
            assertion="The accept valve refuses an item with no verified record.",
            references=_RESOLVABLE_HEADING,
        ),
    )

    verdict = _route(issue_id="li-clean", repo=_repo(tmp_path=tmp_path))

    assert verdict == "ready"
    assert _comments(issue_id="li-clean") == ()


def test_an_item_with_no_section_is_held_out_of_ready_by_the_absent_section_finding(
    tmp_path: Path,
) -> None:
    """The absent section is mechanical, so a sectionless filing cannot auto-admit.

    This is the migration-relevant arm: every item filed before v115 looks like
    this, and the clause's whole point is that such an item stops at the valve
    rather than reaching a sandbox.
    """
    _seed_issue(issue_id="li-sectionless", description="Just prose, no section at all.")

    verdict = _route(issue_id="li-sectionless", repo=_repo(tmp_path=tmp_path))

    assert verdict == "pending-approval"
    comments = _comments(issue_id="li-sectionless")
    assert len(comments) == 1
    assert "carries no Definition of Done section" in comments[0]


def test_a_verdict_reached_without_a_repository_root_grades_nothing() -> None:
    """With no repository there is no governed spec tree to grade a reference against.

    The one verdict where that absence could matter — the `ready` approval — still
    raises, which `test_pending_item_without_repo_root_fails_loudly` in the
    Scenario-8 integration module asserts. The epic verdict never reaches it.
    """
    _seed_issue(issue_id="li-no-root", description="Just prose, no section at all.")

    verdict = unsafe_perform_io(
        apply_intake_dor(
            path=_config(),
            item_id="li-no-root",
            checklist=DefinitionOfReadyChecklist(
                single_coherent_done=False,
                autonomously_verifiable=True,
                autonomy_tiered=True,
                dependency_linked=True,
                repo_targeted=True,
                above_floor=True,
            ),
        ).unwrap()
    )

    assert verdict == "backlog"
    assert _comments(issue_id="li-no-root") == ()

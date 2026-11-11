"""The ancestry and tree readings behind preserved-descendant protection."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkAbsent,
    PreservedWorkUnobservable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import ResumeAnchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation import ResumeGather
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import ResumeObservation
from livespec_orchestrator_beads_fabro.types import WorkItem


def test_the_original_runner_exercises_every_scripted_answer() -> None:
    """The sibling's script is complete coverage, including its defensive branch."""
    sibling = importlib.import_module(
        "tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_resume_preserved_descendant"
    )
    runner = vars(sibling)["_Runner"]()
    kwargs = {"cwd": Path("/repo"), "timeout_seconds": 120.0}

    assert runner.run(argv=["git", "merge-base", "--is-ancestor"], **kwargs).exit_code == 0
    assert runner.run(argv=["git", "rev-parse", "a" * 40 + "^{tree}"], **kwargs).stdout
    assert runner.run(argv=["git", "rev-parse", "b" * 40 + "^{tree}"], **kwargs).stdout
    with pytest.raises(AssertionError, match="unexpected command"):
        _ = runner.run(argv=["git", "status"], **kwargs)


@pytest.mark.parametrize(
    ("answers", "age", "expected"),
    [
        ((), "later", "none"),
        ((CommandResult(exit_code=1, stdout="", stderr=""),), "same", "none"),
        (
            (
                CommandResult(exit_code=0, stdout="", stderr=""),
                CommandResult(exit_code=0, stdout="1" * 40 + "\n", stderr=""),
                CommandResult(exit_code=0, stdout="1" * 40 + "\n", stderr=""),
            ),
            "same",
            "none",
        ),
        (
            (
                CommandResult(exit_code=0, stdout="", stderr=""),
                CommandResult(exit_code=0, stdout="1" * 40 + "\n", stderr=""),
                CommandResult(exit_code=0, stdout="2" * 40 + "\n", stderr=""),
            ),
            "same",
            "descendant",
        ),
        ((CommandResult(exit_code=128, stdout="", stderr=""),), "same", "unobservable"),
        (
            (
                CommandResult(exit_code=0, stdout="", stderr=""),
                CommandResult(exit_code=128, stdout="", stderr=""),
                CommandResult(exit_code=0, stdout="2" * 40 + "\n", stderr=""),
            ),
            "same",
            "unobservable",
        ),
        (
            (
                CommandResult(exit_code=0, stdout="", stderr=""),
                CommandResult(exit_code=0, stdout="", stderr=""),
                CommandResult(exit_code=0, stdout="2" * 40 + "\n", stderr=""),
            ),
            "same",
            "unobservable",
        ),
    ],
)
def test_the_measurement_only_refuses_a_descendant_with_a_different_tree(
    answers: tuple[CommandResult, ...], age: str, expected: str
) -> None:
    """Earlier, non-descending, and identical-tree refs leave a resume available."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )
    runner = Mock()
    runner.run.side_effect = answers

    result = module.preserved_descendant(
        runner=runner,
        repo=Path("/repo"),
        preservation=RecoverySeed(
            source_run_id="run-1",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run-1",
        ),
        published_head="a" * 40,
        head_is_later=age == "later",
    )

    if expected == "descendant":
        assert isinstance(result, module.PreservedDescendant)
    elif expected == "unobservable":
        assert isinstance(result, module.PreservedDescendantUnobservable)
    else:
        assert result is None


def test_the_measurement_holds_when_the_publishing_run_cannot_be_ordered() -> None:
    """An unknown run order cannot authorize a resume that might lose work."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )

    result = module.preserved_descendant(
        runner=Mock(),
        repo=Path("/repo"),
        preservation=RecoverySeed(
            source_run_id="run-1",
            remote="origin",
            commit_sha="b" * 40,
            preservation_ref="refs/heads/needs-human/run-1",
        ),
        published_head="a" * 40,
        head_is_later=None,
    )

    assert isinstance(result, module.PreservedDescendantUnobservable)
    assert "could not be ordered" in result.detail


def _item() -> WorkItem:
    return WorkItem(
        id="item",
        type="bug",
        status="ready",
        title="preserved descendant",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-01-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _gather(*, head: str | None = "a" * 40, publications: bool = True) -> ResumeGather:
    anchor = ResumeAnchor(
        record=Mock(), run_id="run-1", head="a" * 40, resumed_at="pr", source="factory"
    )
    return ResumeGather(
        observation=ResumeObservation(
            work_item_id="item",
            status="ready",
            pull_request=1,
            pull_request_head=head,
            liveness_observed=True,
        ),
        anchor=anchor,
        branch="feat/item",
        earlier_run_ids=("run-1",),
        workflow_name=None,
        publications=(("a" * 40, "run-1"),) if publications else (),
    )


def _measurement_inputs(*, kind: str) -> tuple[ResumeGather, object, object]:
    """Build one preservation reading and its scripted descendant comparison."""
    seed = RecoverySeed(
        source_run_id="run-1",
        remote="origin",
        commit_sha="b" * 40,
        preservation_ref="refs/heads/needs-human/run-1",
    )
    preserved: object = seed
    comparison: object = None
    gather = _gather()
    descendant = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )
    if kind == "no-publication":
        gather = _gather(publications=False)
    elif kind == "unobservable":
        preserved = PreservedWorkUnobservable(detail="origin unreadable")
    elif kind == "absent":
        preserved = PreservedWorkAbsent(source_run_id="run-1", sources_asked=())
    elif kind == "headless":
        gather = _gather(head=None)
    elif kind == "same-tip":
        preserved = RecoverySeed(
            source_run_id="run-1",
            remote="origin",
            commit_sha="a" * 40,
            preservation_ref="refs/livespec/preserved-publish/item/a",
            preservation_tip_sha="a" * 40,
        )
    elif kind == "held":
        comparison = descendant.PreservedDescendantUnobservable(detail="tree unreadable")
    elif kind == "seeded":
        comparison = descendant.PreservedDescendant(
            preservation_ref=seed.preservation_ref,
            preservation_tip=seed.commit_sha,
            published_head="a" * 40,
        )
    return gather, preserved, comparison


@pytest.mark.parametrize("kind", ["none", "held", "seeded"])
def test_recovery_protection_holds_or_seeds_only_for_the_measured_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A clean recovery resume is protected before it can select its launch route."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_resume_protection"
    )
    descendant = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = journal.path.write_text("", encoding="utf-8")
    seed = RecoverySeed(
        source_run_id="run-1",
        remote="origin",
        commit_sha="b" * 40,
        preservation_ref="refs/heads/needs-human/run-1",
    )
    protected: object = None
    if kind == "held":
        protected = descendant.PreservedDescendantUnobservable(detail="tree unreadable")
    elif kind == "seeded":
        protected = seed
    monkeypatch.setattr(module, "protected_resume_seed", Mock(return_value=protected))

    route = module.resume_protection(
        gather=_gather(), item=_item(), repo=tmp_path, runner=Mock(), journal=journal
    )

    assert (route is None) is (kind == "none")
    if kind == "held":
        assert route is not None and route.hold is not None
    if kind == "seeded":
        assert route is not None and route.seed == seed


@pytest.mark.parametrize(
    "kind", ["no-publication", "headless", "absent", "descendant", "unobservable"]
)
def test_resume_command_renders_the_extra_refusal_only_when_its_measurement_requires_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """The direct resume has the same refusal as recovery routing's protected arm."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_resume_protection"
    )
    descendant = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = journal.path.write_text("", encoding="utf-8")
    seed = RecoverySeed(
        source_run_id="run-1",
        remote="origin",
        commit_sha="b" * 40,
        preservation_ref="refs/heads/needs-human/run-1",
    )
    gather = _gather(
        head=None if kind == "headless" else "a" * 40,
        publications=kind != "no-publication",
    )
    protected: object = None
    if kind == "descendant":
        protected = seed
    elif kind == "unobservable":
        protected = descendant.PreservedDescendantUnobservable(detail="tree unreadable")
    monkeypatch.setattr(module, "protected_resume_seed", Mock(return_value=protected))

    refusal = module.preserved_descendant_refusal(
        gather=gather, item=_item(), repo=tmp_path, journal=journal
    )

    assert bool(refusal) is (kind in {"descendant", "unobservable"})
    if kind == "descendant":
        assert seed.preservation_ref in refusal[0] and "dispatch" in refusal[0]
    if kind == "unobservable":
        assert refusal == ("tree unreadable",)


@pytest.mark.parametrize(
    "kind",
    ["no-publication", "unobservable", "absent", "headless", "same-tip", "none", "held", "seeded"],
)
def test_preserved_descendant_measurement_only_protects_a_readable_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """The seed read, head read, and ancestry comparison remain independently guarded."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_resume_protection"
    )
    descendant = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_preserved_descendant"
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    _ = journal.path.write_text("", encoding="utf-8")
    seed = RecoverySeed(
        source_run_id="run-1",
        remote="origin",
        commit_sha="b" * 40,
        preservation_ref="refs/heads/needs-human/run-1",
    )
    gather, preserved, comparison = _measurement_inputs(kind=kind)
    monkeypatch.setattr(module, "read_journal_records", Mock(return_value=()))
    monkeypatch.setattr(module, "verified_preserved_seed", Mock(return_value=preserved))
    monkeypatch.setattr(module, "published_head_relation", Mock(return_value=False))
    monkeypatch.setattr(module, "preserved_descendant", Mock(return_value=comparison))

    result = module.protected_resume_seed(
        gather=gather, item=_item(), repo=tmp_path, runner=Mock(), journal=journal
    )

    if kind == "held":
        assert isinstance(result, descendant.PreservedDescendantUnobservable)
    elif kind == "seeded":
        assert result == seed
    else:
        assert result is None

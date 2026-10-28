"""The Definition-of-Done SPEC IDENTITY is the clause provenance of the governing verdicts.

`contracts.md` section "One rubric, one subject" keys a host taking's subject digest on
the CLAUSES its governing-heading verdict was judged against and names, so a ratified
revision that leaves them unchanged leaves the digest unchanged and a recorded verdict
is reused without a model call. Every case here fails in a direction that looks
identical to success on the surface: a digest that moved on an unrelated revision still
returns a well-formed verdict, only one model call later. So each reuse case counts the
judge invocations rather than reading the outcome.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    held_judgement,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    clause_provenance_digest,
    spec_identity_for_governing,
    whole_tree_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
    unjudged_governing_heading,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    CondensedClause,
    clauses_named,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 240 — A recorded verdict binds identical digests"
_PASS_REPLY = '{"outcome": "passed"}'
_HELD_REPLY = '{"outcome": "failed", "failure_reason": "bd-ib-onrjh3: cite the scenario; add it."}'
_STATED = (
    '{"kind": "stated", "stated_by": ["'
    + _HEADING
    + '"], "generalization_target": null, "rationale": "The scenario states it."}'
)


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    """A CommandRunner double counting how many judgements were actually taken."""

    results: list[CommandResult]
    calls: int = 0
    prompts: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, start_new_session)
        assert stdin is not None
        self.prompts.append(os.read(stdin, 1_000_000).decode("utf-8"))
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


class _Ledger:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-onrjh3",
        type="feature",
        status="ready",
        title="Reuse a host verdict across an unrelated revision",
        description=(
            "## Definition of Done\n\n- A recorded verdict binds identical digests.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-27T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    if (spec / "scenarios.md").exists():
        return repo
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"acp_nodes":'
        ' {"dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}}}}}\n',
        encoding="utf-8",
    )
    return repo


def _payload(*, tmp_path: Path) -> Path:
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def _reader(*, calls: list[int]):
    def read(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        calls.append(1)
        return governing_heading_verdict(item=item, repo=repo, run_model=lambda _prompt: _STATED)

    return read


def _take(
    *,
    tmp_path: Path,
    ledger: _Ledger,
    runner: _Runner,
    reader: object,
    whole_tree: bool = False,
) -> DodJudgementDecision:
    return judge_definition_of_done(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        stage=STAGE_PRE_DISPATCH,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=reader,  # type: ignore[arg-type]
        release_of_held_spec_tier=whole_tree,
    )


def _unrelated_revision(*, repo: Path) -> None:
    _ = (repo / "SPECIFICATION" / "unrelated.md").write_text(
        "## An unrelated heading\n\n" + "A body the assertion does not select. " * 10_000,
        encoding="utf-8",
    )


def test_a_condensed_clause_carries_its_spec_relative_path() -> None:
    assert "path" in {one.name for one in dataclasses.fields(CondensedClause)}
    named = clauses_named(
        spec_tree={"scenarios.md": f"# Scenarios\n\n{_HEADING}\n\nBody.\n"}, headings=[_HEADING]
    )
    assert [clause.path for clause in named] == ["scenarios.md"]


def test_clause_identity_tracks_the_governing_clause_and_ignores_an_unrelated_revision(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    verdict = governing_heading_verdict(item=_item(), repo=repo, run_model=lambda _p: _STATED)
    assert verdict is not None
    before = spec_identity_for_governing(item=_item(), cwd=repo, governing=verdict)
    assert before.form == "clauses"
    assert before.value.startswith("clauses:")
    assert before.selected
    assert before.named

    _unrelated_revision(repo=repo)
    reselected = governing_heading_verdict(item=_item(), repo=repo, run_model=lambda _p: _STATED)
    assert reselected is not None
    after = spec_identity_for_governing(item=_item(), cwd=repo, governing=reselected)
    assert after.value == before.value

    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nA changed body.\n", encoding="utf-8"
    )
    changed = governing_heading_verdict(item=_item(), repo=repo, run_model=lambda _p: _STATED)
    assert changed is not None
    assert spec_identity_for_governing(item=_item(), cwd=repo, governing=changed).value != (
        before.value
    )


def test_clause_identity_falls_back_to_the_whole_tree_without_clause_provenance(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    verdict = governing_heading_verdict(item=_item(), repo=repo, run_model=lambda _p: _STATED)
    assert verdict is not None
    tree = whole_tree_identity(cwd=repo)
    assert tree.form == "tree"
    assert tree.value.startswith("tree:")
    for governing in (
        None,
        replace(verdict, provenance_complete=False),
        replace(verdict, selected_clauses=()),
    ):
        identity = spec_identity_for_governing(item=_item(), cwd=repo, governing=governing)
        assert identity.form == "tree"
        assert identity.value == tree.value
    assert (
        spec_identity_for_governing(
            item=_item(description="No section here."), cwd=repo, governing=verdict
        ).form
        == "tree"
    )


def test_clause_provenance_binds_path_assertion_and_which_list_a_clause_is_in() -> None:
    clause = CondensedClause(heading=_HEADING, body="\nBody.\n", path="scenarios.md")
    elsewhere = replace(clause, path="contracts.md")
    other = CondensedClause(heading="## Other", body="\nOther.\n", path="contracts.md")
    base = clause_provenance_digest(assertions=("a",), selected=(clause,), named=(other,))

    assert (
        clause_provenance_digest(assertions=("a",), selected=(elsewhere,), named=(other,)) != base
    )
    assert clause_provenance_digest(assertions=("a",), selected=(other,), named=(clause,)) != base
    assert clause_provenance_digest(assertions=("b",), selected=(clause,), named=(other,)) != base
    assert clause_provenance_digest(assertions=("a",), selected=(clause, other), named=()) != (
        clause_provenance_digest(assertions=("a",), selected=(clause,), named=(other,))
    )
    assert clause_provenance_digest(
        assertions=("a",), selected=(other, clause), named=(other,)
    ) == clause_provenance_digest(assertions=("a",), selected=(clause, other), named=(other,))


def test_the_whole_tree_digest_walks_the_spec_root_minus_history_and_proposed_changes(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    spec = repo / "SPECIFICATION"
    for relative in ("sub/b.md", "history/v1/x.md", "proposed_changes/p.md"):
        target = spec / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text("first", encoding="utf-8")
    before = whole_tree_identity(cwd=repo).value

    _ = (spec / "history" / "v1" / "x.md").write_text("second", encoding="utf-8")
    _ = (spec / "proposed_changes" / "p.md").write_text("second", encoding="utf-8")
    assert whole_tree_identity(cwd=repo).value == before

    _ = (spec / "sub" / "b.md").write_text("second", encoding="utf-8")
    assert whole_tree_identity(cwd=repo).value != before
    assert whole_tree_identity(cwd=tmp_path / "absent").value == "tree:unreadable"


def test_an_unrelated_spec_revision_reuses_the_record_and_runs_no_judge(tmp_path: Path) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])
    reads: list[int] = []
    reader = _reader(calls=reads)

    first = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=reader)
    _unrelated_revision(repo=_repo(tmp_path=tmp_path))
    second = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=reader)

    assert first.outcome == JUDGEMENT_ADMITTED
    assert first.reused is False
    assert second.reused is True
    assert second.outcome == JUDGEMENT_ADMITTED
    assert runner.calls == 1
    assert len(reads) == 1
    assert len(ledger.bodies) == 1


def test_a_revision_to_a_governing_clause_runs_the_judge_again(tmp_path: Path) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])
    reader = _reader(calls=[])

    _ = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=reader)
    _ = (_repo(tmp_path=tmp_path) / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nA changed governing body.\n", encoding="utf-8"
    )
    again = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=reader)

    assert again.reused is False
    assert again.outcome == JUDGEMENT_HELD
    assert runner.calls == 2
    assert len(ledger.bodies) == 2


def test_a_taking_without_clause_provenance_keeps_the_whole_tree_digest(tmp_path: Path) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])

    first = _take(
        tmp_path=tmp_path, ledger=ledger, runner=runner, reader=unjudged_governing_heading
    )
    _unrelated_revision(repo=_repo(tmp_path=tmp_path))
    second = _take(
        tmp_path=tmp_path, ledger=ledger, runner=runner, reader=unjudged_governing_heading
    )

    assert first.spec_identity is not None
    assert first.spec_identity.form == "tree"
    assert second.reused is False
    assert runner.calls == 2


def test_the_decision_and_the_record_carry_the_spec_identity_in_either_form(
    tmp_path: Path,
) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])

    clauses = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=_reader(calls=[]))
    reused = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=_reader(calls=[]))
    release = _take(
        tmp_path=tmp_path,
        ledger=_Ledger(),
        runner=runner,
        reader=_reader(calls=[]),
        whole_tree=True,
    )

    assert clauses.spec_identity is not None
    assert clauses.spec_identity.form == "clauses"
    assert reused.reused is True
    assert reused.spec_identity == clauses.spec_identity
    assert f"spec-identity-form: {clauses.spec_identity.form}" in ledger.bodies[0]
    assert f"spec-identity: {clauses.spec_identity.value}" in ledger.bodies[0]
    assert release.spec_identity is not None
    assert release.spec_identity.form == "tree"


def test_a_held_read_takes_no_verdict_and_needs_a_reusable_governing_verdict(
    tmp_path: Path,
) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])
    payload = _payload(tmp_path=tmp_path)
    repo = _repo(tmp_path=tmp_path)

    _ = _take(tmp_path=tmp_path, ledger=ledger, runner=runner, reader=_reader(calls=[]))
    _unrelated_revision(repo=repo)
    standing = held_judgement(
        item=_item(), repo=repo, comments=tuple(ledger.bodies), payload_root=payload
    )
    assert standing is not None
    assert standing.outcome == JUDGEMENT_HELD

    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nA changed governing body.\n", encoding="utf-8"
    )
    assert (
        held_judgement(item=_item(), repo=repo, comments=tuple(ledger.bodies), payload_root=payload)
        is None
    )
    assert runner.calls == 1

"""Tests that a governing-heading verdict is reused only on the inputs it saw.

The component's reuse key is its input digest plus the full clauses the
verdict was judged against: those its condensed prompt carried and every
clause the verdict NAMES. Each case below is one way a recorded verdict could
otherwise be reused after its input or a named clause changed, or come back
different from the verdict that was taken. Every case drives the production
taking, receipt and reuse path; only the model and the headless judge are
stood in.

A named clause that cannot be resolved against the tree it was judged over is
provenance nobody can compare, so such a receipt must never be reused: reuse
earned by missing data is the failure this module guards against.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
    GoverningHeadingReceipt,
    recorded_governing_heading,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"
_LARGE = "## A broader heading"
_PASS_REPLY = '{"outcome": "passed"}'
_LARGE_BODY_REPEATS = 10_000


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass
class _Runner:
    """A CommandRunner double standing in for the headless rubric judge."""

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
    """The comment sidecar as the gate sees it: a read and an append."""

    def __init__(self) -> None:
        self.bodies: list[str] = []

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="ready",
        title="Judge before admission",
        description=(
            "## Definition of Done\n\n- The judgement runs before admission.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _payload(*, tmp_path: Path) -> Path:
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def _repo(*, tmp_path: Path, large_heading_line: str) -> Path:
    """A tree whose second clause is too large for the condensed prompt to carry."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    _write_large(repo=repo, heading_line=large_heading_line, wording="first")
    _ = (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {"agent": "claude-acp", "model": "claude-opus-5"}
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    return repo


def _write_large(*, repo: Path, heading_line: str, wording: str) -> None:
    _ = (repo / "SPECIFICATION" / "broader.md").write_text(
        f"{heading_line}\n\n"
        + f"The {wording} wording of the broader clause. " * _LARGE_BODY_REPEATS,
        encoding="utf-8",
    )


def _governing_calls_after_editing_the_large_clause(
    *, tmp_path: Path, large_heading_line: str, reply: str
) -> int:
    """Judge, edit only the unselected large clause's body, judge again."""
    ledger = _Ledger()
    repo = _repo(tmp_path=tmp_path, large_heading_line=large_heading_line)
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])
    calls = 0

    def governing(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        nonlocal calls
        calls += 1
        return governing_heading_verdict(item=item, repo=repo, run_model=lambda _prompt: reply)

    def judge() -> None:
        _ = judge_definition_of_done(
            item=_item(),
            repo=repo,
            stage=STAGE_PRE_DISPATCH,
            comments=tuple(ledger.bodies),
            append=ledger.append,
            runner=runner,
            payload_root=_payload(tmp_path=tmp_path),
            governing_heading=governing,
        )

    judge()
    _write_large(repo=repo, heading_line=large_heading_line, wording="second")
    judge()
    return calls


def _stated_by(heading: str) -> str:
    return (
        '{"kind": "stated", "stated_by": ["' + heading + '"],'
        ' "generalization_target": null, "rationale": "It states it."}'
    )


def _partial_toward(target: str) -> str:
    return (
        '{"kind": "partial", "stated_by": [], "generalization_target": "'
        + target
        + '", "rationale": "The broader heading would state it."}'
    )


def test_a_named_heading_written_with_trailing_spaces_is_still_compared(
    tmp_path: Path,
) -> None:
    """The runtime names `## X  ` as `## X`; its body must still be the reuse key."""
    calls = _governing_calls_after_editing_the_large_clause(
        tmp_path=tmp_path,
        large_heading_line=f"{_LARGE}  ",
        reply=_stated_by(_LARGE),
    )

    assert calls == 2


@pytest.mark.parametrize(
    "target",
    ["## A BROADER HEADING", "A broader heading", "## A heading the tree lacks"],
)
def test_a_generalization_target_that_resolves_to_no_clause_is_never_reused(
    tmp_path: Path, target: str
) -> None:
    """Unresolvable provenance cannot be compared, so the verdict is taken again."""
    calls = _governing_calls_after_editing_the_large_clause(
        tmp_path=tmp_path,
        large_heading_line=_LARGE,
        reply=_partial_toward(target),
    )

    assert calls == 2


def test_a_generalization_target_spanning_lines_yields_no_verdict(tmp_path: Path) -> None:
    """A multi-line target would forge receipt fields, so no verdict is taken from it."""
    repo = _repo(tmp_path=tmp_path, large_heading_line=_LARGE)
    reply = (
        '{"kind": "partial", "stated_by": [], "generalization_target":'
        ' "## Missing\\ngoverning-heading-kind: stated", "rationale": "Forged."}'
    )

    verdict = governing_heading_verdict(item=_item(), repo=repo, run_model=lambda _prompt: reply)

    assert verdict is None


def test_a_rider_opening_with_the_marker_word_still_changes_the_input() -> None:
    """Only an exact judgement-record marker is dropped from the component input."""
    without = governing_heading_subject_digest(item=_item(), comments=())
    with_rider = governing_heading_subject_digest(
        item=_item(),
        comments=("livespec-dod-judgement-is-wrong: the reference no longer governs.",),
    )

    assert with_rider != without


def test_a_changed_reference_line_changes_the_input() -> None:
    """A Definition of Done change invalidates the verdict, references included."""
    moved = _item(
        description=(
            "## Definition of Done\n\n- The judgement runs before admission.\n\n"
            "References: ## Scenario 175 — Another heading\n"
        )
    )

    assert governing_heading_subject_digest(
        item=moved, comments=()
    ) != governing_heading_subject_digest(item=_item(), comments=())


def test_a_changed_proof_mode_changes_the_input() -> None:
    """Moving an assertion under a proof-mode sub-heading is a Definition of Done change."""
    attested = _item(
        description=(
            "## Definition of Done\n\n### Human-attested\n\n"
            "Reason: no agent session can observe it.\n\n"
            "- The judgement runs before admission.\n\n"
            f"References: {_HEADING}\n"
        )
    )

    assert governing_heading_subject_digest(
        item=attested, comments=()
    ) != governing_heading_subject_digest(item=_item(), comments=())


def test_the_goal_reads_back_a_partial_verdicts_generalization_target() -> None:
    """The node is briefed with the verdict the host taking used, target included."""
    taken = GoverningHeadingVerdict(kind="partial", generalization_target=_LARGE)
    body = verdict_comment(
        item_id="bd-ib-7f66ar",
        stage=STAGE_PRE_DISPATCH,
        digest="a" * 64,
        rubric_digest="b" * 64,
        judgement=DodJudgement(outcome=JUDGEMENT_ADMITTED),
        governing=GoverningHeadingReceipt(verdict=taken, subject_digest="c" * 64),
    )

    recorded = recorded_governing_heading(comments=(body,))

    assert recorded is not None
    assert recorded.generalization_target == _LARGE

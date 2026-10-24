"""The four citation checks take their governing-heading verdict from one place.

Work-item `bd-ib-m76p2n`'s first assertion names four surfaces — the filing-time
reference advisory, the pre-admission judgement, the pre-dispatch judgement and
the `dod_gate` node — and requires each to take the governing-heading verdict
for an item's assertions FROM THE SPEC-STATED JUDGEMENT and to name the heading
it returns as the remedy. Three of them are host surfaces this module drives
directly; the fourth reads the verdict out of the brief the Dispatcher renders,
so it is bound here through `render_goal`, which is the only thing the node ever
sees.

EVERY CASE NAMES THE SAME HEADING, and that is the point rather than a
convenience: a filer who reads the remedy at filing time, an operator who reads
it off a pre-admission hold and the node that grades the brief must all be
pointed at one edit. Four surfaces each with their own answer is four edits a
filer can make one at a time, and nothing announces the divergence because
every surface keeps producing a well-formed finding.

THE CONTROL IS THE VERDICT THAT RETURNS NOTHING. Each surface is driven a second
time with a judgement that could not be taken, because "the remedy named the
governing heading" is otherwise equally consistent with a surface that names
that heading whatever the judgement said.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories import (
    advisory_definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    judgement_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    recorded_governing_heading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    ADVISORY_FINDING_PREFIX,
    filing_display,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import render_goal
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GOVERNING_HEADING_BLOCK_HEADING,
    GOVERNING_HEADING_UNOBSERVED_BODY,
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingReader,
)
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_GOVERNING = "## Scenario 206 — The spec-change tier is decided by the spec-stated judgement"
_CITED = "## Scenario 141 — The referenced scenario governs the proof"
_PASS_REPLY = '{"outcome": "passed"}'
_REMEDY = "add that heading to the reference line"

_VERDICT = GoverningHeadingVerdict(kind="stated", stated_by=(_GOVERNING,))


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-m76p2n",
        type="feature",
        status="ready",
        title="The citation checks consult the spec-stated judgement",
        description=(
            "## Definition of Done\n\n- The checks consult the judgement.\n\n"
            f"References: {_CITED}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="b0f",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-23T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_GOVERNING}\n\nIt states the behaviour.\n\n{_CITED}\n\nOther.\n",
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


class _Runner:
    """A `CommandRunner` double answering the rubric judge with a clean pass."""

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
        _ = (argv, cwd, timeout_seconds, env, stdin, start_new_session)
        return CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")


class _Ledger:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


def _reader(*, verdict: GoverningHeadingVerdict | None) -> GoverningHeadingReader:
    """A component whose verdict is fixed, so the SURFACE is the only variable."""

    def read(*, item: WorkItem, repo: Path) -> GoverningHeadingVerdict | None:
        _ = (item, repo)
        return verdict

    return read


def _judge(
    *, tmp_path: Path, ledger: _Ledger, stage: str, verdict: GoverningHeadingVerdict | None
) -> DodJudgementDecision:
    return judge_definition_of_done(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        stage=stage,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=_Runner(),
        payload_root=_payload(tmp_path=tmp_path),
        governing_heading=_reader(verdict=verdict),
    )


def test_the_pre_admission_judgement_holds_on_the_heading_the_judgement_returned(
    tmp_path: Path,
) -> None:
    """The rubric judge PASSES, so the hold can only come from the component."""
    ledger = _Ledger()

    decision = _judge(tmp_path=tmp_path, ledger=ledger, stage=STAGE_PRE_ADMISSION, verdict=_VERDICT)

    assert decision.outcome == JUDGEMENT_HELD
    assert any(_GOVERNING in finding and _REMEDY in finding for finding in decision.findings)
    assert decision.first_remedy is not None


def test_the_pre_dispatch_judgement_holds_on_the_same_heading(tmp_path: Path) -> None:
    ledger = _Ledger()

    decision = _judge(tmp_path=tmp_path, ledger=ledger, stage=STAGE_PRE_DISPATCH, verdict=_VERDICT)

    assert decision.outcome == JUDGEMENT_HELD
    assert any(_GOVERNING in finding for finding in decision.findings)


def test_a_judgement_that_could_not_be_taken_leaves_the_rubric_verdict_alone(
    tmp_path: Path,
) -> None:
    """The control: without it, every hold above is consistent with a constant."""
    ledger = _Ledger()

    decision = _judge(tmp_path=tmp_path, ledger=ledger, stage=STAGE_PRE_ADMISSION, verdict=None)

    assert decision.outcome == JUDGEMENT_ADMITTED
    assert decision.findings == ()


def test_the_recorded_verdict_carries_the_governing_heading_to_the_node(
    tmp_path: Path,
) -> None:
    """The node's leg: the record the taking wrote is what the goal reads back."""
    ledger = _Ledger()

    _ = _judge(tmp_path=tmp_path, ledger=ledger, stage=STAGE_PRE_DISPATCH, verdict=_VERDICT)

    recorded = recorded_governing_heading(comments=tuple(ledger.bodies))

    assert recorded is not None
    assert recorded.kind == "stated"
    assert recorded.stated_by == (_GOVERNING,)


def test_the_rendered_goal_carries_the_recorded_verdict_block(tmp_path: Path) -> None:
    ledger = _Ledger()
    _ = _judge(tmp_path=tmp_path, ledger=ledger, stage=STAGE_PRE_DISPATCH, verdict=_VERDICT)
    comments = tuple(
        WorkItemComment(text=body, author="dispatcher", created_at="2026-10-23T00:00:00Z")
        for body in ledger.bodies
    )

    goal = render_goal(
        item=_item(), repo=_repo(tmp_path=tmp_path), branch="feat/x", comments=comments
    )

    assert GOVERNING_HEADING_BLOCK_HEADING in goal
    assert _GOVERNING in goal


def test_a_goal_for_an_item_with_no_record_names_the_absence_rather_than_omitting_it(
    tmp_path: Path,
) -> None:
    """The node's fallback is its own search, which an absent block cannot signal."""
    goal = render_goal(item=_item(), repo=_repo(tmp_path=tmp_path), branch="feat/x")

    assert GOVERNING_HEADING_BLOCK_HEADING in goal
    assert GOVERNING_HEADING_UNOBSERVED_BODY in goal


def test_the_judged_subject_carries_the_verdict_the_host_taking_graded_by(
    tmp_path: Path,
) -> None:
    """One rubric, one subject: the host taking grades the block the node reads."""
    subject = judgement_subject(item=_item(), cwd=_repo(tmp_path=tmp_path), governing=_VERDICT)

    assert GOVERNING_HEADING_BLOCK_HEADING in subject
    assert _GOVERNING in subject


def test_the_filing_advisory_names_the_judgement_heading_in_place_of_a_candidate(
    tmp_path: Path,
) -> None:
    """The advisory's own rule is REPLACED, so a filer reads exactly one heading."""
    item = _item()
    repo = _repo(tmp_path=tmp_path)

    findings = advisory_definition_of_done_findings(item=item, cwd=repo, governing=_VERDICT)

    assert len(findings) == 1
    assert _GOVERNING in findings[0]
    assert _REMEDY in findings[0]


def test_the_filing_display_renders_that_remedy_under_the_advisory_leader(
    tmp_path: Path,
) -> None:
    """Given a verdict, the filer meets the same heading as the wall."""
    repo = _repo(tmp_path=tmp_path)

    rendered = filing_display(item=_item(), cwd=repo, governing=_reader(verdict=_VERDICT))

    assert f"{ADVISORY_FINDING_PREFIX} " in rendered
    assert _GOVERNING in rendered


def _install_judge(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand the judge in AT THE EXECUTABLE, as both Scenario 174 modules do.

    The display's taking is the spec-stated judgement and nothing else, so one
    unconditional reply answers it, and standing the judge in here rather than
    handing the display a verdict is the whole of the case below: a reader
    passed in cannot tell a surface that TAKES the judgement from one that
    merely accepts a verdict somebody else took.
    """
    script = tmp_path / "fake-judge"
    _ = script.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "{{\\"kind\\": \\"stated\\", \\"stated_by\\": [\\"{_GOVERNING}\\"],'
        ' \\"generalization_target\\": null, \\"rationale\\": \\"It states it.\\"}"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def test_the_filing_display_takes_the_judgement_with_no_reader_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven exactly as the four front-ends drive it: no `governing=` argument.

    The front-ends call `filing_display(item=..., cwd=Path.cwd())`, so a display
    whose verdict arrives only when a caller hands one in renders the lexical
    candidate at every production filing surface while the pre-admission
    judgement holds the item for a different heading — the divergence the whole
    assertion exists to close, and one no hand-fed case can detect.
    """
    repo = _repo(tmp_path=tmp_path)
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch)

    rendered = filing_display(item=_item(), cwd=repo)

    assert f"{ADVISORY_FINDING_PREFIX} " in rendered
    assert _GOVERNING in rendered
    assert _REMEDY in rendered


def test_the_filing_display_names_no_judgement_heading_when_none_could_be_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the heading above comes from the judgement, not from the item."""
    repo = _repo(tmp_path=tmp_path)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(tmp_path / "no-such-judge"))

    rendered = filing_display(item=_item(), cwd=repo)

    assert _GOVERNING not in rendered

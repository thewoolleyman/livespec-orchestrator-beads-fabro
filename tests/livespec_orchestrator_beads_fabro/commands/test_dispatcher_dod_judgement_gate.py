"""Tests for the one composed Definition-of-Done judgement decision.

Both call sites the clause names take the SAME decision, so it lives in one
place: reuse a recorded verdict when the item's bytes have not moved, otherwise
take the judgement and record what it said. Three caps are asserted here, and
every one of them is a claim about something that must NOT happen — the hardest
kind to notice when it breaks, because the surface looks identical either way.

A REUSED VERDICT SPENDS NOTHING. "MUST NOT run the judgement again or append
another comment for a reused verdict" is asserted by counting BOTH the judge
invocations and the appended comments, because a decision that re-ran the judge
and happened to get the same answer satisfies every assertion about the verdict
itself.

A DID-NOT-RUN RECORD IS WRITTEN ONCE PER DISTINCT CAUSE. Asserted by taking the
same unavailable judgement twice and counting one comment, then taking a
DIFFERENT cause and counting a second — without the second half, a decision
that never recorded anything at all would pass the first.

THE SUBJECT IS THE ITEM'S BRIEF, AND A JUDGEMENT RECORD IS NOT PART OF IT. The
one-rubric-one-subject clause puts every ledger comment in the subject EXCEPT the
Dispatcher's own judgement records, which are receipts rather than brief. Both
halves are load-bearing and each fails in its own direction: without the riders,
the judge grades a brief the item no longer has — a rider that narrows an
assertion is exactly the kind an operator appends — and without the exclusion,
the first recorded verdict changes the subject it was taken on, so no later
taking can ever reuse it and every pass pays a model call.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    judgement_subject_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    held_judgement,
    judge_definition_of_done,
    judge_item_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    JUDGEMENT_COMMENT_MARKER,
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
    UNAVAILABLE_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"
_HELD_REPLY = (
    '{"outcome": "failed", "failure_reason":'
    ' "bd-ib-7f66ar: the References line omits the scenario; add that heading."}'
)
_PASS_REPLY = '{"outcome": "passed"}'
# A rider of the shape operators actually append: it narrows what the section
# asserts, so a judge that never read it is grading a brief the item has moved on
# from.
_RIDER = "EVIDENCE: the preflight and the in-run gate disagreed on these same bytes."
# Two judgement records as a reader meets them on the timeline. They are written
# as LITERAL bodies rather than through the renderer so this case stays a test of
# the SUBJECT: what a record's fields look like is the record module's subject,
# and only its marker line decides whether the subject carries it. The verdict
# record names a digest nothing matches, so it cannot be reused and the judgement
# below really is taken.
_FOREIGN_VERDICT_RECORD = (
    f"{JUDGEMENT_COMMENT_MARKER}\n"
    "\n"
    "work-item: bd-ib-7f66ar\n"
    "stage: pre-admission\n"
    "outcome: admitted\n"
    "subject-digest: 0000000000000000000000000000000000000000000000000000000000000000\n"
)
_UNAVAILABLE_RECORD = (
    f"{UNAVAILABLE_COMMENT_MARKER}\n"
    "\n"
    "The pre-admission Definition-of-Done judgement did not run for this item.\n"
    "\n"
    "judgement-unavailable-cause: judge-command-failed\n"
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
        _ = (cwd, timeout_seconds, env, stdin, start_new_session)
        self.prompts.append(argv[argv.index("-p") + 1])
        self.calls += 1
        return self.results[min(self.calls - 1, len(self.results) - 1)]


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
    """A payload whose rubric is the SHIPPED one, byte for byte.

    The judgement-free read below resolves the EXECUTING build's rubric rather
    than a fixture's, so a rubric of this module's own invention would make every
    verdict recorded here unreusable by that read. That refusal would be correct
    behaviour and would hide what these cases are about, which is what the two
    surfaces do with a verdict that DOES stand.
    """
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(
        dod_gate_prompt_path().read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nBody.\n", encoding="utf-8"
    )
    return repo


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


class _Ledger:
    """The comment sidecar as the gate sees it: a read and an append."""

    def __init__(self) -> None:
        self.bodies: list[str] = []

    def append(self, *, body: str) -> None:
        self.bodies.append(body)


def _judge(
    *,
    tmp_path: Path,
    ledger: _Ledger,
    runner: _Runner,
    stage: str = STAGE_PRE_ADMISSION,
    item: WorkItem | None = None,
) -> DodJudgementDecision:
    return judge_definition_of_done(
        item=_item() if item is None else item,
        repo=_repo(tmp_path=tmp_path),
        stage=stage,
        comments=tuple(ledger.bodies),
        append=ledger.append,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
    )


def test_a_held_verdict_is_recorded_once_and_reused_without_spending_a_second(
    tmp_path: Path,
) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])

    first = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner)

    assert first.outcome == JUDGEMENT_HELD
    assert first.reused is False
    assert first.first_remedy == "add that heading."
    assert runner.calls == 1
    assert len(ledger.bodies) == 1

    second = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner)

    assert second.outcome == JUDGEMENT_HELD
    assert second.reused is True
    # Neither a second judgement nor a second comment: both caps at once.
    assert runner.calls == 1
    assert len(ledger.bodies) == 1


def test_criteria_that_change_retire_the_recorded_verdict_and_are_judged_again(
    tmp_path: Path,
) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])
    _ = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner)

    edited = _item(
        description=(
            "## Definition of Done\n\n- The judgement runs before admission now.\n\n"
            f"References: {_HEADING}\n"
        )
    )
    again = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner, item=edited)

    assert again.reused is False
    assert runner.calls == 2
    assert len(ledger.bodies) == 2


def test_an_admitted_verdict_is_recorded_so_the_next_pass_reuses_it(tmp_path: Path) -> None:
    ledger = _Ledger()
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])

    first = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner, stage=STAGE_PRE_DISPATCH)
    second = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner, stage=STAGE_PRE_DISPATCH)

    assert first.outcome == JUDGEMENT_ADMITTED
    assert first.holds is False
    assert second.reused is True
    assert runner.calls == 1


def test_a_did_not_run_record_is_written_once_per_distinct_cause(tmp_path: Path) -> None:
    ledger = _Ledger()
    absent = _Runner(results=[CommandResult(exit_code=127, stdout="", stderr="")])

    first = _judge(tmp_path=tmp_path, ledger=ledger, runner=absent)
    _ = _judge(tmp_path=tmp_path, ledger=ledger, runner=absent)

    assert first.outcome == JUDGEMENT_UNAVAILABLE
    assert first.holds is False
    assert len(ledger.bodies) == 1

    timed_out = _Runner(results=[CommandResult(exit_code=124, stdout="", stderr="")])
    _ = _judge(tmp_path=tmp_path, ledger=ledger, runner=timed_out)

    # A DIFFERENT cause is its own record: without this the first assertion is
    # also satisfied by a gate that records nothing at all.
    assert len(ledger.bodies) == 2


def test_only_a_recorded_hold_against_the_current_bytes_reads_as_held(tmp_path: Path) -> None:
    ledger = _Ledger()
    repo = _repo(tmp_path=tmp_path)
    assert held_judgement(item=_item(), repo=repo, comments=()) is None

    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])
    _ = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner)

    recorded = held_judgement(item=_item(), repo=repo, comments=tuple(ledger.bodies))
    assert recorded is not None
    assert recorded.first_remedy == "add that heading."

    passing = _Ledger()
    clean = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])
    _ = _judge(tmp_path=tmp_path, ledger=passing, runner=clean)
    assert held_judgement(item=_item(), repo=repo, comments=tuple(passing.bodies)) is None


def test_the_store_bound_entry_reads_and_appends_through_the_ledger(tmp_path: Path) -> None:
    config = _config()
    item = _item()
    append_work_item(path=config, item=item)
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])

    decision = judge_item_definition_of_done(
        item=item,
        repo=_repo(tmp_path=tmp_path),
        path=config,
        stage=STAGE_PRE_ADMISSION,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
    )

    assert decision.outcome == JUDGEMENT_HELD
    # The record reached the ledger, so the next pass reuses it rather than
    # spending a second judgement.
    reused = judge_item_definition_of_done(
        item=item,
        repo=_repo(tmp_path=tmp_path),
        path=config,
        stage=STAGE_PRE_ADMISSION,
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path),
    )
    assert reused.reused is True
    assert runner.calls == 1


def test_the_pre_dispatch_subject_carries_a_rider_and_omits_the_judgement_records(
    tmp_path: Path,
) -> None:
    ledger = _Ledger()
    ledger.bodies.extend((_RIDER, _FOREIGN_VERDICT_RECORD, _UNAVAILABLE_RECORD))
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_PASS_REPLY, stderr="")])

    decision = _judge(tmp_path=tmp_path, ledger=ledger, runner=runner, stage=STAGE_PRE_DISPATCH)

    # The foreign verdict record names a digest nothing matches, so the judgement
    # really was taken and there IS a prompt to read.
    assert decision.reused is False
    assert runner.calls == 1
    prompt = runner.prompts[0]
    assert _RIDER in prompt
    # The two record markers, which is the whole of how a reader tells a receipt
    # from a rider. Asserting the markers rather than a field name is deliberate:
    # a record's fields are the record module's subject and may change.
    assert JUDGEMENT_COMMENT_MARKER not in prompt
    assert UNAVAILABLE_COMMENT_MARKER not in prompt


def test_every_appended_judgement_record_names_the_subject_and_rubric_digests(
    tmp_path: Path,
) -> None:
    """Both digests, on the verdict record AND on the did-not-run record.

    The clause keys reuse on the pair, so a record naming only one of them
    supports no comparison — and the half it names is the half that reads as a
    complete answer: such a record is reused across a rubric change, which is
    exactly the state the pair exists to retire.
    """
    payload = _payload(tmp_path=tmp_path)
    rubric = (
        payload / ".fabro" / "workflows" / "implement-work-item" / "prompts" / "dod-gate.md"
    ).read_bytes()
    expected_rubric = hashlib.sha256(rubric).hexdigest()
    expected_subject = judgement_subject_digest(
        item=_item(), cwd=_repo(tmp_path=tmp_path), comments=()
    )

    held = _Ledger()
    _ = _judge(
        tmp_path=tmp_path,
        ledger=held,
        runner=_Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")]),
        stage=STAGE_PRE_DISPATCH,
    )
    unavailable = _Ledger()
    _ = _judge(
        tmp_path=tmp_path,
        ledger=unavailable,
        runner=_Runner(results=[CommandResult(exit_code=127, stdout="", stderr="")]),
        stage=STAGE_PRE_DISPATCH,
    )

    assert len(held.bodies) == 1
    assert len(unavailable.bodies) == 1
    for body in (held.bodies[0], unavailable.bodies[0]):
        assert f"subject-digest: {expected_subject}" in body
        assert f"rubric-digest: {expected_rubric}" in body

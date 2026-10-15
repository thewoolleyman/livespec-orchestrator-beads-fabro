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
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    held_judgement,
    judge_definition_of_done,
    judge_item_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
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
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text("# gate\n", encoding="utf-8")
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

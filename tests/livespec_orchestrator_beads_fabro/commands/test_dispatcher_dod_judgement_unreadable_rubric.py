"""The two gate arms reached when the RUBRIC itself cannot be read.

The gate reads the rubric before it decides anything, because the rubric's
digest is half the reuse condition. That read can fail — an evicted plugin cache
build, a payload root that does not resolve — and both of the gate's surfaces
then owe an answer with no rubric in hand. They owe OPPOSITE answers, which is
why each has its own case here.

The DECIDING surface fails CLOSED: it takes no judgement, because a judgement
with no rubric is not the judgement the clause names, and it records a
did-not-run so the item does not fall silent about a judgement that has stopped
working. The JUDGEMENT-FREE read fails OPEN: a drain filter and a hygiene
listing both read "nothing is holding this item back" as the absence of
evidence, so holding every item on an unreadable rubric would empty the queue on
an environment fault — and the emptiness reads exactly like a factory with no
work.

They live in a module of their own rather than beside the gate's other cases
because they were found by a coverage measurement taken after that module's Red
was authored, and a Red's test bytes are fixed across its Red-to-Green pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    UNREADABLE_RUBRIC_DIGEST,
    held_judgement,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    CAUSE_PROMPT_UNREADABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"
_HELD_REPLY = (
    '{"outcome": "failed", "failure_reason":'
    ' "bd-ib-7f66ar: the References line omits the scenario; add that heading."}'
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


def test_an_unreadable_rubric_records_a_did_not_run_and_takes_no_judgement(
    tmp_path: Path,
) -> None:
    """Nothing is spent, and the item is told why.

    The two halves pull in opposite directions and both matter. NOTHING is
    spent: the judge is never invoked, which is the whole of "a judgement with
    no rubric is not the judgement the clause names". And a record IS written,
    naming the cause, because the alternative is an item that says nothing about
    a judgement that has stopped working.
    """
    bodies: list[str] = []
    runner = _Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")])

    decision = judge_definition_of_done(
        item=_item(),
        repo=_repo(tmp_path=tmp_path),
        stage=STAGE_PRE_DISPATCH,
        comments=(),
        append=lambda *, body: bodies.append(body),
        runner=runner,
        payload_root=tmp_path / "no-payload-here",
    )

    assert decision.outcome == JUDGEMENT_UNAVAILABLE
    assert runner.calls == 0
    assert len(bodies) == 1
    assert CAUSE_PROMPT_UNREADABLE in bodies[0]
    # The field is still present and still self-describing, so the record says
    # which rubric it was taken under rather than leaving the field blank — an
    # empty field reads as one the writer forgot.
    assert f"rubric-digest: {UNREADABLE_RUBRIC_DIGEST}" in bodies[0]


def test_an_unreadable_rubric_holds_no_item_back(tmp_path: Path) -> None:
    """The judgement-free read fails OPEN, exactly as it does for a bad sidecar.

    The CONTROL is the same item and the same standing refusal read through the
    payload that verdict was taken under, which MUST report the hold: without
    it, the empty answer is equally consistent with a read that reports nothing
    at all.
    """
    bodies: list[str] = []
    repo = _repo(tmp_path=tmp_path)
    payload = _payload(tmp_path=tmp_path)
    _ = judge_definition_of_done(
        item=_item(),
        repo=repo,
        stage=STAGE_PRE_DISPATCH,
        comments=(),
        append=lambda *, body: bodies.append(body),
        runner=_Runner(results=[CommandResult(exit_code=0, stdout=_HELD_REPLY, stderr="")]),
        payload_root=payload,
    )

    assert (
        held_judgement(item=_item(), repo=repo, comments=tuple(bodies), payload_root=payload)
        is not None
    )
    assert (
        held_judgement(
            item=_item(),
            repo=repo,
            comments=tuple(bodies),
            payload_root=tmp_path / "no-payload-here",
        )
        is None
    )

"""Tests for taking the Definition-of-Done judgement on the operator host.

"Judged before admission" requires the Dispatcher to run "the same
Definition-of-Done judgement the `dod_gate` node applies (its prompt, against
the item's effective criteria, the referenced specification headings and the
resolved sandbox capabilities)". "The same prompt" is a claim about BYTES, so
the test that matters reads the node's own prompt file off the payload and
asserts its text reaches the judge — a host-side paraphrase would pass every
behavioural assertion while judging by different rules, and nothing downstream
would catch it.

THE FOUR UNAVAILABLE CAUSES ARE THE OTHER LOAD-BEARING SET. The clause names
"no eligible model, a timeout, or an unparseable verdict" and requires each to
route the item as it would be routed without the judgement. Each is MEASURED
here rather than guessed: the runner maps an absent executable to 127 and a
timeout to 124, so those two causes come from the measurement the runner
already took, not from a probe of our own that could disagree with it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    CAUSE_UNPARSEABLE_VERDICT,
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    CAUSE_JUDGE_COMMAND_FAILED,
    CAUSE_JUDGEMENT_TIMED_OUT,
    CAUSE_NO_ELIGIBLE_MODEL,
    CAUSE_PROMPT_UNREADABLE,
    dod_gate_prompt_path,
    judgement_prompt,
    resolve_judge_model,
    resolve_judge_path,
    resolve_judge_timeout_seconds,
    run_dod_judgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_GATE_PROMPT = "# Definition-of-Done gate\n\nWork through all six checks.\n"
_HEADING = "## Scenario 174 — The judgement runs before admission"


@dataclass
class _Runner:
    """A CommandRunner double recording the one invocation it is given."""

    result: CommandResult
    argv: list[str] | None = None
    timeout_seconds: float | None = None
    environ: dict[str, str] | None = None

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
        self.argv = argv
        self.timeout_seconds = timeout_seconds
        self.environ = env
        _ = (cwd, stdin, start_new_session)
        return self.result


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
    _ = (prompts / "dod-gate.md").write_text(_GATE_PROMPT, encoding="utf-8")
    return root


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nThe judgement runs before admission.\n", encoding="utf-8"
    )
    return repo


def _take(
    *, tmp_path: Path, result: CommandResult, payload: Path | None = None
) -> tuple[DodJudgement, _Runner]:
    runner = _Runner(result=result)
    verdict = run_dod_judgement(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path),
        runner=runner,
        payload_root=_payload(tmp_path=tmp_path) if payload is None else payload,
    )
    return verdict, runner


def test_the_prompt_the_judge_receives_is_the_node_s_own_prompt_plus_the_subject() -> None:
    prompt = judgement_prompt(gate_prompt=_GATE_PROMPT, subject="work-item: bd-ib-1")

    assert _GATE_PROMPT in prompt
    assert "work-item: bd-ib-1" in prompt
    # The host ending contract replaces the node's graph fallthrough, and it has
    # to name BOTH objects: without the passing one, a clean judgement and an
    # unreadable reply are the same bytes.
    assert '{"outcome": "passed"}' in prompt
    assert '"outcome": "failed"' in prompt


def test_the_shipped_node_prompt_resolves_under_the_executing_payload() -> None:
    # The claim "the same prompt the node applies" is about the SHIPPED file, so
    # the default path is asserted against the real payload rather than a
    # fixture: a path that resolved only in a fixture would read as correct here
    # and find nothing on every host.
    assert dod_gate_prompt_path().is_file()


def test_a_passing_reply_admits_the_item_and_the_judge_is_given_the_gate_prompt(
    tmp_path: Path,
) -> None:
    verdict, runner = _take(
        tmp_path=tmp_path,
        result=CommandResult(exit_code=0, stdout='Clean.\n{"outcome": "passed"}\n', stderr=""),
    )

    assert verdict.outcome == JUDGEMENT_ADMITTED
    assert runner.argv is not None
    assert "Work through all six checks." in " ".join(runner.argv)
    # The referenced heading's own body travels with the subject, because a
    # headless judge reaches no spec tree of its own by default.
    assert "The judgement runs before admission." in " ".join(runner.argv)


def test_the_judge_uses_the_caam_selected_credential_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    selection = home / ".local/state/caam-usage-rotate/selected-account.json"
    selection.parent.mkdir(parents=True)
    _ = selection.write_text('{"profile": "anthropic-5"}', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "bare-token")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5", "selected-token")

    verdict, runner = _take(
        tmp_path=tmp_path,
        result=CommandResult(exit_code=0, stdout='{"outcome": "passed"}\n', stderr=""),
    )

    assert verdict.outcome == JUDGEMENT_ADMITTED
    assert runner.environ is not None
    assert runner.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "selected-token"


def test_the_judge_names_the_unnumbered_credential_fallback_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home-without-selection"))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "bare-token")

    verdict, runner = _take(
        tmp_path=tmp_path,
        result=CommandResult(exit_code=0, stdout='{"outcome": "passed"}\n', stderr=""),
    )

    assert verdict.outcome == JUDGEMENT_ADMITTED
    assert runner.environ is not None
    assert runner.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "bare-token"
    assert capsys.readouterr().err.splitlines() == [
        "factory credential slot fallback — using CLAUDE_CODE_OAUTH_TOKEN: "
        "no caam-published account selection record"
    ]


def test_a_failing_reply_holds_the_item_with_its_findings(tmp_path: Path) -> None:
    verdict, _ = _take(
        tmp_path=tmp_path,
        result=CommandResult(
            exit_code=0,
            stdout='{"outcome": "failed", "failure_reason": "bd-ib-1: no scenario; add it."}',
            stderr="",
        ),
    )

    assert verdict.outcome == JUDGEMENT_HELD
    assert verdict.findings == ("bd-ib-1: no scenario; add it.",)


def test_each_measured_invocation_failure_maps_onto_its_own_stable_cause(
    tmp_path: Path,
) -> None:
    for exit_code, cause in (
        (127, CAUSE_NO_ELIGIBLE_MODEL),
        (124, CAUSE_JUDGEMENT_TIMED_OUT),
        (2, CAUSE_JUDGE_COMMAND_FAILED),
    ):
        verdict, _ = _take(
            tmp_path=tmp_path,
            result=CommandResult(exit_code=exit_code, stdout="", stderr="boom"),
        )

        assert verdict.outcome == JUDGEMENT_UNAVAILABLE, exit_code
        assert verdict.cause == cause, exit_code


def test_an_unreadable_reply_from_a_successful_judge_is_still_did_not_run(
    tmp_path: Path,
) -> None:
    verdict, _ = _take(
        tmp_path=tmp_path,
        result=CommandResult(exit_code=0, stdout="I could not decide.", stderr=""),
    )

    assert verdict.outcome == JUDGEMENT_UNAVAILABLE
    assert verdict.cause == CAUSE_UNPARSEABLE_VERDICT


def test_an_unreadable_gate_prompt_is_reported_rather_than_judged_around(
    tmp_path: Path,
) -> None:
    verdict, runner = _take(
        tmp_path=tmp_path,
        result=CommandResult(exit_code=0, stdout='{"outcome": "passed"}', stderr=""),
        payload=tmp_path / "no-payload-here",
    )

    assert verdict.outcome == JUDGEMENT_UNAVAILABLE
    assert verdict.cause == CAUSE_PROMPT_UNREADABLE
    # Nothing was spent: a judgement with no prompt is not a judgement.
    assert runner.argv is None


def test_the_judge_executable_resolves_by_override_then_path_then_convention(
    tmp_path: Path,
) -> None:
    override = tmp_path / "my-claude"
    assert resolve_judge_path(
        environ={"LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH": str(override)},
        which=lambda _name: None,
        conventional=tmp_path / "absent",
    ) == str(override)
    assert (
        resolve_judge_path(
            environ={}, which=lambda _name: "/usr/bin/claude", conventional=tmp_path / "absent"
        )
        == "/usr/bin/claude"
    )
    conventional = tmp_path / "conventional-claude"
    _ = conventional.write_text("", encoding="utf-8")
    assert resolve_judge_path(
        environ={}, which=lambda _name: None, conventional=conventional
    ) == str(conventional)
    # Last resort: the bare name, so the runner surfaces the absence as exit 127
    # rather than this resolver guessing that no model is eligible.
    assert (
        resolve_judge_path(environ={}, which=lambda _name: None, conventional=tmp_path / "absent")
        == "claude"
    )


def test_the_model_and_the_time_box_take_their_committed_defaults_unless_overridden() -> None:
    assert resolve_judge_model(environ={}) == resolve_judge_model(environ={"X": "y"})
    assert resolve_judge_model(environ={"LIVESPEC_DOD_JUDGEMENT_MODEL": "m"}) == "m"
    default = resolve_judge_timeout_seconds(environ={})
    assert default > 0
    assert resolve_judge_timeout_seconds(environ={"LIVESPEC_DOD_JUDGEMENT_TIMEOUT_SECONDS": "30"})
    assert (
        resolve_judge_timeout_seconds(environ={"LIVESPEC_DOD_JUDGEMENT_TIMEOUT_SECONDS": "30"})
        == 30.0
    )
    # A zero, negative or unparseable time box reads as the default rather than
    # as a self-inflicted hang or a crash on the fail-soft path.
    for raw in ("0", "-1", "not-a-number", ""):
        assert (
            resolve_judge_timeout_seconds(environ={"LIVESPEC_DOD_JUDGEMENT_TIMEOUT_SECONDS": raw})
            == default
        )

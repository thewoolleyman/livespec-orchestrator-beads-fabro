"""Tests for a command the operating system refuses to INVOKE at all.

The runner's whole contract is that "the runner never lets an expected failure
escape as an exception" — every failure reaches its caller as a non-zero
`CommandResult` it can journal or classify. It held that contract for exactly
two invocation failures, a TIMEOUT and an ABSENT EXECUTABLE, and
`FileNotFoundError` is the only `OSError` it named. Every OTHER launch failure
— `E2BIG` from an argv entry past `MAX_ARG_STRLEN`, `EACCES` from a file
without the execute bit — escaped as a bug-class exception.

WHY THAT IS A DEFECT RATHER THAN AN UNTESTED CORNER, and why the regression
test here is the Definition-of-Done judgement rather than the runner. That
judgement passes its WHOLE prompt as ONE argv entry, and the prompt now carries
the verbatim body of every specification heading an item's reference line names.
Linux caps a single argv entry at `MAX_ARG_STRLEN` (32 pages, 131072 bytes on
this host), so an item citing a large governing heading renders an argv entry
over the cap and `execve` fails with `OSError [Errno 7]`. Measured on this
repository's own spec tree, a References line naming `## Dispatcher admission,
WIP cap, and post-merge acceptance` (153,878 bytes in `SPECIFICATION/
contracts.md`) rendered a 172,666-byte entry and raised.

Nothing between that call and the three call sites caught it — not
`judge_definition_of_done`, not `dod_judgement_refusal`, not
`pre_dispatch_wall_exit` — so the exception escaped the pre-dispatch wall, the
intake routing and the approve valve alike. That is PRECISELY the condition
assertions 5 and 13 call "the judgement cannot run", where the item must be
routed as it would be routed without the judgement and the cause recorded. A
crash routes nothing and records nothing, and it crashes the dispatcher on the
one path `_dispatcher_dod_judgement_wall`'s own docstring says must never let a
bug-class exception escape.

The check suite could not see it: every judgement test stands the judge in at
the executable with a tiny fixture heading, so no test ever built an argv entry
the kernel would refuse.

WHY THE ABSENT-EXECUTABLE CONTROL IS LOAD-BEARING. `FileNotFoundError` IS an
`OSError`, so a widened catch mapping every `OSError` onto one exit code would
satisfy the fail-soft claim while collapsing 127 into it — and 127 is the one
code `_invocation_cause` reads as `no-eligible-model`, the cause whose remedy is
to install the judge. Without that control, a build that reported every launch
failure as the same thing would pass every other case in this module.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    CAUSE_JUDGE_COMMAND_FAILED,
    CAUSE_NO_ELIGIBLE_MODEL,
    run_dod_judgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

# Twice the 131072-byte `MAX_ARG_STRLEN` this host enforces, so the entry is
# over the cap on any page size a smaller margin would leave to chance.
_OVER_THE_ARGV_CAP = "x" * (2**18)
_HEADING = "## Scenario 174 — The judgement runs before admission"


def _item() -> WorkItem:
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
    return replace(base)


def _oversized_payload(*, tmp_path: Path) -> Path:
    """A payload whose `dod_gate` prompt alone exceeds one argv entry.

    The prompt file is the REAL input the oversized entry comes from — the
    judgement reads it off the payload and hands the whole thing to `-p` — so
    oversizing it reproduces the live condition rather than simulating it.
    """
    root = tmp_path / "payload"
    prompts = root / ".fabro" / "workflows" / "implement-work-item" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    _ = (prompts / "dod-gate.md").write_text(_OVER_THE_ARGV_CAP, encoding="utf-8")
    return root


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nThe judgement runs before admission.\n",
        encoding="utf-8",
    )
    return repo


def test_an_uninvokable_command_reaches_its_caller_as_routable_data(tmp_path: Path) -> None:
    """A launch the kernel refuses is a non-zero result, not an escaping error.

    126 is the POSIX "command found but could not be executed" convention, and
    it is deliberately NOT 127: the two have different remedies, and 127 is the
    one the judgement reads as a missing judge.
    """
    result = ShellCommandRunner().run(
        argv=[sys.executable, "-c", "pass", _OVER_THE_ARGV_CAP],
        cwd=tmp_path,
        timeout_seconds=30.0,
    )

    assert result.exit_code == 126
    assert result.stdout == ""
    assert "command could not be invoked" in result.stderr
    # The errno the kernel reported rides the message, because an operator
    # reading this line has to tell an oversized argument from a permission
    # fault and the exit code alone cannot say which it was.
    assert "Argument list too long" in result.stderr


def test_an_absent_executable_is_still_its_own_measurement(tmp_path: Path) -> None:
    """The control: widening the catch must not collapse 127 into 126."""
    result = ShellCommandRunner().run(
        argv=["livespec-no-such-binary-xyz"],
        cwd=tmp_path,
        timeout_seconds=30.0,
    )

    assert result.exit_code == 127
    assert "executable not found: livespec-no-such-binary-xyz" in result.stderr


def test_a_prompt_past_the_argv_cap_leaves_the_judgement_fail_soft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression: the judgement reports it could not run, and does not raise.

    The judge path is PINNED to a real executable so the failure under
    measurement is the kernel's refusal to launch and not an unresolvable
    name — with the bare `claude` fallback, whether `ENOENT` or `E2BIG` is
    reported first is the host's business and the test would be measuring that
    instead.
    """
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", sys.executable)

    verdict = run_dod_judgement(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path),
        payload_root=_oversized_payload(tmp_path=tmp_path),
    )

    assert verdict.outcome == JUDGEMENT_UNAVAILABLE
    assert verdict.cause == CAUSE_JUDGE_COMMAND_FAILED
    # Not the missing-judge cause: the judge resolved, so an operator must not
    # be sent to install one.
    assert verdict.cause != CAUSE_NO_ELIGIBLE_MODEL

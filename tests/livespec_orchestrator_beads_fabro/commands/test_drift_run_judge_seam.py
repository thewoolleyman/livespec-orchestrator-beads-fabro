"""The drift judge's one load-bearing property: the prompt is not an argv entry.

The judge prompt carries the entire ratified spec tree — 1.36 MB in this
repository — while Linux caps a single argv entry at 131072 bytes. A prompt
passed as an argument makes `execve` refuse the launch, which the runner maps
to exit 126, so EVERY merge of EVERY pass would report a judgement that could
not be taken and the frontier would never move again. Nothing in the output
would name the cause.

So the test that matters is not "the judge returns the reply" but "the prompt
reached the child on STANDARD INPUT and no argv entry carries it". It is
asserted over a prompt LARGER than that cap, because a small prompt passes
either way — which is exactly why the defect would have shipped.

The non-zero arm is asserted too: it answers the empty string, which the shared
judgement's parser reads as a `Failure` and the pass reads as one unprocessed
merge. Raising there would kill a whole pass over one merge the next tick
retries anyway.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import (
    DEFAULT_DRIFT_JUDGE_MODEL,
    DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS,
    DRIFT_JUDGE_MODEL_ENV,
    DRIFT_JUDGE_TIMEOUT_ENV,
    drift_judge,
    resolve_drift_judge_model,
    resolve_drift_judge_timeout_seconds,
)

# The kernel's own single-argv-entry ceiling, which is what makes the stdin
# route a correctness requirement rather than a preference.
_ARGV_ENTRY_CEILING = 131072


def _read_whole(*, fd: int) -> str:
    """Everything the child would have read from its standard input."""
    _ = os.lseek(fd, 0, os.SEEK_SET)
    return os.read(fd, _ARGV_ENTRY_CEILING * 4).decode("utf-8")


@dataclass(kw_only=True)
class _Runner:
    """A `CommandRunner` that reads whatever the child was given on stdin."""

    exit_code: int = 0
    reply: str = '{"kind": "stated"}'
    argvs: list[list[str]] = field(default_factory=list)
    stdin_text: list[str] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, env)
        self.argvs.append(argv)
        self.timeouts.append(timeout_seconds)
        # Read unconditionally: this seam ALWAYS hands the child a descriptor,
        # so a guard here would be an arm no call can reach — and an
        # unreachable arm in a fake is a fake that stopped describing the seam.
        self.stdin_text.append(_read_whole(fd=stdin or 0))
        return CommandResult(exit_code=self.exit_code, stdout=self.reply, stderr="")


def test_a_prompt_past_the_argv_ceiling_reaches_the_child_on_standard_input(
    tmp_path: Path,
) -> None:
    runner = _Runner()
    prompt = "x" * (_ARGV_ENTRY_CEILING + 1)

    reply = drift_judge(project_root=tmp_path, runner=runner)(prompt)

    assert reply == '{"kind": "stated"}'
    assert runner.stdin_text == [prompt]
    # And no argv entry carries it: the one that did would make the launch fail.
    assert all(len(token) <= _ARGV_ENTRY_CEILING for token in runner.argvs[0])
    assert prompt not in runner.argvs[0]


def test_the_judge_is_invoked_headless_with_no_prompt_argument(tmp_path: Path) -> None:
    runner = _Runner()

    _ = drift_judge(project_root=tmp_path, runner=runner)("a prompt")

    argv = runner.argvs[0]
    assert argv[1] == "-p"
    assert "--model" in argv
    # `claude -p` reads the prompt from stdin precisely because no prompt
    # argument follows the flag.
    assert argv[argv.index("-p") + 1] == "--model"


def test_a_non_zero_exit_answers_the_empty_string(tmp_path: Path) -> None:
    runner = _Runner(exit_code=126, reply="whatever the shell said")

    assert drift_judge(project_root=tmp_path, runner=runner)("a prompt") == ""


def test_the_prompt_file_does_not_outlive_the_call(tmp_path: Path) -> None:
    runner = _Runner()
    before = sorted(Path(os.environ.get("TMPDIR", "/tmp")).glob("livespec-drift-judge-*"))

    _ = drift_judge(project_root=tmp_path, runner=runner)("a prompt")

    # A 1.36 MB prompt per merge, on a timer firing every ten minutes, is what
    # makes the cleanup a property rather than tidiness.
    assert sorted(Path(os.environ.get("TMPDIR", "/tmp")).glob("livespec-drift-judge-*")) == before


def test_the_model_defaults_and_is_overridable() -> None:
    assert resolve_drift_judge_model(environ={}) == DEFAULT_DRIFT_JUDGE_MODEL
    assert resolve_drift_judge_model(environ={DRIFT_JUDGE_MODEL_ENV: "  "}) == (
        DEFAULT_DRIFT_JUDGE_MODEL
    )
    assert resolve_drift_judge_model(environ={DRIFT_JUDGE_MODEL_ENV: "m"}) == "m"


@pytest.mark.parametrize(
    ("case", "raw"),
    [("absent", ""), ("unparseable", "soon"), ("zero", "0"), ("negative", "-5")],
)
def test_a_bad_time_box_falls_back_rather_than_hanging(case: str, raw: str) -> None:
    resolved = resolve_drift_judge_timeout_seconds(environ={DRIFT_JUDGE_TIMEOUT_ENV: raw})

    assert resolved == DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS, case


def test_a_positive_time_box_is_honoured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DRIFT_JUDGE_TIMEOUT_ENV, "12.5")
    runner = _Runner()

    _ = drift_judge(project_root=tmp_path, runner=runner)("a prompt")

    assert runner.timeouts == [12.5]

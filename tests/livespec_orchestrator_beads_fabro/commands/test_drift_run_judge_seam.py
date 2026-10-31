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
from typing import get_args

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import (
    DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS,
    DRIFT_JUDGE_TIMEOUT_ENV,
    _looks_like_spec_stated_verdict,
    drift_judge,
    resolve_drift_judge_timeout_seconds,
)
from livespec_runtime import spec_stated

# The kernel's own single-argv-entry ceiling, which is what makes the stdin
# route a correctness requirement rather than a preference.
_ARGV_ENTRY_CEILING = 131072


def _project_root(*, tmp_path: Path) -> tuple[Path, Path]:
    """A fixture chain, never the repository's committed ACP-node table."""
    project = tmp_path / "project"
    project.mkdir()
    _ = (project / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "dispatcher": {
      "acp_nodes": {
        "dod_gate": {
          "agent": "codex-acp",
          "model": "gpt-5.6-terra",
          "effort": "high",
          "fallbacks": [{
            "agent": "claude-acp",
            "model": "claude-opus-5",
            "effort": "high"
          }]
        }
      }
    }
  }
}
""",
        encoding="utf-8",
    )
    payload = tmp_path / "payload"
    workflow = payload / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(
        "[run.inputs]\\n" 'dod_gate_adapter = "ANTHROPIC_MODEL=claude-opus-5 claude-acp"\\n',
        encoding="utf-8",
    )
    return project, payload


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
    environs: list[dict[str, str] | None] = field(default_factory=list)
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
        _ = cwd
        self.argvs.append(argv)
        self.environs.append(None if env is None else dict(env))
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
    project, payload = _project_root(tmp_path=tmp_path)

    reply = drift_judge(project_root=project, payload_root=payload, runner=runner)(prompt)

    assert reply == '{"kind": "stated"}'
    assert runner.stdin_text == [prompt]
    # And no argv entry carries it: the one that did would make the launch fail.
    assert all(len(token) <= _ARGV_ENTRY_CEILING for token in runner.argvs[0])
    assert prompt not in runner.argvs[0]


def test_the_judge_is_invoked_headless_with_no_prompt_argument(tmp_path: Path) -> None:
    runner = _Runner()
    project, payload = _project_root(tmp_path=tmp_path)

    _ = drift_judge(project_root=project, payload_root=payload, runner=runner)("a prompt")

    argv = runner.argvs[0]
    assert argv[:4] == ["codex", "exec", "-m", "gpt-5.6-terra"]
    assert "a prompt" not in argv


def test_the_drift_judge_appends_its_caller_to_inherited_resource_attributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.namespace=livespec-family")
    runner = _Runner()
    project, payload = _project_root(tmp_path=tmp_path)

    _ = drift_judge(project_root=project, payload_root=payload, runner=runner)("a prompt")

    assert runner.environs[0] is not None
    assert (
        runner.environs[0]["OTEL_RESOURCE_ATTRIBUTES"]
        == "service.namespace=livespec-family,livespec.caller=drift_run"
    )


def test_a_non_zero_exit_answers_the_empty_string(tmp_path: Path) -> None:
    runner = _Runner(exit_code=126, reply="whatever the shell said")
    project, payload = _project_root(tmp_path=tmp_path)

    assert drift_judge(project_root=project, payload_root=payload, runner=runner)("a prompt") == ""


@pytest.mark.parametrize(
    "reply",
    [pytest.param("not JSON"), pytest.param("[]"), pytest.param('{"kind": 3}')],
)
def test_only_a_mapping_with_a_text_spec_kind_is_a_drift_verdict(reply: str) -> None:
    assert not _looks_like_spec_stated_verdict(text=reply)


@pytest.mark.parametrize("kind", get_args(spec_stated.StatedKind))
def test_every_shared_spec_stated_kind_is_a_drift_verdict(kind: str) -> None:
    assert _looks_like_spec_stated_verdict(text=f'{{"kind": "{kind}"}}')


def test_the_prompt_file_does_not_outlive_the_call(tmp_path: Path) -> None:
    runner = _Runner()
    before = sorted(Path(os.environ.get("TMPDIR", "/tmp")).glob("livespec-drift-judge-*"))
    project, payload = _project_root(tmp_path=tmp_path)

    _ = drift_judge(project_root=project, payload_root=payload, runner=runner)("a prompt")

    # A 1.36 MB prompt per merge, on a timer firing every ten minutes, is what
    # makes the cleanup a property rather than tidiness.
    assert sorted(Path(os.environ.get("TMPDIR", "/tmp")).glob("livespec-drift-judge-*")) == before


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
    project, payload = _project_root(tmp_path=tmp_path)

    _ = drift_judge(project_root=project, payload_root=payload, runner=runner)("a prompt")

    assert runner.timeouts == [12.5]

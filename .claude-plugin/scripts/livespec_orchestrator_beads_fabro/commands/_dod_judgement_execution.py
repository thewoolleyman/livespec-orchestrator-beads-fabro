"""Execute one host Definition-of-Done candidate and measure its input use.

The candidate chain owns ordering and result meaning. This module owns the
process boundary: it launches one isolated candidate, journals assistant
events, and stops a streaming Claude candidate at the input bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidate_command import (
    candidate_command,
    is_codex_candidate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    INPUT_USAGE_UNREPORTED,
    CandidateInputUsage,
    candidate_input_usage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_judge_candidate import (
    isolated_launch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._host_judge_spend_journal import (
    HostJudgeSpendJournal,
    append_assistant_event,
    is_claude_agent,
    start_spend_journal,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = ["CandidateRun", "run_candidate"]

_UNBOUNDED_USAGE = CandidateInputUsage(total_tokens=None, status=INPUT_USAGE_UNREPORTED)


@dataclass(frozen=True, kw_only=True)
class CandidateRun:
    """One candidate's final result and live budget disposition."""

    result: CommandResult
    usage: CandidateInputUsage
    ended_by_input_limit: bool


@dataclass(kw_only=True)
class _LiveUsage:
    """State owned by the streaming callback while it measures a candidate."""

    output: list[str] = field(default_factory=list)
    ended_by_input_limit: bool = False

    def observe(self, *, line: str) -> bool:
        """Record a line and say whether its cumulative use ends this candidate."""
        self.output.append(line)
        self.ended_by_input_limit = candidate_input_usage(output="".join(self.output)).reached_limit
        return self.ended_by_input_limit


def run_candidate(  # noqa: PLR0913 - each argument is an execution seam input.
    *,
    candidate: AcpCandidate,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    environ: dict[str, str],
    timeout_seconds: float,
    bound_input: bool,
    journal_name: str,
    journal_spend: bool,
) -> CandidateRun:
    """Run one configured host candidate with a prompt file as its only stdin."""
    argv, judge_environ = candidate_command(
        candidate=candidate,
        environ=environ,
        bound_input=bound_input,
        journal_spend=journal_spend,
        journal_name=journal_name,
        allowed_directory=cwd,
    )
    journal = (
        start_spend_journal(
            home=Path(environ.get("HOME", str(Path.home()))),
            name=journal_name,
            cwd=cwd,
            first_prompt=prompt,
        )
        if is_claude_agent(agent_id=candidate.agent_id) and (bound_input or journal_spend)
        else None
    )
    with isolated_launch(
        is_codex=is_codex_candidate(candidate=candidate),
        prompt=prompt,
        candidate_environ=judge_environ,
        ambient_environ=environ,
    ) as isolated:
        if journal is not None and isinstance(runner, ShellCommandRunner):
            live_usage = _LiveUsage()
            result = runner.run_streaming(
                argv=argv,
                cwd=isolated.cwd,
                timeout_seconds=timeout_seconds,
                on_stdout_line=lambda line: _observe_line(
                    journal=journal, live_usage=live_usage, bound_input=bound_input, line=line
                ),
                env=isolated.environ,
                stdin=isolated.stdin,
            )
            return CandidateRun(
                result=result,
                usage=candidate_input_usage(output=result.stdout),
                ended_by_input_limit=live_usage.ended_by_input_limit,
            )
        result = runner.run(
            argv=argv,
            cwd=isolated.cwd,
            timeout_seconds=timeout_seconds,
            env=isolated.environ,
            stdin=isolated.stdin,
        )
    if journal is not None:
        for line in result.stdout.splitlines():
            append_assistant_event(journal=journal, line=line)
    usage = candidate_input_usage(output=result.stdout) if bound_input else _UNBOUNDED_USAGE
    return CandidateRun(result=result, usage=usage, ended_by_input_limit=False)


def _observe_line(
    *, journal: HostJudgeSpendJournal, live_usage: _LiveUsage, bound_input: bool, line: str
) -> bool:
    """Journal a received response before optionally ending an over-budget candidate."""
    append_assistant_event(journal=journal, line=line)
    return live_usage.observe(line=line) if bound_input else False

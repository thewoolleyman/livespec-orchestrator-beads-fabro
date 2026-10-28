"""Run the ordered host Definition-of-Done candidate chain.

The input bound belongs to a candidate across every request it makes.  The
production shell runner therefore reports stdout while the candidate is alive,
letting this module end its private process group before a later request or a
natural verdict can consume more input.

The bound is OPT-IN per chain (`bound_input`), because the clause that states it
covers only the pre-admission and pre-dispatch takings: a chain run for another
purpose keeps the candidates' plain replies and is never ended on input use.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    OUTCOME_VERDICT,
    CandidateAttempt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidate_command import (
    candidate_command,
    candidate_label,
    candidate_model,
    is_codex_candidate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    resolve_judge_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    INPUT_USAGE_UNREPORTED,
    CandidateInputUsage,
    candidate_input_usage,
    candidate_reply,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_judge_candidate import (
    isolated_launch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "CAUSE_INPUT_LIMIT",
    "CAUSE_JUDGEMENT_TIMED_OUT",
    "CAUSE_JUDGE_COMMAND_FAILED",
    "CAUSE_NO_ELIGIBLE_MODEL",
    "CandidateChainResult",
    "run_candidate_chain",
]

# The three conditions the clause names as "cannot be run" that are properties
# of the INVOCATION, plus the one property of the payload. Each is one stable
# string, because the did-not-run record is capped per distinct cause and a
# cause carrying a varying detail would make every attempt distinct.
CAUSE_NO_ELIGIBLE_MODEL = "no-eligible-model"
CAUSE_JUDGEMENT_TIMED_OUT = "judgement-timed-out"
CAUSE_JUDGE_COMMAND_FAILED = "judge-command-failed"
# The input bound ended every candidate that reached it; one stable string for
# the same reason as the three above.
CAUSE_INPUT_LIMIT = "input-limit-reached"
# The runner's own mapping of a caught invocation failure, which is where these
# two numbers come from rather than from any convention restated here.
_EXIT_TIMED_OUT = 124
_EXIT_EXECUTABLE_ABSENT = 127
_UNBOUNDED_USAGE = CandidateInputUsage(total_tokens=None, status=INPUT_USAGE_UNREPORTED)


@dataclass(frozen=True, kw_only=True)
class CandidateChainResult:
    """The candidate result whose verdict remains eligible to decide.

    `attempts` is every candidate the chain ran, in order, each with the agent and
    model it resolved to, its exit code and its outcome.
    """

    reply: str | None
    cause: str
    deciding_candidate: str | None = None
    usage: CandidateInputUsage | None = None
    bound_ended_candidates: tuple[str, ...] = ()
    attempts: tuple[CandidateAttempt, ...] = ()

    def __iter__(self) -> Iterator[str | None]:
        """Yield the established reply/cause pair for existing host consumers."""
        yield self.reply
        yield self.cause


@dataclass(frozen=True, kw_only=True)
class _CandidateRun:
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


def run_candidate_chain(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
    candidate_resolver: Callable[..., tuple[AcpCandidate, ...] | None] = dod_gate_candidates,
    bound_input: bool = False,
) -> CandidateChainResult:
    """Run the resolved candidates in order, closing stdin for each.

    A candidate that cannot run or produces a reply the caller cannot parse
    advances the ordered fallback chain. The first parseable verdict returns
    immediately, so no later candidate can run after a judgement is decided.

    `bound_input` turns on the input bound: each candidate is asked to report its
    usage, is ended once its requests together report the limit, and loses any
    verdict it returned past it. Off, the chain is exactly the unbounded one.
    """
    resolved = candidate_resolver(cwd=cwd)
    if resolved is None:
        return CandidateChainResult(reply=None, cause=CAUSE_NO_ELIGIBLE_MODEL)
    environ = dict(os.environ)
    resolved_timeout = (
        resolve_judge_timeout_seconds(environ=environ)
        if timeout_seconds is None
        else timeout_seconds
    )
    last_cause = CAUSE_NO_ELIGIBLE_MODEL
    bound_ended: list[str] = []
    attempts: list[CandidateAttempt] = []
    for candidate in resolved:
        attempt = _run_candidate(
            candidate=candidate,
            prompt=prompt,
            cwd=cwd,
            runner=runner,
            environ=environ,
            timeout_seconds=resolved_timeout,
            bound_input=bound_input,
        )
        reply = (
            candidate_reply(output=attempt.result.stdout) if bound_input else attempt.result.stdout
        )
        outcome = _candidate_outcome(attempt=attempt, reply=reply, is_verdict=is_verdict)
        attempts.append(
            CandidateAttempt(
                agent=candidate.agent_id or candidate.adapter.command,
                model=candidate_model(candidate=candidate),
                exit_code=attempt.result.exit_code,
                outcome=outcome,
            )
        )
        if outcome == CAUSE_INPUT_LIMIT:
            bound_ended.append(candidate_label(candidate=candidate))
        if outcome == OUTCOME_VERDICT:
            return CandidateChainResult(
                reply=reply,
                cause="",
                deciding_candidate=candidate_label(candidate=candidate),
                usage=attempt.usage,
                bound_ended_candidates=tuple(bound_ended),
                attempts=tuple(attempts),
            )
        last_cause = outcome
    return CandidateChainResult(
        reply=None,
        cause=last_cause,
        bound_ended_candidates=tuple(bound_ended),
        attempts=tuple(attempts),
    )


def _candidate_outcome(
    *, attempt: _CandidateRun, reply: str, is_verdict: Callable[[str], bool]
) -> str:
    """What one candidate's run amounted to: a verdict, or the cause that moved on."""
    if attempt.ended_by_input_limit or attempt.usage.reached_limit:
        return CAUSE_INPUT_LIMIT
    if attempt.result.exit_code != 0:
        return _invocation_cause(exit_code=attempt.result.exit_code)
    return OUTCOME_VERDICT if is_verdict(reply) else "unparseable-verdict"


def _run_candidate(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    candidate: AcpCandidate,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    environ: dict[str, str],
    timeout_seconds: float,
    bound_input: bool,
) -> _CandidateRun:
    """Run one configured host candidate with a prompt file as its only stdin."""
    argv, judge_environ = candidate_command(
        candidate=candidate, environ=environ, bound_input=bound_input, allowed_directory=cwd
    )
    with isolated_launch(
        is_codex=is_codex_candidate(candidate=candidate),
        prompt=prompt,
        candidate_environ=judge_environ,
        ambient_environ=environ,
    ) as isolated:
        if bound_input and isinstance(runner, ShellCommandRunner):
            live_usage = _LiveUsage()
            result = runner.run_streaming(
                argv=argv,
                cwd=isolated.cwd,
                timeout_seconds=timeout_seconds,
                on_stdout_line=live_usage.observe,
                env=isolated.environ,
                stdin=isolated.stdin,
            )
            return _CandidateRun(
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
    usage = candidate_input_usage(output=result.stdout) if bound_input else _UNBOUNDED_USAGE
    return _CandidateRun(result=result, usage=usage, ended_by_input_limit=False)


def _invocation_cause(*, exit_code: int) -> str:
    if exit_code == _EXIT_EXECUTABLE_ABSENT:
        return CAUSE_NO_ELIGIBLE_MODEL
    if exit_code == _EXIT_TIMED_OUT:
        return CAUSE_JUDGEMENT_TIMED_OUT
    return CAUSE_JUDGE_COMMAND_FAILED

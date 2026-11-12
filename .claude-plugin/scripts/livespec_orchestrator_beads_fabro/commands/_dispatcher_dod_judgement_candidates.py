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
from dataclasses import dataclass
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
    candidate_label,
    candidate_model,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    resolve_judge_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    INPUT_USAGE_COMPLETE,
    INPUT_USAGE_PARTIAL,
    INPUT_USAGE_UNREPORTED,
    CandidateInputUsage,
    candidate_reply,
)
from livespec_orchestrator_beads_fabro.commands._dod_judgement_execution import (
    CandidateRun,
    run_candidate,
)
from livespec_orchestrator_beads_fabro.commands._host_judge_spend_journal import (
    is_claude_agent,
    spend_journal_name,
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
    total_usage: CandidateInputUsage | None = None
    bound_ended_candidates: tuple[str, ...] = ()
    bound_ended_input_tokens: tuple[int | None, ...] = ()
    attempts: tuple[CandidateAttempt, ...] = ()

    def __iter__(self) -> Iterator[str | None]:
        """Yield the established reply/cause pair for existing host consumers."""
        yield self.reply
        yield self.cause


def run_candidate_chain(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
    candidate_resolver: Callable[..., tuple[AcpCandidate, ...] | None] = dod_gate_candidates,
    bound_input: bool = False,
    caller: str | None = None,
    journal_name: str | None = None,
    journal_spend: bool = False,
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
    environ = _caller_environ(caller=caller, environ=dict(os.environ))
    resolved_journal_name = (
        spend_journal_name(caller=caller, cwd=cwd) if journal_name is None else journal_name
    )
    resolved_timeout = (
        resolve_judge_timeout_seconds(environ=environ)
        if timeout_seconds is None
        else timeout_seconds
    )
    last_cause = CAUSE_NO_ELIGIBLE_MODEL
    bound_ended: list[str] = []
    bound_ended_input_tokens: list[int | None] = []
    attempts: list[CandidateAttempt] = []
    usages: list[CandidateInputUsage] = []
    for candidate in resolved:
        attempt = run_candidate(
            candidate=candidate,
            prompt=prompt,
            cwd=cwd,
            runner=runner,
            environ=environ,
            timeout_seconds=resolved_timeout,
            bound_input=bound_input,
            journal_name=resolved_journal_name,
            journal_spend=journal_spend,
        )
        reply = (
            candidate_reply(output=attempt.result.stdout)
            if bound_input or is_claude_agent(agent_id=candidate.agent_id)
            else attempt.result.stdout
        )
        outcome = _candidate_outcome(attempt=attempt, reply=reply, is_verdict=is_verdict)
        usages.append(attempt.usage)
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
            bound_ended_input_tokens.append(attempt.usage.total_tokens)
        if outcome == OUTCOME_VERDICT:
            return CandidateChainResult(
                reply=reply,
                cause="",
                deciding_candidate=candidate_label(candidate=candidate),
                usage=attempt.usage,
                total_usage=_total_usage(usages=usages),
                bound_ended_candidates=tuple(bound_ended),
                bound_ended_input_tokens=tuple(bound_ended_input_tokens),
                attempts=tuple(attempts),
            )
        last_cause = outcome
    return CandidateChainResult(
        reply=None,
        cause=last_cause,
        total_usage=_total_usage(usages=usages),
        bound_ended_candidates=tuple(bound_ended),
        bound_ended_input_tokens=tuple(bound_ended_input_tokens),
        attempts=tuple(attempts),
    )


def _candidate_outcome(
    *, attempt: CandidateRun, reply: str, is_verdict: Callable[[str], bool]
) -> str:
    """What one candidate's run amounted to: a verdict, or the cause that moved on."""
    if attempt.ended_by_input_limit or attempt.usage.reached_limit:
        return CAUSE_INPUT_LIMIT
    if attempt.result.exit_code != 0:
        return _invocation_cause(exit_code=attempt.result.exit_code)
    return OUTCOME_VERDICT if is_verdict(reply) else "unparseable-verdict"


def _total_usage(*, usages: list[CandidateInputUsage]) -> CandidateInputUsage:
    """The taking's input across every candidate it launched."""
    if not usages or all(usage.total_tokens is None for usage in usages):
        return CandidateInputUsage(total_tokens=None, status=INPUT_USAGE_UNREPORTED)
    total = sum(usage.total_tokens or 0 for usage in usages)
    status = (
        INPUT_USAGE_COMPLETE
        if all(usage.status == INPUT_USAGE_COMPLETE for usage in usages)
        else INPUT_USAGE_PARTIAL
    )
    return CandidateInputUsage(total_tokens=total, status=status)


def _invocation_cause(*, exit_code: int) -> str:
    if exit_code == _EXIT_EXECUTABLE_ABSENT:
        return CAUSE_NO_ELIGIBLE_MODEL
    if exit_code == _EXIT_TIMED_OUT:
        return CAUSE_JUDGEMENT_TIMED_OUT
    return CAUSE_JUDGE_COMMAND_FAILED


def _caller_environ(*, caller: str | None, environ: dict[str, str]) -> dict[str, str]:
    """Append the launching judgement's caller label when one is supplied."""
    if caller is None:
        return environ
    label = f"livespec.caller={caller}"
    inherited = environ.get("OTEL_RESOURCE_ATTRIBUTES")
    return {
        **environ,
        "OTEL_RESOURCE_ATTRIBUTES": label if inherited is None else f"{inherited},{label}",
    }

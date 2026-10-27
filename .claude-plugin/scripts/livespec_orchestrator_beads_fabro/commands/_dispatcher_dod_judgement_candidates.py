"""Run the ordered host Definition-of-Done candidate chain.

The host budget belongs to a CANDIDATE rather than an individual CLI request.
Some clients stream several request records before producing a natural verdict,
so the chain observes stdout as it arrives and ends a candidate's private
process group as soon as its deduplicated input total reaches the fixed limit.
The following candidate then receives the same prompt; an over-budget reply is
never eligible to decide the judgement.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    judgement_argv,
    resolve_judge_path,
    resolve_judge_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    CandidateInputUsage,
    candidate_input_usage,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
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
CAUSE_INPUT_LIMIT = "input-limit-reached"

# The runner's own mapping of a caught invocation failure, which is where these
# two numbers come from rather than from any convention restated here.
_EXIT_TIMED_OUT = 124
_EXIT_EXECUTABLE_ABSENT = 127
_CODEX_AGENT = "codex-acp"
_CODEX_SANDBOX_SETTINGS = frozenset({"sandbox_mode", "approval_policy"})
_CLAUDE_AGENT = "claude-acp"
_PROMPT_FILE_PREFIX = "livespec-dod-gate-"


@dataclass(frozen=True, kw_only=True)
class CandidateChainResult:
    """The candidate result whose verdict remains eligible to decide."""

    reply: str | None
    cause: str
    deciding_candidate: str | None = None
    usage: CandidateInputUsage | None = None
    bound_ended_candidates: tuple[str, ...] = ()

    def __iter__(self) -> Iterator[str | None]:
        """Yield the established reply/cause pair for existing host consumers."""
        yield self.reply
        yield self.cause


@dataclass(frozen=True, kw_only=True)
class _CandidateRun:
    """One candidate's result, its live usage total, and its budget disposition."""

    result: CommandResult
    usage: CandidateInputUsage
    ended_by_input_limit: bool


@dataclass(kw_only=True)
class _LiveUsage:
    """State the streaming callback owns while it decides the candidate budget."""

    output: list[str] = field(default_factory=list)
    ended_by_input_limit: bool = False

    def observe(self, *, line: str) -> bool:
        """Record one stdout line and say whether its cumulative total ends the run."""
        self.output.append(line)
        self.ended_by_input_limit = candidate_input_usage(output="".join(self.output)).reached_limit
        return self.ended_by_input_limit


def run_candidate_chain(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
    candidate_resolver: Callable[..., tuple[AcpCandidate, ...] | None] = dod_gate_candidates,
) -> CandidateChainResult:
    """Run configured candidates in order and return the first eligible verdict."""
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
    for candidate in resolved:
        result = _run_candidate(
            candidate=candidate,
            prompt=prompt,
            cwd=cwd,
            runner=runner,
            environ=environ,
            timeout_seconds=resolved_timeout,
        )
        if result.ended_by_input_limit:
            bound_ended.append(_candidate_label(candidate=candidate))
            last_cause = CAUSE_INPUT_LIMIT
            continue
        if result.result.exit_code != 0:
            last_cause = _invocation_cause(exit_code=result.result.exit_code)
            continue
        if result.usage.reached_limit:
            bound_ended.append(_candidate_label(candidate=candidate))
            last_cause = CAUSE_INPUT_LIMIT
            continue
        if is_verdict(result.result.stdout):
            return CandidateChainResult(
                reply=result.result.stdout,
                cause="",
                deciding_candidate=_candidate_label(candidate=candidate),
                usage=result.usage,
                bound_ended_candidates=tuple(bound_ended),
            )
        last_cause = "unparseable-verdict"
    return CandidateChainResult(
        reply=None,
        cause=last_cause,
        bound_ended_candidates=tuple(bound_ended),
    )


def _run_candidate(
    *,
    candidate: AcpCandidate,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    environ: dict[str, str],
    timeout_seconds: float,
) -> _CandidateRun:
    """Run one configured host candidate with a prompt file as its only stdin."""
    argv, judge_environ = _candidate_command(candidate=candidate, environ=environ)
    with tempfile.TemporaryDirectory(prefix=_PROMPT_FILE_PREFIX) as scratch:
        prompt_path = Path(scratch) / "prompt.txt"
        _ = prompt_path.write_text(prompt, encoding="utf-8")
        with prompt_path.open("rb") as handle:
            streaming = cast(
                "Callable[..., CommandResult] | None",
                getattr(runner, "run_streaming", None),
            )
            if callable(streaming):
                live_usage = _LiveUsage()
                result = streaming(
                    argv=argv,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                    on_stdout_line=lambda line: live_usage.observe(line=line),
                    env=judge_environ,
                    stdin=handle.fileno(),
                )
                return _CandidateRun(
                    result=result,
                    usage=candidate_input_usage(output=result.stdout),
                    ended_by_input_limit=live_usage.ended_by_input_limit,
                )
            result = runner.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=judge_environ,
                stdin=handle.fileno(),
            )
            usage = candidate_input_usage(output=result.stdout)
            return _CandidateRun(
                result=result,
                usage=usage,
                ended_by_input_limit=False,
            )


def _candidate_command(
    *, candidate: AcpCandidate, environ: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """The direct host command for one catalog-resolved ACP candidate.

    The host runs the one-shot CLIs, never the ACP adapter command itself: an
    adapter is a JSON-RPC stdio server that does not grade a prompt on standard
    input, and the Codex adapter path is baked into the factory sandbox image.
    What the candidate resolved still reaches the CLI: its adapter environment
    (effort, endpoint and auth overrides) and, for Codex, every string
    `CODEX_CONFIG` setting as a `-c` override. The factory's sandbox and
    approval settings do not carry over; a host judge only reads, so Codex runs
    `-s read-only`, the counterpart of the Claude judge's read-only tool list.
    """
    judge_environ = {**environ, **candidate.adapter.env}
    if candidate.agent_id == _CODEX_AGENT:
        settings = _codex_settings(candidate=candidate)
        model = settings.pop("model", "")
        argv = ["codex", "exec", "-m", model, "--json"]
        for key, value in settings.items():
            argv.extend(("-c", f"{key}={json.dumps(value)}"))
        argv.extend(("-s", "read-only"))
        return argv, judge_environ
    if candidate.agent_id == _CLAUDE_AGENT:
        model = candidate.adapter.env.get("ANTHROPIC_MODEL", "")
        credential = select_factory_credential(
            environ=environ,
            home=Path.home(),
            warn=lambda message: sys.stderr.write(f"{message}\n"),
        )
        judge_environ[CLAUDE_OAUTH_TOKEN_ENV] = environ.get(credential.env_name, "")
        argv = judgement_argv(judge_path=resolve_judge_path(environ=environ), model=model)
        return argv, judge_environ
    return [candidate.adapter.command, *candidate.adapter.args], judge_environ


def _candidate_label(*, candidate: AcpCandidate) -> str:
    """The candidate identity a durable record can name without host-local paths."""
    if candidate.agent_id == _CODEX_AGENT:
        model = _codex_settings(candidate=candidate).get("model")
        return f"{candidate.agent_id}:{model if model is not None else ''}"
    if candidate.agent_id == _CLAUDE_AGENT:
        return f"{candidate.agent_id}:{candidate.adapter.env.get('ANTHROPIC_MODEL', '')}"
    return candidate.agent_id or ""


def _codex_settings(*, candidate: AcpCandidate) -> dict[str, str]:
    """The string settings rendered into this candidate's catalog adapter.

    Only a string is carried, so a malformed value is dropped rather than
    rendered, and the sandbox and approval settings belong to the factory
    sandbox, so they are not carried either.
    """
    raw = candidate.adapter.env.get("CODEX_CONFIG", "")
    try:
        decoded: object = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    payload = cast("dict[str, object]", decoded)
    return {
        key: value
        for key, value in payload.items()
        if key not in _CODEX_SANDBOX_SETTINGS and isinstance(value, str)
    }


def _invocation_cause(*, exit_code: int) -> str:
    if exit_code == _EXIT_EXECUTABLE_ABSENT:
        return CAUSE_NO_ELIGIBLE_MODEL
    if exit_code == _EXIT_TIMED_OUT:
        return CAUSE_JUDGEMENT_TIMED_OUT
    return CAUSE_JUDGE_COMMAND_FAILED

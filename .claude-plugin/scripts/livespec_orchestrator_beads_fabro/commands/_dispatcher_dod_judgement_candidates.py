"""Run the ordered host Definition-of-Done candidate chain.

The input bound belongs to a candidate across every request it makes.  The
production shell runner therefore reports stdout while the candidate is alive,
letting this module end its private process group before a later request or a
natural verdict can consume more input.
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
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

CAUSE_NO_ELIGIBLE_MODEL = "no-eligible-model"
CAUSE_JUDGEMENT_TIMED_OUT = "judgement-timed-out"
CAUSE_JUDGE_COMMAND_FAILED = "judge-command-failed"
CAUSE_INPUT_LIMIT = "input-limit-reached"
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


def run_candidate_chain(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
    candidate_resolver: Callable[..., tuple[AcpCandidate, ...] | None] = dod_gate_candidates,
) -> CandidateChainResult:
    """Run configured candidates in order and retain only the first eligible verdict."""
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
        attempt = _run_candidate(
            candidate=candidate,
            prompt=prompt,
            cwd=cwd,
            runner=runner,
            environ=environ,
            timeout_seconds=resolved_timeout,
        )
        if attempt.ended_by_input_limit or attempt.usage.reached_limit:
            bound_ended.append(_candidate_label(candidate=candidate))
            last_cause = CAUSE_INPUT_LIMIT
            continue
        if attempt.result.exit_code != 0:
            last_cause = _invocation_cause(exit_code=attempt.result.exit_code)
            continue
        if is_verdict(attempt.result.stdout):
            return CandidateChainResult(
                reply=attempt.result.stdout,
                cause="",
                deciding_candidate=_candidate_label(candidate=candidate),
                usage=attempt.usage,
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
    """Run one candidate with a prompt file as its only stdin."""
    argv, judge_environ = _candidate_command(candidate=candidate, environ=environ)
    with tempfile.TemporaryDirectory(prefix=_PROMPT_FILE_PREFIX) as scratch:
        prompt_path = Path(scratch) / "prompt.txt"
        _ = prompt_path.write_text(prompt, encoding="utf-8")
        with prompt_path.open("rb") as handle:
            if isinstance(runner, ShellCommandRunner):
                live_usage = _LiveUsage()
                result = runner.run_streaming(
                    argv=argv,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                    on_stdout_line=live_usage.observe,
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
    return _CandidateRun(
        result=result,
        usage=candidate_input_usage(output=result.stdout),
        ended_by_input_limit=False,
    )


def _candidate_command(
    *, candidate: AcpCandidate, environ: dict[str, str]
) -> tuple[list[str], dict[str, str]]:
    """Build one direct host command from a catalog-resolved candidate."""
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
        return (
            judgement_argv(
                judge_path=resolve_judge_path(environ=environ),
                model=model,
            ),
            judge_environ,
        )
    return [candidate.adapter.command, *candidate.adapter.args], judge_environ


def _candidate_label(*, candidate: AcpCandidate) -> str:
    """Render a durable candidate identity without host-local paths."""
    if candidate.agent_id == _CODEX_AGENT:
        model = _codex_settings(candidate=candidate).get("model")
        return f"{candidate.agent_id}:{model if model is not None else ''}"
    if candidate.agent_id == _CLAUDE_AGENT:
        return f"{candidate.agent_id}:{candidate.adapter.env.get('ANTHROPIC_MODEL', '')}"
    return candidate.agent_id or ""


def _codex_settings(*, candidate: AcpCandidate) -> dict[str, str]:
    """Return the string Codex settings safe to carry from the candidate config."""
    try:
        decoded: object = json.loads(candidate.adapter.env.get("CODEX_CONFIG", ""))
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

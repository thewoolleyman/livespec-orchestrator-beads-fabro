"""Taking the Definition-of-Done judgement on the operator host.

"Judged before admission" requires "the same Definition-of-Done judgement the
`dod_gate` node applies (its prompt, against the item's effective criteria, the
referenced specification headings and the resolved sandbox capabilities)".
"Its prompt" is a claim about BYTES, so this module READS THE NODE'S OWN PROMPT
FILE off the executing payload rather than restating its checks. A host-side
paraphrase would judge by rules that drift from the node's on the first edit to
either, and nothing downstream compares them.

WHAT THE HOST CALL ADDS, AND WHY ONLY THAT. The node ends a pass by falling
through the graph and a failure by emitting one JSON object; a host call has no
graph to fall through, so a pass and a reply nobody could read would be the same
bytes. The appended ending contract therefore asks for a verdict object in BOTH
directions and nothing else changes — every check, its order, and every remedy
it names are the file's.

AND "NOTHING ELSE" IS A RULE RATHER THAN A HABIT. `contracts.md`'s
one-rubric-one-subject clause lets a taking other than the node "append only an
ending contract stating the verdict form it must return", and says that "any
other guidance about how to grade a check, including any statement about where
the capability set comes from, MUST be written into the rubric itself, so that
the node grades by it too". This contract used to carry a capability-source
bullet of its own — the published file is unreachable from a host, so resolve the
set from the committed array — which is grading guidance the node never reads. It
is gone, and not relocated: the rubric already resolves the capability set in its
own order, and what a host call owes is to grade by that order rather than to
replace it. Every measured preflight-versus-in-run disagreement on this
repository's own items is the same shape one layer up, so the discipline is the
point: a sentence that changes an answer belongs in the one file both takings
read.

WHY THE SUBJECT CARRIES THE REFERENCED HEADING BODIES. A headless `claude -p`
grants no tools by default, so the judge is given a read-only grant AND the
heading bodies inline: the grant lets it search `scenarios.md` as the
reference-coverage check requires, and the inline bodies mean the assertion can
still be judged against its governing heading on a host where that search
returns nothing.

WHY EVERY FAILURE CAUSE IS MEASURED RATHER THAN PROBED. The runner already maps
an absent executable to exit 127, a timeout to exit 124 and a launch the
operating system refuses to exit 126, so reading those codes reports what
actually happened. A separate probe of our own — "is the judge installed?" —
would be a second instrument that can disagree with the one that ran, and the
disagreement would be invisible: both answers are plausible and neither names
the other.

THE PROMPT FILE REMOVES THE ARGV-SIZE FAILURE from this taking: a subject may
inline every referenced heading without becoming one oversized argv entry. A
launch failure can still occur for another operating-system reason, and the
runner's generic launch-failure arm keeps it a `judge-command-failed`
did-not-run verdict instead of an `OSError` escaping the pre-dispatch wall, the
intake routing and the approve valve. It is deliberately NOT
`no-eligible-model`: the candidate resolved, so the invocation rather than the
chain is what failed.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
    judgement_subject,
    parse_judgement_reply,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_prompt import (
    HOST_ENDING_CONTRACT,
    dod_gate_prompt_path,
    judgement_argv,
    judgement_prompt,
    judgement_rubric,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CAUSE_INPUT_LIMIT",
    "CAUSE_JUDGEMENT_TIMED_OUT",
    "CAUSE_JUDGE_COMMAND_FAILED",
    "CAUSE_NO_ELIGIBLE_MODEL",
    "CAUSE_PROMPT_UNREADABLE",
    "HOST_ENDING_CONTRACT",
    "dod_gate_prompt_path",
    "judgement_argv",
    "judgement_prompt",
    "judgement_rubric",
    "resolve_judge_path",
    "resolve_judge_timeout_seconds",
    "run_dod_gate_prompt",
    "run_dod_judgement",
]

# The three conditions the clause names as "cannot be run" that are properties
# of the INVOCATION, plus the one property of the payload. Each is one stable
# string, because the did-not-run record is capped per distinct cause and a
# cause carrying a varying detail would make every attempt distinct.
CAUSE_NO_ELIGIBLE_MODEL = "no-eligible-model"
CAUSE_JUDGEMENT_TIMED_OUT = "judgement-timed-out"
CAUSE_JUDGE_COMMAND_FAILED = "judge-command-failed"
CAUSE_INPUT_LIMIT = "input-limit-reached"
CAUSE_PROMPT_UNREADABLE = "dod-gate-prompt-unreadable"

# The runner's own mapping of a caught invocation failure, which is where these
# two numbers come from rather than from any convention restated here.
_EXIT_TIMED_OUT = 124
_EXIT_EXECUTABLE_ABSENT = 127
_CODEX_AGENT = "codex-acp"
_CODEX_SANDBOX_SETTINGS = frozenset({"sandbox_mode", "approval_policy"})
_CLAUDE_AGENT = "claude-acp"
_PROMPT_FILE_PREFIX = "livespec-dod-gate-"


@dataclass(frozen=True, kw_only=True)
class _CandidateChainResult:
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


def run_dod_judgement(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    item: WorkItem,
    cwd: Path,
    comments: Sequence[str] = (),
    rubric: str | None = None,
    runner: CommandRunner | None = None,
    payload_root: Path | None = None,
    governing: GoverningHeadingVerdict | None = None,
) -> DodJudgement:
    """Take the judgement for ONE item, or report why it could not be taken.

    An unreadable prompt returns BEFORE the judge is invoked: a judgement with
    no prompt is not the judgement the clause names, and spending a model call
    on whatever is left would produce a verdict against rules nobody wrote.

    `comments` is the item's ledger comment bodies, oldest first. They travel
    into the SUBJECT rather than being read here, and the default is empty for
    the reason `judgement_subject` records.

    `rubric` is the gate prompt's bytes. A caller that already holds them — the
    gate, which needs their digest before it decides anything — hands them in, so
    the bytes the judge grades by and the bytes the record names are ONE reading.
    Omitting it reads the file here, which is what keeps every other caller
    unchanged; an unreadable one returns BEFORE the judge is invoked, because a
    judgement with no rubric is not the judgement the clause names and spending a
    model call on whatever is left would produce a verdict against rules nobody
    wrote.

    `governing` is the spec-stated judgement's verdict about which clauses
    govern these assertions. It travels into the SUBJECT rather than into the
    appended contract, which is the one-rubric-one-subject clause's own
    division: a host taking "MAY append only an ending contract stating the
    verdict form it must return", so anything that changes how a check is
    graded belongs in the rubric or in the subject the node also reads.
    """
    gate_prompt = judgement_rubric(payload_root=payload_root) if rubric is None else rubric
    if gate_prompt is None:
        return DodJudgement(outcome=JUDGEMENT_UNAVAILABLE, cause=CAUSE_PROMPT_UNREADABLE)
    active_runner = ShellCommandRunner() if runner is None else runner
    prompt = judgement_prompt(
        gate_prompt=gate_prompt,
        subject=judgement_subject(item=item, cwd=cwd, comments=comments, governing=governing),
    )
    result = run_dod_gate_prompt(
        prompt=prompt,
        cwd=cwd,
        runner=active_runner,
        is_verdict=lambda text: parse_judgement_reply(reply=text).outcome != JUDGEMENT_UNAVAILABLE,
    )
    if result.reply is not None:
        parsed = parse_judgement_reply(reply=result.reply)
        usage = result.usage
        return DodJudgement(
            outcome=parsed.outcome,
            findings=parsed.findings,
            cause=parsed.cause,
            deciding_candidate=result.deciding_candidate,
            input_tokens=None if usage is None else usage.total_tokens,
            input_usage="unreported" if usage is None else usage.status,
            bound_ended_candidates=result.bound_ended_candidates,
        )
    return DodJudgement(
        outcome=JUDGEMENT_UNAVAILABLE,
        cause=result.cause or CAUSE_NO_ELIGIBLE_MODEL,
        bound_ended_candidates=result.bound_ended_candidates,
    )


def run_dod_gate_prompt(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
) -> _CandidateChainResult:
    """Run the resolved `dod_gate` candidates in order, closing stdin for each.

    A candidate that cannot run or produces a reply the caller cannot parse
    advances the ordered fallback chain. The first parseable verdict returns
    immediately, so no later candidate can run after a judgement is decided.
    """
    resolved = dod_gate_candidates(cwd=cwd)
    if resolved is None:
        return _CandidateChainResult(reply=None, cause=CAUSE_NO_ELIGIBLE_MODEL)
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
            return _CandidateChainResult(
                reply=result.result.stdout,
                cause="",
                deciding_candidate=_candidate_label(candidate=candidate),
                usage=result.usage,
                bound_ended_candidates=tuple(bound_ended),
            )
        last_cause = "unparseable-verdict"
    return _CandidateChainResult(
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
                output: list[str] = []
                ended_by_input_limit = False

                def stop_at_input_limit(line: str) -> bool:
                    nonlocal ended_by_input_limit
                    output.append(line)
                    usage = candidate_input_usage(output="".join(output))
                    ended_by_input_limit = usage.reached_limit
                    return ended_by_input_limit

                result = streaming(
                    argv=argv,
                    cwd=cwd,
                    timeout_seconds=timeout_seconds,
                    on_stdout_line=stop_at_input_limit,
                    env=judge_environ,
                    stdin=handle.fileno(),
                )
                return _CandidateRun(
                    result=result,
                    usage=candidate_input_usage(output=result.stdout),
                    ended_by_input_limit=ended_by_input_limit,
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

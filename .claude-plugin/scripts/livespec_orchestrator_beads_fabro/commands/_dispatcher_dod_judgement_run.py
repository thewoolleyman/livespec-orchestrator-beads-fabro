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

import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    OUTCOME_VERDICT,
    CandidateAttempt,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_command import (
    candidate_command,
    candidate_model,
    resolve_judge_timeout_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    CAUSE_UNPARSEABLE_VERDICT,
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
    judgement_subject,
    parse_judgement_reply,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import executing_payload_root
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    attempt,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        CommandResult,
        CommandRunner,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CAUSE_JUDGEMENT_TIMED_OUT",
    "CAUSE_JUDGE_COMMAND_FAILED",
    "CAUSE_NO_ELIGIBLE_MODEL",
    "CAUSE_PROMPT_UNREADABLE",
    "HOST_ENDING_CONTRACT",
    "GateChainResult",
    "dod_gate_prompt_path",
    "judgement_prompt",
    "judgement_rubric",
    "run_dod_gate_chain",
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
CAUSE_PROMPT_UNREADABLE = "dod-gate-prompt-unreadable"

# The runner's own mapping of a caught invocation failure, which is where these
# two numbers come from rather than from any convention restated here.
_EXIT_TIMED_OUT = 124
_EXIT_EXECUTABLE_ABSENT = 127
_PROMPT_FILE_PREFIX = "livespec-dod-gate-"

# The ONE thing a host taking appends, and the whole of it: the verdict form.
# PUBLIC, because the repository preflight appends the identical bytes — a second
# copy over there is two ending contracts that can drift, and a drifted one makes
# the preflight's verdict unreadable while the judge it ran was perfectly healthy.
HOST_ENDING_CONTRACT = """
## How THIS taking of the judgement ends — a host call, not a node

You are running as a host call rather than as a node of a graph, so ONE thing
replaces the "How to end" section above. Nothing else changes: every check, its
order, and every remedy it names are exactly as written, and this section adds
no rule of its own about how to grade any of them.

There is no graph to fall through, so end with a JSON object on the LAST line of
your reply in BOTH directions:

- every check clean: {"outcome": "passed"}
- any finding: {"outcome": "failed", "failure_reason": "<the findings>"}, one
  finding per line inside `failure_reason`, each naming the work-item id, the
  offending element quoted verbatim, and the remedy.

A reply whose last line is neither is read as a judgement that could not run,
and the item is then routed exactly as it would be without the judgement.

## The work-item under judgement

It follows verbatim.

"""


def dod_gate_prompt_path(*, payload_root: Path | None = None) -> Path:
    """Where the `dod_gate` node's own prompt sits under a payload root.

    Resolved through `executing_payload_root` rather than `plugin_root`, because
    this is a packaged ASSET read: it must keep resolving after the installation
    the running code was copied from has been evicted.
    """
    root = executing_payload_root() if payload_root is None else payload_root
    return root / ".fabro" / "workflows" / RESERVED_WORKFLOW_NAME / "prompts" / "dod-gate.md"


def judgement_rubric(*, payload_root: Path | None = None) -> str | None:
    """The executing build's `dod-gate.md` bytes, or `None` when unreadable.

    PUBLIC because the GATE reads it, not this module: the rubric's digest is
    half the reuse condition, so it has to be in hand before the gate decides
    whether to take a judgement at all. Reading it twice — once to decide and
    once to grade — would be two readings of a file a release can replace
    between them, and the verdict would then name a rubric the judge never saw.
    """
    read = attempt(
        action=lambda: dod_gate_prompt_path(payload_root=payload_root).read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    return None if isinstance(read, AttemptFailure) else read


def judgement_prompt(*, gate_prompt: str, subject: str) -> str:
    """The node's prompt, the host ending contract, then the item's subject."""
    return f"{gate_prompt}{HOST_ENDING_CONTRACT}{subject}\n"


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
    chain = run_dod_gate_chain(
        prompt=prompt,
        cwd=cwd,
        runner=active_runner,
        is_verdict=lambda text: parse_judgement_reply(reply=text).outcome != JUDGEMENT_UNAVAILABLE,
    )
    if chain.reply is not None:
        return replace(parse_judgement_reply(reply=chain.reply), attempts=chain.attempts)
    return DodJudgement(
        outcome=JUDGEMENT_UNAVAILABLE,
        cause=chain.cause or CAUSE_NO_ELIGIBLE_MODEL,
        attempts=chain.attempts,
    )


@dataclass(frozen=True, kw_only=True)
class GateChainResult:
    """What the `dod_gate` chain produced: a reply or a cause, and who was asked.

    `attempts` names every candidate the chain ran, in order, so a caller can say
    which legs ran and which one ended the chain without re-deriving it.
    """

    reply: str | None
    cause: str
    attempts: tuple[CandidateAttempt, ...]


def run_dod_gate_prompt(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
) -> tuple[str | None, str]:
    """The chain's reply and last cause, for a caller that needs no attempt list."""
    chain = run_dod_gate_chain(
        prompt=prompt,
        cwd=cwd,
        runner=runner,
        is_verdict=is_verdict,
        timeout_seconds=timeout_seconds,
    )
    return (chain.reply, chain.cause)


def run_dod_gate_chain(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
) -> GateChainResult:
    """Run the resolved `dod_gate` candidates in order, closing stdin for each.

    A candidate that cannot run or produces a reply the caller cannot parse
    advances the ordered fallback chain. The first parseable verdict returns
    immediately, so no later candidate can run after a judgement is decided.
    """
    resolved = dod_gate_candidates(cwd=cwd)
    if resolved is None:
        return GateChainResult(reply=None, cause=CAUSE_NO_ELIGIBLE_MODEL, attempts=())
    environ = dict(os.environ)
    resolved_timeout = (
        resolve_judge_timeout_seconds(environ=environ)
        if timeout_seconds is None
        else timeout_seconds
    )
    attempts: list[CandidateAttempt] = []
    outcome = CAUSE_NO_ELIGIBLE_MODEL
    for candidate in resolved:
        result = _run_candidate(
            candidate=candidate,
            prompt=prompt,
            cwd=cwd,
            runner=runner,
            environ=environ,
            timeout_seconds=resolved_timeout,
        )
        outcome = _candidate_outcome(result=result, is_verdict=is_verdict)
        attempts.append(
            CandidateAttempt(
                agent=candidate.agent_id or candidate.adapter.command,
                model=candidate_model(candidate=candidate),
                exit_code=result.exit_code,
                outcome=outcome,
            )
        )
        if outcome == OUTCOME_VERDICT:
            return GateChainResult(reply=result.stdout, cause="", attempts=tuple(attempts))
    return GateChainResult(reply=None, cause=outcome, attempts=tuple(attempts))


def _candidate_outcome(*, result: CommandResult, is_verdict: Callable[[str], bool]) -> str:
    """What one candidate's run amounted to: a verdict, or the cause that moved on."""
    if result.exit_code != 0:
        return _invocation_cause(exit_code=result.exit_code)
    return OUTCOME_VERDICT if is_verdict(result.stdout) else CAUSE_UNPARSEABLE_VERDICT


def _run_candidate(
    *,
    candidate: AcpCandidate,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    environ: dict[str, str],
    timeout_seconds: float,
):
    """Run one configured host candidate with a prompt file as its only stdin."""
    argv, judge_environ = candidate_command(candidate=candidate, environ=environ)
    with tempfile.TemporaryDirectory(prefix=_PROMPT_FILE_PREFIX) as scratch:
        prompt_path = Path(scratch) / "prompt.txt"
        _ = prompt_path.write_text(prompt, encoding="utf-8")
        with prompt_path.open("rb") as handle:
            return runner.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=judge_environ,
                stdin=handle.fileno(),
            )


def _invocation_cause(*, exit_code: int) -> str:
    if exit_code == _EXIT_EXECUTABLE_ABSENT:
        return CAUSE_NO_ELIGIBLE_MODEL
    if exit_code == _EXIT_TIMED_OUT:
        return CAUSE_JUDGEMENT_TIMED_OUT
    return CAUSE_JUDGE_COMMAND_FAILED

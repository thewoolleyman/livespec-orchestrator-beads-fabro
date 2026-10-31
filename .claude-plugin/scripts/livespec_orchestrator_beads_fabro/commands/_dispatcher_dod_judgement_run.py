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

WHY THE SUBJECT CARRIES THE REFERENCED HEADING BODIES. The host judge receives
an empty tool set, so the heading bodies travel inline: it can grade the
assertion against its governing heading without a repository search, and no
exploratory tool call can turn one judgement into a multi-request session.

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

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    unavailable_report,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
    CAUSE_INPUT_LIMIT,
    CAUSE_JUDGE_COMMAND_FAILED,
    CAUSE_JUDGEMENT_TIMED_OUT,
    CAUSE_NO_ELIGIBLE_MODEL,
    CandidateChainResult,
    run_candidate_chain,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_capabilities import (
    BASELINE_CAPABILITY,
    mirrored_sandbox_capabilities,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

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

CAUSE_PROMPT_UNREADABLE = "dod-gate-prompt-unreadable"


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
    configured_capabilities = mirrored_sandbox_capabilities(block=dispatcher_block(cwd=cwd))
    sandbox_capabilities = (
        configured_capabilities
        if isinstance(configured_capabilities, tuple) and configured_capabilities
        else (BASELINE_CAPABILITY,)
    )
    prompt = judgement_prompt(
        gate_prompt=gate_prompt,
        subject=judgement_subject(item=item, cwd=cwd, comments=comments, governing=governing),
        sandbox_capabilities=sandbox_capabilities,
    )
    result = run_dod_gate_prompt(
        prompt=prompt,
        cwd=cwd,
        runner=active_runner,
        is_verdict=lambda text: parse_judgement_reply(reply=text).outcome != JUDGEMENT_UNAVAILABLE,
        bound_input=True,
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
            attempts=result.attempts,
        )
    cause = result.cause or CAUSE_NO_ELIGIBLE_MODEL
    _ = sys.stderr.write(f"{unavailable_report(cause=cause, attempts=result.attempts)}\n")
    return DodJudgement(
        outcome=JUDGEMENT_UNAVAILABLE,
        cause=cause,
        bound_ended_candidates=result.bound_ended_candidates,
        attempts=result.attempts,
    )


def run_dod_gate_prompt(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    is_verdict: Callable[[str], bool],
    timeout_seconds: float | None = None,
    bound_input: bool = False,
) -> CandidateChainResult:
    """Run the resolved `dod_gate` candidates in order, closing stdin for each.

    A candidate that cannot run or produces a reply the caller cannot parse
    advances the ordered fallback chain. The first parseable verdict returns
    immediately, so no later candidate can run after a judgement is decided.

    `bound_input` is off unless the caller turns it on: the input bound belongs
    to the pre-admission and pre-dispatch takings alone, so only
    `run_dod_judgement` enables it.
    """
    return run_candidate_chain(
        prompt=prompt,
        cwd=cwd,
        runner=runner,
        is_verdict=is_verdict,
        timeout_seconds=timeout_seconds,
        candidate_resolver=dod_gate_candidates,
        bound_input=bound_input,
    )

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

THE 126 CASE IS THIS CALL'S OWN EXPOSURE rather than a courtesy, because the
whole prompt travels as ONE argv entry and `judgement_subject` inlines the
verbatim body of every heading the item's reference line names. Linux caps a
single entry at 131072 bytes, so an item citing a large governing heading
renders an entry the kernel refuses, and the runner's generic launch-failure
arm is what keeps that a `judge-command-failed` did-not-run verdict instead of
an `OSError` escaping the pre-dispatch wall, the intake routing and the approve
valve. It is deliberately NOT `no-eligible-model`: the judge resolved, so the
remedy is a smaller subject rather than an installed binary.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_UNAVAILABLE,
    DodJudgement,
    judgement_subject,
    parse_judgement_reply,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import executing_payload_root
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    FloatParseFailure,
    attempt,
    parse_float,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "CAUSE_JUDGEMENT_TIMED_OUT",
    "CAUSE_JUDGE_COMMAND_FAILED",
    "CAUSE_NO_ELIGIBLE_MODEL",
    "CAUSE_PROMPT_UNREADABLE",
    "HOST_ENDING_CONTRACT",
    "dod_gate_prompt_path",
    "judgement_argv",
    "judgement_prompt",
    "judgement_rubric",
    "resolve_judge_model",
    "resolve_judge_path",
    "resolve_judge_timeout_seconds",
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

_JUDGE_PATH_ENV = "LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH"
_MODEL_ENV = "LIVESPEC_DOD_JUDGEMENT_MODEL"
_TIMEOUT_ENV = "LIVESPEC_DOD_JUDGEMENT_TIMEOUT_SECONDS"
_DEFAULT_MODEL = "claude-opus-4-8"
_DEFAULT_TIMEOUT_SECONDS = 600.0
_JUDGE_EXECUTABLE = "claude"
_CONVENTIONAL_JUDGE_PATH = "~/.local/bin/claude"
# The read-only grant check 6 needs to search `scenarios.md` for a governing
# scenario before concluding none does. A headless call grants no tool at all by
# default, so without this the judge can only report what it was handed — and
# "no scenario governs this" is exactly the conclusion the prompt forbids it
# from reaching by recollection.
_ALLOWED_TOOLS = "Read,Grep,Glob"
# The runner's own mapping of a caught invocation failure, which is where these
# two numbers come from rather than from any convention restated here.
_EXIT_TIMED_OUT = 124
_EXIT_EXECUTABLE_ABSENT = 127

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


def judgement_argv(*, judge_path: str, prompt: str, model: str) -> list[str]:
    """The headless judge invocation — a plain `claude -p`, never a Fabro run."""
    return [
        judge_path,
        "-p",
        prompt,
        "--allowedTools",
        _ALLOWED_TOOLS,
        "--model",
        model,
    ]


def resolve_judge_path(
    *,
    environ: dict[str, str],
    which: Callable[[str], str | None] = shutil.which,
    conventional: Path | None = None,
) -> str:
    """The judge executable: override, then PATH, then the conventional install.

    The last resort is the BARE NAME rather than a verdict of our own that no
    model is eligible. Letting the runner fail to exec it reports the absence as
    the measurement it is — exit 127 — instead of as a guess this resolver made
    without trying.
    """
    override = environ.get(_JUDGE_PATH_ENV, "").strip()
    if override:
        return override
    found = which(_JUDGE_EXECUTABLE)
    if found is not None:
        return found
    local_bin = (
        Path(_CONVENTIONAL_JUDGE_PATH).expanduser() if conventional is None else conventional
    )
    if local_bin.is_file():
        return str(local_bin)
    return _JUDGE_EXECUTABLE


def resolve_judge_model(*, environ: dict[str, str]) -> str:
    """The judging model: the env override, else the committed default."""
    return environ.get(_MODEL_ENV, "").strip() or _DEFAULT_MODEL


def resolve_judge_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The judge's time box, falling back on an absent, bad or non-positive value.

    A zero or negative box is a self-inflicted hang rather than a tighter
    bound, and an unparseable one must not crash a path whose whole contract is
    to fail soft, so both read as the committed default.
    """
    raw = environ.get(_TIMEOUT_ENV, "")
    parsed = parse_float(text=raw)
    if isinstance(parsed, FloatParseFailure):
        return _DEFAULT_TIMEOUT_SECONDS
    return parsed if parsed > 0 else _DEFAULT_TIMEOUT_SECONDS


def run_dod_judgement(
    *,
    item: WorkItem,
    cwd: Path,
    comments: Sequence[str] = (),
    rubric: str | None = None,
    runner: CommandRunner | None = None,
    payload_root: Path | None = None,
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
    """
    gate_prompt = judgement_rubric(payload_root=payload_root) if rubric is None else rubric
    if gate_prompt is None:
        return DodJudgement(outcome=JUDGEMENT_UNAVAILABLE, cause=CAUSE_PROMPT_UNREADABLE)
    environ = dict(os.environ)
    credential = select_factory_credential(
        environ=environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"{message}\n"),
    )
    judge_environ = dict(environ)
    judge_environ[CLAUDE_OAUTH_TOKEN_ENV] = environ.get(credential.env_name, "")
    active_runner = ShellCommandRunner() if runner is None else runner
    result = active_runner.run(
        argv=judgement_argv(
            judge_path=resolve_judge_path(environ=environ),
            prompt=judgement_prompt(
                gate_prompt=gate_prompt,
                subject=judgement_subject(item=item, cwd=cwd, comments=comments),
            ),
            model=resolve_judge_model(environ=environ),
        ),
        cwd=cwd,
        timeout_seconds=resolve_judge_timeout_seconds(environ=environ),
        env=judge_environ,
    )
    if result.exit_code != 0:
        return DodJudgement(
            outcome=JUDGEMENT_UNAVAILABLE, cause=_invocation_cause(exit_code=result.exit_code)
        )
    return parse_judgement_reply(reply=result.stdout)


def _invocation_cause(*, exit_code: int) -> str:
    if exit_code == _EXIT_EXECUTABLE_ABSENT:
        return CAUSE_NO_ELIGIBLE_MODEL
    if exit_code == _EXIT_TIMED_OUT:
        return CAUSE_JUDGEMENT_TIMED_OUT
    return CAUSE_JUDGE_COMMAND_FAILED

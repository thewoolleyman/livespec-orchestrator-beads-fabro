"""The model the drift pass puts the shared spec-stated judgement through.

The one IMPURE seam `livespec_runtime.spec_stated.judge` is given: a
`ModelRunner` taking a rendered prompt and returning the model's reply. The
judgement itself — the prompt, the verdict schema, the parser — belongs to the
shared runtime module, which "opens no subprocess, no socket and no network
connection of its own and holds no credential"; everything a provider binding
needs is here.

⛔ THE PROMPT TRAVELS ON STANDARD INPUT, NOT AS AN ARGV ENTRY, and that is a
correctness requirement rather than a style choice. The judge prompt carries
the ENTIRE ratified spec tree, which is 1.36 MB in this repository as measured
2026-10-22, while Linux caps a single argv entry at 131072 bytes. A prompt
passed as an argument would make `execve` refuse the launch outright — the
runner maps that to exit 126 — so every merge of every pass would report a
judgement that could not be taken, for a reason nothing in the output names.
`claude -p` with no prompt argument reads the prompt from standard input, so
the prompt is written to a temporary file and that file's descriptor is handed
to the runner.

The temporary file is deleted as the context manager closes, after the child
has exited, which is what keeps a 1.36 MB prompt from accumulating on the host
across the ten-minute ticks of the root reconcile timer.

WHICH EXECUTABLE, MODEL AND CREDENTIAL APPLY IS NOT THIS MODULE'S DECISION.
The Definition-of-Done chain resolves them through the configured `dod_gate`
candidate, so this taking has the same Codex-first order and the same fallback
behaviour as host Definition-of-Done judgements rather than a second provider
or model policy of its own.

A NON-ZERO EXIT ANSWERS THE EMPTY STRING, deliberately. The shared judgement's
parser treats a reply it cannot read as a `Failure`, and the drift pass maps
that to one UNPROCESSED merge — which stops the frontier at it. That is the
fail-closed route and it needs no exception: raising here would kill the whole
pass over one merge the next tick would retry anyway, losing every later
merge's finding with it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast, get_args

from livespec_runtime import spec_stated

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    candidate_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
    run_candidate_chain,
)
from livespec_orchestrator_beads_fabro.effects import FloatParseFailure, parse_float

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS",
    "DRIFT_JUDGE_TIMEOUT_ENV",
    "drift_judge",
    "resolve_drift_judge_timeout_seconds",
]

ReplyShape = Literal["verdict", "item_class"]

DRIFT_JUDGE_TIMEOUT_ENV = "LIVESPEC_DRIFT_JUDGE_TIMEOUT_SECONDS"
DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS = 600.0


def resolve_drift_judge_timeout_seconds(*, environ: dict[str, str]) -> float:
    """The judge's time box, falling back on an absent, bad or non-positive value.

    A zero or negative box is a self-inflicted hang rather than a tighter
    bound, and an unparseable one must not crash a pass whose whole contract is
    to fail soft per merge, so both read as the committed default.
    """
    parsed = parse_float(text=environ.get(DRIFT_JUDGE_TIMEOUT_ENV, ""))
    if isinstance(parsed, FloatParseFailure):
        return DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_DRIFT_JUDGE_TIMEOUT_SECONDS


def drift_judge(
    *,
    project_root: Path,
    runner: CommandRunner,
    caller: str,
    payload_root: Path | None = None,
    reply: ReplyShape = "verdict",
) -> spec_stated.ModelRunner:
    """A `ModelRunner` that puts one rendered prompt to the headless judge.

    `caller` is REQUIRED, with no default, because a default would attribute
    every launcher that forgot to name itself to one named judgement. It is the
    identifier-shaped `livespec.caller` value the spawn carries.

    `reply` names the SHAPE the caller's prompt is answered in, because the
    shared chain advances to its next candidate on any reply its shape check
    does not recognise. The judgement answers with a JSON verdict object and the
    classification with one bare item-class word, so a runner built for one
    shape discards every reply of the other as unparseable.

    Returned as a closure rather than a class so that the model, the time box
    and the credential are resolved ONCE per pass: a pass over ten merges must
    not re-read the environment ten times, where two readings of one variable
    could disagree while both looked healthy.
    """
    del payload_root
    # A LAMBDA over a keyword-only helper, because `ModelRunner` is the shared
    # runtime's own type and `spec_stated.judge` calls it POSITIONALLY: the one
    # positional parameter here is fixed by a caller outside this repository,
    # and everything this module itself defines stays keyword-only.
    return lambda prompt: _judged(
        prompt=prompt,
        cwd=project_root,
        runner=runner,
        reply=reply,
        caller=caller,
    )


def _judged(
    *,
    prompt: str,
    cwd: Path,
    runner: CommandRunner,
    reply: ReplyShape,
    caller: str,
) -> str:
    """One prompt through the shared chain, or no reply when every candidate fails.

    Each candidate the chain ran is reported on standard error, because a drift
    pass and a governing-heading read write no ledger record of their own.
    """
    is_reply = _looks_like_item_class if reply == "item_class" else _looks_like_spec_stated_verdict
    chain = run_candidate_chain(
        prompt=prompt,
        cwd=cwd,
        runner=runner,
        is_verdict=lambda text: is_reply(text=text),
        timeout_seconds=resolve_drift_judge_timeout_seconds(environ=dict(os.environ)),
        caller=caller,
    )
    for ran in chain.attempts:
        _ = sys.stderr.write(f"{candidate_report(attempt=ran)}\n")
    return chain.reply or ""


def _looks_like_item_class(*, text: str) -> bool:
    """Whether a reply is exactly one member of the classification vocabulary."""
    return text.strip() in get_args(spec_stated.ItemClass)


def _looks_like_spec_stated_verdict(*, text: str) -> bool:
    """Whether a reply has the minimum parseable shape of a spec-stated verdict."""
    try:
        decoded: object = json.loads(text)
    except ValueError:
        return False
    if not isinstance(decoded, dict):
        return False
    kind = cast("dict[str, object]", decoded).get("kind")
    return isinstance(kind, str) and kind in get_args(spec_stated.StatedKind)

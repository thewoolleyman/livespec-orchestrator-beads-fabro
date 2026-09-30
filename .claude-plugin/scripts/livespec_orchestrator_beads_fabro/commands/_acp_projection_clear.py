"""The operator's clearance of ONE projection-failure fact, by its exact id.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": the projection-failure fact "clears only after successful
idempotent projection for the run/node or an attributed,
reason-required, append-only operator clearance naming that exact fact
id. Clearance retires the fact only and MUST NOT mint, retire, or
reinterpret a hold; run absence alone is never resolution."

THIS IS A THIRD VALVE AND IT TOUCHES NO HOLD. The legacy
`clear-provider-exhaustion` retires a vendor-wide record;
`clear-acp-availability-hold` retires typed observations on an exact
scope and key; this one retires an ATTENTION FACT about an unread event
stream. Its record carries no scope, no hold key and no candidate
identity, so there is no field a later reader could mistake for a hold
target -- the prohibition is a property of the record's shape rather
than a rule someone has to remember.

THE TWO HUMAN-ONLY REFUSALS ARE THE SIBLING VALVE'S, FOR ITS REASONS. A
blank `--reason` is refused because a clearance asserts something no
observation supports; an invocation resolving to the unattributed mark
is refused outright, not under `dispatcher.require_invoker`, because
that mark is exactly what an unattended process carries by default and
this must stay a human act rather than becoming a second automatic
resolution path beside successful projection.

THE THIRD REFUSAL IS EXACTNESS. A fact id naming nothing unresolved is
refused rather than written, because an append-only clearance of a fact
that does not exist is indistinguishable, later, from one that silently
missed its target by a typo -- and the target here is a long
`<repo>:<run>:<node>` string a person types by hand.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    PROJECTION_FACT_PREFIX,
    projection_failure_clearance_record,
    unresolved_projection_failures,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    FALLBACK_SOURCE,
    INVOKER_ENV_VAR,
    INVOKER_FLAG,
    add_invoker_argument,
    invoker_from_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_clear_model_fallback_projection_arguments",
    "run_clear_model_fallback_projection_command",
]

_COMMAND = "clear-model-fallback-projection"

_BLANK_REASON_REFUSAL = (
    f"ERROR: {_COMMAND} refused: --reason is blank.\n"
    "A clearance asserts the run's event stream no longer needs projecting, which no "
    "successful projection recorded; state why on the record.\n"
)


def add_clear_model_fallback_projection_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the exact-fact clearance flag surface to its subparser."""
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument(
        "--fact-id",
        dest="fact_id",
        required=True,
        help=f"the exact {PROJECTION_FACT_PREFIX}:<repo>:<run>:<node> fact to retire",
    )
    _ = parser.add_argument(
        "--reason",
        dest="reason",
        required=True,
        help="why the operator knows this run's unread event stream no longer matters",
    )
    _ = parser.add_argument("--journal", dest="journal", default=None)


def run_clear_model_fallback_projection_command(*, args: argparse.Namespace) -> int:
    """Retire ONE projection-failure fact, touching no availability hold."""
    reason = str(args.reason).strip()
    if not reason:
        _ = write_stderr(text=_BLANK_REASON_REFUSAL)
        return EXIT_PRECONDITION_ERROR
    identity = invoker_from_args(args=args)
    if identity.invoker_source == FALLBACK_SOURCE:
        _ = write_stderr(text=_unattributed_refusal(invoker=identity.invoker))
        return EXIT_PRECONDITION_ERROR
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    path = journal_path(args=args, repo=repo)
    fact_id = str(args.fact_id)
    if all(
        failure.fact_id != fact_id for failure in unresolved_projection_failures(journal_path=path)
    ):
        _ = write_stderr(text=_nothing_unresolved_refusal(fact_id=fact_id))
        return EXIT_PRECONDITION_ERROR
    JournalFile(path=path, identity=identity).append(
        record=projection_failure_clearance_record(fact_id=fact_id, reason=reason)
    )
    _ = write_stdout(text=f"CLEARED  {fact_id}  by {identity.invoker}: {reason}\n")
    return 0


def _unattributed_refusal(*, invoker: str) -> str:
    """The refusal text for an invocation that asserted no identity."""
    return (
        f"ERROR: {_COMMAND} refused: this invocation asserted no identity "
        f"(resolved {invoker} as {FALLBACK_SOURCE}).\n"
        "Retiring an unread-event-stream fact is a human act by construction and is never "
        f"taken on an unattributed invocation: pass {INVOKER_FLAG} <id> or set the "
        f"{INVOKER_ENV_VAR} environment variable.\n"
    )


def _nothing_unresolved_refusal(*, fact_id: str) -> str:
    """The refusal text naming a fact id that stands unresolved nowhere."""
    return (
        f"ERROR: {_COMMAND} refused: no unresolved projection-failure fact is held under "
        f"{fact_id!r}; nothing to clear.\n"
    )

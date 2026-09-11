"""The operator's EXACT clearance of one typed ACP availability hold.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "An exact scope/key clearance valve MUST be attributed,
reason-required, append-only, and refuse a nonexistent live target; the
legacy provider valve addresses legacy records only."

THIS IS A SECOND VALVE, NOT A WIDENING OF THE FIRST. The legacy
`clear-provider-exhaustion` subcommand retires a provider-wide record
and knows nothing of candidate identity; it stays exactly as it was.
This one names a scope and key, retires only the observations live on
that exact target, and writes its own `acp-availability-cleared` stage,
which the legacy reverse scan never reads. Two separate stages is what
makes "the legacy provider valve addresses legacy records only" a
property of the data rather than a rule.

THE TWO REFUSALS THAT KEEP THIS FROM BECOMING A SECOND EXPIRY PATH are
the ones the legacy valve already carries, for the same reasons, and are
deliberately spelled the same way:

- A blank `--reason` is refused. A clearance asserts a fact about the
  world that no observation supports, so the assertion has to be stated
  on the record rather than inferred from the act.
- An invocation asserting NO identity is refused outright, not under the
  `dispatcher.require_invoker` dial. The fallback `unattributed:<user>@
  <host>` mark is exactly what an unattended process carries by default,
  so refusing it is what makes "a human triggered this" a property of
  the record instead of a hope.

A THIRD REFUSAL IS SPECIFIC TO EXACTNESS. The scope and key must name a
target that is actually live, and the two scopes carry different key
shapes: a candidate-scoped clearance MUST name its `candidate_key` and a
domain-scoped one MUST NOT. Accepting a half-specified target would let
`--scope candidate --hold-key codex` clear something -- the nearest
match, the whole domain -- and an operator who meant one entitlement
would silently un-hold every candidate on the provider.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    CANDIDATE_SCOPE,
    DOMAIN_SCOPE,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import (
    acp_hold_clearance_record,
    live_holds_for_target,
    read_acp_hold_ledger,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    FALLBACK_SOURCE,
    INVOKER_ENV_VAR,
    INVOKER_FLAG,
    InvokerIdentity,
    add_invoker_argument,
    invoker_from_args,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_clear_acp_availability_hold_arguments",
    "run_clear_acp_availability_hold_command",
]

_COMMAND = "clear-acp-availability-hold"

_BLANK_REASON_REFUSAL = (
    f"ERROR: {_COMMAND} refused: --reason is blank.\n"
    "A clearance asserts the entitlement is available again, which no observation "
    "supports; state why on the record.\n"
)


def _nothing_held_refusal(*, scope: str, key: str) -> str:
    """The refusal text naming the exact target that holds nothing."""
    return (
        f"ERROR: {_COMMAND} refused: no live observation is held on scope {scope} "
        f"key {key}; nothing to clear.\n"
    )


def _unattributed_refusal(*, invoker: str) -> str:
    """The refusal text for an invocation that asserted no identity."""
    return (
        f"ERROR: {_COMMAND} refused: this invocation asserted no identity "
        f"(resolved {invoker} as {FALLBACK_SOURCE}).\n"
        "Manual clearance is a human act by construction and is never taken on an "
        f"unattributed invocation: pass {INVOKER_FLAG} <id> or set the {INVOKER_ENV_VAR} "
        "environment variable.\n"
    )


def _scope_shape_refusal(*, scope: str, candidate_key: str | None) -> str | None:
    """Refuse a key shape that disagrees with the scope it was given."""
    if scope == CANDIDATE_SCOPE and candidate_key is None:
        return (
            f"ERROR: {_COMMAND} refused: scope {CANDIDATE_SCOPE} keys on an exact "
            "(availability_key, candidate_key) pair; pass --candidate-key.\n"
        )
    if scope == DOMAIN_SCOPE and candidate_key is not None:
        return (
            f"ERROR: {_COMMAND} refused: scope {DOMAIN_SCOPE} keys on its hold key "
            "alone; --candidate-key names a target this scope cannot address.\n"
        )
    return None


def add_clear_acp_availability_hold_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Attach the exact-clearance flag surface to its subparser."""
    add_invoker_argument(parser=parser)
    _ = parser.add_argument("--repo", dest="repo", default=None)
    _ = parser.add_argument(
        "--scope",
        dest="scope",
        required=True,
        choices=(DOMAIN_SCOPE, CANDIDATE_SCOPE),
        help="the ratified scope of the observation to retire",
    )
    _ = parser.add_argument(
        "--hold-key",
        dest="hold_key",
        required=True,
        help="the opaque hold key (an availability key, or a declared domain override)",
    )
    _ = parser.add_argument(
        "--candidate-key",
        dest="candidate_key",
        default=None,
        help=f"the candidate key, required for scope {CANDIDATE_SCOPE} and forbidden otherwise",
    )
    _ = parser.add_argument(
        "--reason",
        dest="reason",
        required=True,
        help="why the operator knows this entitlement is available again",
    )
    _ = parser.add_argument("--journal", dest="journal", default=None)


def run_clear_acp_availability_hold_command(*, args: argparse.Namespace) -> int:
    """Retire every live observation on one exact scope and key."""
    reason = str(args.reason).strip()
    if not reason:
        _ = write_stderr(text=_BLANK_REASON_REFUSAL)
        return EXIT_PRECONDITION_ERROR
    identity = invoker_from_args(args=args)
    if identity.invoker_source == FALLBACK_SOURCE:
        _ = write_stderr(text=_unattributed_refusal(invoker=identity.invoker))
        return EXIT_PRECONDITION_ERROR
    candidate_key = None if args.candidate_key is None else str(args.candidate_key)
    shape = _scope_shape_refusal(scope=str(args.scope), candidate_key=candidate_key)
    if shape is not None:
        _ = write_stderr(text=shape)
        return EXIT_PRECONDITION_ERROR
    return _clear(args=args, reason=reason, candidate_key=candidate_key, identity=identity)


def _clear(
    *,
    args: argparse.Namespace,
    reason: str,
    candidate_key: str | None,
    identity: InvokerIdentity,
) -> int:
    """Resolve the live targets and append one clearance, or refuse."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    path = journal_path(args=args, repo=repo)
    scope = str(args.scope)
    hold_key = str(args.hold_key)
    ledger = read_acp_hold_ledger(journal_path=path, now_iso=utc_now_iso())
    held = live_holds_for_target(
        ledger=ledger, scope=scope, hold_key=hold_key, candidate_key=candidate_key
    )
    if not held:
        _ = write_stderr(
            text=_nothing_held_refusal(
                scope=scope, key=_display_key(hold_key=hold_key, candidate_key=candidate_key)
            )
        )
        return EXIT_PRECONDITION_ERROR
    JournalFile(path=path, identity=identity).append(
        record=acp_hold_clearance_record(
            scope=scope,
            hold_key=hold_key,
            candidate_key=candidate_key,
            reason=reason,
            observation_ids=tuple(hold.observation_id for hold in held),
        )
    )
    _ = write_stdout(
        text=(
            f"CLEARED  {scope}  "
            f"{_display_key(hold_key=hold_key, candidate_key=candidate_key)}  "
            f"{len(held)} observation(s)  by {identity.invoker}: {reason}\n"
        )
    )
    return 0


def _display_key(*, hold_key: str, candidate_key: str | None) -> str:
    """The operator-facing rendering of one exact target key."""
    if candidate_key is None:
        return hold_key
    return f"{hold_key}/{candidate_key}"

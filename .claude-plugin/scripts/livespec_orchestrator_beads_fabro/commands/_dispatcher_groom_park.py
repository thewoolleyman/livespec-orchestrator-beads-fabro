"""Consume a groom run's terminal account: park its draft, or file its cut.

BOTH PHASES TERMINATE HERE, because both publish over the one channel a dead
run has. The propose phase publishes a DRAFT and this module records it as a
ledger comment; the apply phase publishes a FILING PLAN and this module hands
it to `_dispatcher_groom_apply`, which files it HOST-SIDE with the tenant
credential the Dispatcher legitimately holds and the factory sandbox
deliberately never gets. The payload's own leading marker discriminates the
two, and that discrimination is load-bearing: recording a plan as a draft
comment would land a fresh draft after the approval and revoke the consent the
plan was published under.

The PARK half of the ratified two-phase groom cut
(`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut"). A groom variant's propose phase drafts
the decomposition, files nothing, and terminates at a needs-human outcome
carrying the draft; the Dispatcher journals that termination and records the
draft on the item as a ledger comment, beside the preserve-by-reference
pointer. `_dispatcher_groom_draft` owns the comment's shape; this module is
where the draft is EXTRACTED from the dead run and written.

WHY IT READS THE RUN'S OWN NEEDS-HUMAN ACCOUNT. A terminated run's account is
already a modelled thing here: the `needs_human` terminal node writes its
prompt to stderr behind this workflow's own sentinel, and
`_fabro_needs_human_question` reads it back off `fabro inspect`. The draft is
that prompt. Reusing the reader means the propose phase publishes its draft
over a channel that already exists, rather than the groom variant needing a
second, groom-only publication route.

WHAT THAT CHANNEL COSTS, stated here because it constrains the groom variant
this module never sees. The sentinel is a stderr LINE, and the reader returns
the text following it ON THAT LINE, so the draft a run publishes is
single-valued by construction: a variant emitting a layered decomposition
across several lines would have only its first line recorded, silently. How a
groom variant encodes its layers into one value is that variant's business;
what this module guarantees is that whatever it published reaches the ledger
verbatim, unescaped and un-rewritten.

WHY A DRAFT CARRYING A TEMPLATE OPENER IS REFUSED RATHER THAN ESCAPED, and why
that is the fail-CLOSED direction even though it withholds the draft. A ledger
comment is append-only -- beads offers neither edit nor delete -- so a comment
carrying a MiniJinja opening delimiter poisons every FUTURE goal render for
that item permanently, killing each dispatch before a run exists. This
repository has already lost records that way. Escaping is not available either:
a rewritten draft is not the draft, and the apply phase would file slices the
propose phase did not write. Refusing costs the draft, which is recoverable --
the preserve-by-reference pointer written beside this one names the run and its
exported tree -- while writing it costs the ITEM, permanently. The skip is
journaled naming the openers so the loss is visible rather than silent.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_workflow import dispatch_workflow_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_apply import file_groom_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_groom_draft import (
    render_groom_draft_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    ShellCommandRunner,
    utc_now_iso,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._fabro_needs_human_question import (
    needs_human_question_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner
from livespec_orchestrator_beads_fabro.commands._groom_filing_plan import is_groom_filing_plan
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import groom_variant_names
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.store import append_work_item_comment
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "GROOM_DRAFT_RECORDED_STAGE",
    "GROOM_DRAFT_SKIPPED_STAGE",
    "record_groom_draft",
]

GROOM_DRAFT_RECORDED_STAGE = "groom-draft-recorded"
GROOM_DRAFT_SKIPPED_STAGE = "groom-draft-skipped"

# The source label the goal preflight's findings carry. It names the RUN's
# output rather than a goal-brief field, because that is what a maintainer
# reading the skip has to go and look at.
_DRAFT_SOURCE = "groom-draft"
_INSPECT_TIMEOUT_SECONDS = 120.0
# Everything this seam can legitimately fail on: the ledger it reads the pin
# from and writes the comment to, and the process boundary the `inspect` call
# crosses. `ShellCommandRunner` already absorbs the two shell-out faults it
# models -- a timeout and an absent binary -- so `OSError` here covers the
# remainder (a permission fault, an exhausted descriptor table) rather than
# the ordinary case.
_RECOVERABLE = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    OSError,
)


def record_groom_draft(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalWriter,
    runner: FabroRunner | None = None,
) -> bool:
    """Record the propose phase's draft, or execute the apply phase's filing plan.

    Returns whether the APPLY phase's approved cut was filed host-side. `True`
    says the slices exist in the ledger and the original closed against them,
    so the caller must NOT then rest the item at `blocked / needs-human`: the
    item is closed, and moving a closed regroom target to `blocked` would undo
    the very disposition the contract calls this run's terminal one. Every
    other path — the propose park, a skip, a non-groom run — returns `False`,
    which leaves the ordinary escalation exactly as it was.

    Fail-soft as a WHOLE, in the same shape `escalate_needs_human_block` is,
    and the placement of that softness is the point: a ledger or a factory this
    seam cannot reach must not turn a needs-human termination into a
    dispatch-path exception, because the escalation that rests the item at
    `blocked / needs-human` runs AFTER this and is what makes the item
    recoverable at all. One wrapper rather than one per fault, so a fault added
    later inherits the guarantee instead of having to remember it.
    """
    recorded = attempt(
        action=lambda: _record_groom_draft(
            args=args, repo=repo, item=item, outcome=outcome, journal=journal, runner=runner
        ),
        exceptions=_RECOVERABLE,
    )
    if isinstance(recorded, AttemptFailure):
        journal.append(
            record={
                "stage": GROOM_DRAFT_SKIPPED_STAGE,
                "work_item_id": item.id,
                "reason": type(recorded.error).__name__,
            }
        )
        return False
    return recorded


def _record_groom_draft(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalWriter,
    runner: FabroRunner | None,
) -> bool:
    if outcome.status != "blocked":
        return False
    config = store_config(repo=repo)
    variant = dispatch_workflow_for(path=config, work_item_id=item.id)
    if variant is None or variant not in groom_variant_names(repo=repo):
        # An implement run reaching a human gate is the ordinary needs-human
        # path and has no draft to record. Silent rather than journaled: it is
        # the common case, and a skip row on every human-gated run would bury
        # the three skips below that DO name something an operator can act on.
        return False
    run_id = outcome.fabro_run_id
    server_url = _factory_server(args=args)
    if run_id is None or server_url is None:
        _skip(journal=journal, item=item, reason="missing-run-or-server", variant=variant)
        return False
    draft = _drafted_decomposition(
        args=args, repo=repo, run_id=run_id, server_url=server_url, runner=runner
    )
    if draft is None:
        _skip(journal=journal, item=item, reason="no-draft-in-run-record", variant=variant)
        return False
    # THE TWO PHASES SHARE ONE CHANNEL, so the payload's own leading marker is
    # what tells them apart. Discriminated BEFORE the poison check below and
    # before any comment is written, because recording an apply phase's filing
    # plan as a draft comment would land a fresh draft AFTER the approval and
    # thereby revoke the consent the plan was published under — the one
    # mistake on this seam that no later dispatch can repair.
    if is_groom_filing_plan(text=draft):
        return file_groom_plan(
            repo=repo, item=item, text=draft, variant=variant, run_id=run_id, journal=journal
        )
    _park_draft(
        config=config, item=item, draft=draft, variant=variant, run_id=run_id, journal=journal
    )
    return False


def _park_draft(
    *,
    config: StoreConfig,
    item: WorkItem,
    draft: str,
    variant: str,
    run_id: str,
    journal: JournalWriter,
) -> None:
    """The PROPOSE phase's ending: the draft as a ledger comment, or a named skip."""
    openers = minijinja_openers_in_text(source=_DRAFT_SOURCE, text=draft)
    if openers:
        _skip(
            journal=journal,
            item=item,
            reason="draft-would-poison-goal",
            variant=variant,
            detail=", ".join(sorted({finding.opener for finding in openers})),
        )
        return
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=render_groom_draft_comment(
            draft=draft, variant=variant, run_id=run_id, at=utc_now_iso()
        ),
    )
    journal.append(
        record={
            "stage": GROOM_DRAFT_RECORDED_STAGE,
            "work_item_id": item.id,
            "workflow_name": variant,
            "run_id": run_id,
        }
    )


def _drafted_decomposition(
    *,
    args: argparse.Namespace,
    repo: Path,
    run_id: str,
    server_url: str,
    runner: FabroRunner | None,
) -> str | None:
    """The terminated run's own needs-human prompt, which is where the draft rides."""
    port = FabroPort(
        fabro_bin=str(args.fabro_bin),
        target=FabroTarget(server_url=server_url),
        runner=runner if runner is not None else ShellCommandRunner(),
        cwd=repo,
    )
    inspected = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    question = needs_human_question_from_payload(payload=inspected.payload)
    return None if question is None else question.prompt


def _factory_server(*, args: argparse.Namespace) -> str | None:
    """The factory this dispatch was sent to, read defensively.

    `fabro_factory_target` is set by the dispatching command paths only, and
    the reconcile and check subcommands reach the post-run sequence with a
    Namespace that never carried it -- the same defensive read
    `_dispatcher_preserve_reference` makes one call earlier.
    """
    target = getattr(args, "fabro_factory_target", None)
    server = getattr(target, "server", None)
    return server if isinstance(server, str) and server != "" else None


def _skip(
    *,
    journal: JournalWriter,
    item: WorkItem,
    reason: str,
    variant: str,
    detail: str = "",
) -> None:
    journal.append(
        record={
            "stage": GROOM_DRAFT_SKIPPED_STAGE,
            "work_item_id": item.id,
            "workflow_name": variant,
            "reason": reason,
            "detail": detail,
        }
    )

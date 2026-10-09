"""Enrich the `resolve-blocked` valve with the terminated run's own account.

An item resting at `blocked / needs-human` already produces exactly one
attention item — the `resolve-blocked:<item-id>:ready` valve lane in
`_needs_attention_work_items.human_valves`. Until now that item carried the
work-item's TITLE and nothing else, so the console offered a decision without
offering anything to decide on: not why the loop gave up, not which run it
was, not whether the work survived.

This module supplies the missing half by reading the run the ledger already
names. Contract v093 means that run is TERMINATED — it did not park and it
cannot be resumed — so the read is pure enrichment of a decision the ledger
has already routed, and the answer stays the existing valve. No attach route,
no resume route, and no second attention item: b3.S2 extends `resolve-blocked`
itself.

FAIL-SOFT IS THE WHOLE POSTURE HERE, and it is what makes the enrichment safe
to attach to a lane that already works. Every step — the ledger read for the
run id, the factory resolution, the `fabro inspect`, the parse — can come back
empty, and each one degrades to the summary the lane would have rendered
anyway. An unreachable factory must cost the enrichment, never the valve: the
human decision is already waiting, and a lane that vanished because a network
read failed would read downstream as a decision that had been made.

TWO READS DECIDE WHICH SERVER IS QUERIED, and the order matters. The item's
own `dispatch_factory` stamp names the factory its run actually went to; the
repository's configured default is the fallback. Resolving the stamped name
through `resolve_fabro_factory` — rather than reading a server url off the
stamp — keeps the target byte-identical to the one a dispatch to that name
would use, and means an undeclared factory resolves to no server and is
skipped rather than queried on a guess. Inspecting the default host for a run
that lives on another is the wrong-population probe this repository
catalogues: it returns cleanly and finds nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import repo_run_attribution
from livespec_orchestrator_beads_fabro.commands._fabro_needs_human_question import (
    NEEDS_HUMAN_NODE_ID,
    NeedsHumanQuestion,
    needs_human_question_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner
from livespec_orchestrator_beads_fabro.commands._fabro_transport_fault import (
    transport_fault_clause,
    transport_fault_from_cause,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.store import dispatch_factory_for

__all__: list[str] = [
    "NeedsHumanRunHandle",
    "needs_human_question_summary",
]

_INSPECT_TIMEOUT_SECONDS = 60.0
_NO_REASON = (
    "the implementer reported a needs-human ending; the engine recorded no "
    "loop failure signature"
)
_NO_PROMPT = "the run record carries no needs-human message"

# The same absorbed set the sibling factory lanes ride: an unreadable config or
# an unreachable tenant costs the ENRICHMENT and never the valve.
_RECOVERABLE: tuple[type[Exception], ...] = (
    OSError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


@dataclass(frozen=True, kw_only=True)
class NeedsHumanRunHandle:
    """The terminated run this blocked item's decision came from."""

    run_id: str
    factory_name: str
    factory_server_url: str


def needs_human_question_summary(
    *,
    project_root: Path,
    item_id: str,
    default_summary: str,
    runner: FabroRunner | None = None,
) -> str:
    """The valve summary, enriched with the run's account when one is readable."""
    read = attempt(
        action=lambda: _question(project_root=project_root, item_id=item_id, runner=runner),
        exceptions=_RECOVERABLE,
    )
    if isinstance(read, AttemptFailure) or read is None:
        return default_summary
    handle, question = read
    return _enriched(
        default_summary=default_summary,
        item_id=item_id,
        handle=handle,
        question=question,
    )


def _question(
    *,
    project_root: Path,
    item_id: str,
    runner: FabroRunner | None,
) -> tuple[NeedsHumanRunHandle, NeedsHumanQuestion] | None:
    handle = _run_handle(project_root=project_root, item_id=item_id)
    if handle is None:
        return None
    port = FabroPort(
        fabro_bin=resolve_fabro_bin(cwd=project_root),
        target=FabroTarget(server_url=handle.factory_server_url),
        runner=runner if runner is not None else ShellCommandRunner(),
        cwd=project_root,
    )
    inspected = port.inspect(run_id=handle.run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    question = needs_human_question_from_payload(payload=inspected.payload)
    if question is None:
        return None
    return (handle, question)


def _run_handle(*, project_root: Path, item_id: str) -> NeedsHumanRunHandle | None:
    """The run the ledger names for this item, on the factory it was sent to."""
    run_id = _stamped_run_id(project_root=project_root, item_id=item_id)
    if run_id is None:
        return None
    factory = resolve_fabro_factory(
        cwd=project_root,
        factory=_stamped_factory_name(project_root=project_root, item_id=item_id),
    )
    if factory.server is None:
        return None
    return NeedsHumanRunHandle(
        run_id=run_id,
        factory_name=factory.name,
        factory_server_url=factory.server,
    )


def _stamped_run_id(*, project_root: Path, item_id: str) -> str | None:
    """This item's newest run id, ledger metadata first and journal second.

    Both maps are keyed by RUN id — the direction that stays single-valued —
    so finding an ITEM's run means scanning them. The ledger holds at most one
    stamp per item (`dispatch_fabro_run_id` is overwritten by a re-dispatch),
    while the append-only journal can name several, so the journal leg takes
    the LAST match: a later record cannot describe an earlier run.
    """
    attribution = repo_run_attribution(repo=project_root)
    for run_id, owner in attribution.metadata_run_ids.items():
        if owner == item_id:
            return run_id
    newest: str | None = None
    for run_id, owner in attribution.journal_run_ids.items():
        if owner == item_id:
            newest = run_id
    return newest


def _stamped_factory_name(*, project_root: Path, item_id: str) -> str | None:
    read = attempt(
        action=lambda: dispatch_factory_for(
            path=store_config(repo=project_root), work_item_id=item_id
        ),
        exceptions=_RECOVERABLE,
    )
    return None if isinstance(read, AttemptFailure) else read


def _enriched(
    *,
    default_summary: str,
    item_id: str,
    handle: NeedsHumanRunHandle,
    question: NeedsHumanQuestion,
) -> str:
    return (
        f"{default_summary}; fabro run {handle.run_id} on factory "
        f"{handle.factory_name} ({handle.factory_server_url}) terminated at the "
        f"{NEEDS_HUMAN_NODE_ID} node and routed the decision to this valve. "
        f"Why: {question.reason if question.reason is not None else _NO_REASON}. "
        f"{_cause(question=question)}"
        f"It reported: {question.prompt if question.prompt is not None else _NO_PROMPT}. "
        f"{_preservation(question=question)} "
        f"Available actions: resolve-blocked:{item_id}:ready, "
        f"resolve-blocked:{item_id}:backlog, or leave the item blocked."
    )


def _cause(*, question: NeedsHumanQuestion) -> str:
    """The innermost cause, classified when it is a TRANSPORT fault.

    `reason` above it is the loop failure signature, which names the stage and
    the engine's generic `ACP turn failed` label — a label that covers a
    backgrounded tool call, a dead adapter, a timed-out turn and a provider
    ceiling alike. So the signature alone sends the human who comes to decide
    looking for a question nobody asked, which is exactly what this valve lane
    exists to stop. The classification is appended to the cause rather than
    replacing it: the family says what to do about it, the cause says what
    happened, and a build that rendered only the family would have dropped the
    one line a triager quotes.

    EMPTY when no cause is readable, which is the fail-soft posture the whole
    lane rides: the valve is what matters, and an unreadable failure block costs
    this sentence and nothing else.
    """
    if question.cause is None:
        return ""
    fault = transport_fault_from_cause(cause=question.cause)
    if fault is None:
        return f"Innermost cause: {question.cause}. "
    return f"Innermost cause: {question.cause}. {transport_fault_clause(fault=fault)}. "


def _preservation(*, question: NeedsHumanQuestion) -> str:
    """What a rework can start FROM — the fact a re-dispatch decision turns on."""
    if not question.tree_preserved:
        return "The run could NOT push its tree, so a rework starts from scratch."
    if question.preserved_ref is None:
        return "The run recorded no preserved ref, so a rework starts from scratch."
    return f"The run's tree is preserved at {question.preserved_ref}."

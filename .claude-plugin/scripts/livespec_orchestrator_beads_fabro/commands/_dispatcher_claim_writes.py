"""The Dispatcher's claim-changing ledger writes, under the claim-token cutover.

`SPECIFICATION/contracts.md` ("Claim tokens") names three Dispatcher writers of
a dispatch claim: admission, a terminal write, and a recovery effect. While the
committed key `dispatcher.claim_tokens` is `true`, each of them may change an
item's status, its `fabro` assignee or its run stamp only after winning the
item's current token, and must name the successor in that one write. This
module is where all of them decide which of the two ways to write. What a
guarded write sends lives in `_dispatcher_claim_guard`.

THE RUN STAMP IS A CLAIM-CHANGING WRITE TOO. The contract's definition is "any
write that changes an item's status, its `fabro` assignee or its run stamp".
The stamp the Dispatcher writes when it learns its run changes neither status
nor assignee, and it is still fenced, through `claim_stamp_write`.

THE UNGUARDED WRITER STAYS AT THE CALL SITE AND IS HANDED IN. While the key is
`false` or unset, the write is the caller's own store writer called with exactly
the arguments that caller passes today: the fields it always sends, plus each
optional field only when the caller set it. Nothing about an unguarded write is
decided here, which is what makes "no behaviour change before the cutover" a
property of this module's shape and not of each call site's discipline.

A REFUSAL IS A RETURN VALUE, NEVER AN EXCEPTION. Every function answers `None`
when its write landed and the outcome name when it did not, so a caller cannot
journal a transition that was refused. A refused writer has written nothing to
the item. Ledger faults still raise, exactly as the store writers raise them.

EVERY GUARDED WRITE STATES THE DECISION IT RESTS ON. Each function takes
`still_as_decided`, a predicate over the item record the guarded write is based
on (`_dispatcher_claim_guard` builds them). It is asked only on the guarded
path: an unguarded write is the caller's own, made as it always was.

AN UNREADABLE KEY REFUSES. The key decides whether a write is fenced at all, so
a value this host cannot read is not read as `false`: the write is withheld and
reported as `claim-tokens-unreadable`. An absent file or an absent key is an
answer (`false`), not an unreadable one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    Decided,
    guarded_blocked_write,
    guarded_hold,
    guarded_metadata_write,
    guarded_status_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CLAIM_TOKENS_UNREADABLE",
    "CLAIM_WRITE_REFUSED_STAGE",
    "LEDGER_WRITE_ERRORS",
    "WRITER_ADMISSION",
    "WRITER_RECOVERY",
    "WRITER_RUN_STAMP",
    "WRITER_TERMINAL",
    "claim_blocked_write",
    "claim_hold",
    "claim_stamp_write",
    "claim_status_write",
    "claim_tokens_setting",
    "settle_claim_write",
]

CLAIM_TOKENS_UNREADABLE = "claim-tokens-unreadable"
CLAIM_WRITE_REFUSED_STAGE = "claim-write-refused"

# The three Dispatcher writers the contract names. The name is recorded in the
# token's close reason, which is the only audit of who won a contested claim.
WRITER_ADMISSION = "dispatcher-admission"
WRITER_TERMINAL = "dispatcher-terminal"
WRITER_RECOVERY = "stranded-claim-recovery"
# The Dispatcher stamping the run it just learned onto its own claim. It is the
# admitting dispatch's write, made after admission and before any terminal.
WRITER_RUN_STAMP = "dispatcher-run-stamp"

# The ledger faults a claim write can raise. One tuple for every Dispatcher
# disposition that degrades a failed write to a journal record.
LEDGER_WRITE_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

_BLOCKED_STATUS = "blocked"


def claim_tokens_setting(*, repo: Path) -> bool | None:
    """The committed `dispatcher.claim_tokens`, or `None` when it cannot be read."""
    setting = resolve_claim_tokens(cwd=repo)
    if not is_successful(setting):
        return None
    return unsafe_perform_io(setting.unwrap())


def settle_claim_write(  # noqa: PLR0913 — kw-only; the two writers and the audit of whichever ran.
    *,
    repo: Path,
    item_id: str,
    writer: str,
    intent: str,
    unguarded: Callable[[], None],
    guarded: Callable[[], str | None],
    journal: JournalWriter | None = None,
) -> str | None:
    """Run the writer the committed key selects; `None` when its write landed.

    A refusal is journaled here, once, as `claim-write-refused` naming the
    writer, its intent and the outcome, so no caller can refuse silently. A
    caller with no journal of its own reports the returned outcome through
    whatever it does return.
    """
    enabled = claim_tokens_setting(repo=repo)
    if enabled is False:
        unguarded()
        return None
    refusal = guarded() if enabled else CLAIM_TOKENS_UNREADABLE
    if refusal is not None and journal is not None:
        journal.append(
            record={
                "stage": CLAIM_WRITE_REFUSED_STAGE,
                "work_item_id": item_id,
                "writer": writer,
                "intent": intent,
                "reason": refusal,
            }
        )
    return refusal


def claim_status_write(  # noqa: PLR0913 — kw-only; one status transition and who is making it.
    *,
    repo: Path,
    path: StoreConfig,
    intent: str,
    write: Callable[..., None],
    item_id: str,
    status: str,
    assignee: str | None = None,
    clear_assignee: bool = False,
    reconcile: Callable[..., None] | None = None,
    writer: str = WRITER_TERMINAL,
    journal: JournalWriter | None = None,
    still_as_decided: Decided | None = None,
) -> str | None:
    """Transition a claim's status, guarded once the cutover key is true.

    `write` is the caller's own status writer. `reconcile` is the post-write
    hook that writer runs for itself, when it runs one: a guarded write does
    not pass through `write`, so it is handed the hook to run after it lands.
    """

    def _guarded_then_reconciled() -> str | None:
        refusal = guarded_status_write(
            path=path,
            item_id=item_id,
            status=status,
            intent=intent,
            writer=writer,
            assignee=assignee,
            clear_assignee=clear_assignee,
            still_as_decided=still_as_decided,
        )
        if refusal is None and reconcile is not None:
            reconcile(path=path, item_id=item_id, status=status)
        return refusal

    optional = _set_fields(assignee=assignee, clear_assignee=clear_assignee)
    return settle_claim_write(
        repo=repo,
        item_id=item_id,
        writer=writer,
        intent=intent,
        journal=journal,
        unguarded=lambda: write(path=path, item_id=item_id, status=status, **optional),
        guarded=_guarded_then_reconciled,
    )


def claim_blocked_write(  # noqa: PLR0913 — kw-only; one blocked rest and who is making it.
    *,
    repo: Path,
    path: StoreConfig,
    intent: str,
    write: Callable[..., None],
    item_id: str,
    blocked_reason: str,
    admission_policy: str | None = None,
    writer: str = WRITER_TERMINAL,
    journal: JournalWriter | None = None,
    still_as_decided: Decided | None = None,
) -> str | None:
    """Rest a claim at `blocked` with its reason, guarded once the key is true."""
    optional = _set_fields(admission_policy=admission_policy)
    return settle_claim_write(
        repo=repo,
        item_id=item_id,
        writer=writer,
        intent=intent,
        journal=journal,
        unguarded=lambda: write(
            path=path,
            item_id=item_id,
            status=_BLOCKED_STATUS,
            blocked_reason=blocked_reason,
            **optional,
        ),
        guarded=lambda: guarded_blocked_write(
            path=path,
            item_id=item_id,
            blocked_reason=blocked_reason,
            intent=intent,
            writer=writer,
            admission_policy=admission_policy,
            still_as_decided=still_as_decided,
        ),
    )


def claim_hold(  # noqa: PLR0913 — kw-only; one hold, who makes it and what it decided on.
    *,
    repo: Path,
    path: StoreConfig,
    intent: str,
    item_id: str,
    writer: str = WRITER_TERMINAL,
    journal: JournalWriter | None = None,
    still_as_decided: Decided | None = None,
) -> str | None:
    """Win the item's token ahead of a close; before the cutover, write nothing."""
    return settle_claim_write(
        repo=repo,
        item_id=item_id,
        writer=writer,
        intent=intent,
        journal=journal,
        unguarded=lambda: None,
        guarded=lambda: guarded_hold(
            path=path,
            item_id=item_id,
            intent=intent,
            writer=writer,
            still_as_decided=still_as_decided,
        ),
    )


def claim_stamp_write(  # noqa: PLR0913 — kw-only; one stamp, its two renderings and its audit.
    *,
    repo: Path,
    path: StoreConfig,
    intent: str,
    write: Callable[[], None],
    item_id: str,
    metadata: dict[str, Any],
    journal: JournalWriter | None = None,
    still_as_decided: Decided | None = None,
) -> str | None:
    """Stamp a run onto its claim, guarded once the cutover key is true.

    `write` is the caller's own stamp write, already bound to its arguments.
    `metadata` is the same stamp as the top-level keys it occupies, which is
    what the guarded write sends: an overlay, never the whole object.
    """
    return settle_claim_write(
        repo=repo,
        item_id=item_id,
        writer=WRITER_RUN_STAMP,
        intent=intent,
        journal=journal,
        unguarded=write,
        guarded=lambda: guarded_metadata_write(
            path=path,
            item_id=item_id,
            intent=intent,
            writer=WRITER_RUN_STAMP,
            metadata=metadata,
            still_as_decided=still_as_decided,
        ),
    )


def _set_fields(**fields: object) -> dict[str, object]:
    """The optional fields a caller actually set, as the store writers take them."""
    return {
        name: value for name, value in fields.items() if value is not None and value is not False
    }

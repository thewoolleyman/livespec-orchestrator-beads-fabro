"""What a stranded-claim pass LEAVES: its journal rows, comments and report.

PURE. Every record this subsection writes is rendered here and written
elsewhere, so each claim a record makes is assertable without a ledger — and
so the two durable records of one recovery, the journal row and the ledger
comment, are rendered from one set of facts rather than from two readings that
could disagree about the same release.

THE COMMENT IS THE RECORD THAT OUTLIVES THE RUN, which is why it names the
factory and the run id in full rather than referring to them. The dispatch
journal lives under the `tmp/` tree of whichever checkout happened to run the
pass, so it is gone the moment that checkout is pruned; the ledger comment is
the only account an operator reading the item months later can still find. And
`bd comments` offers neither edit nor delete, so a comment is written once and
forever: it carries no template opener, no shell quoting and no credential,
because a comment carrying an opener costs the item its dispatchability
permanently.

EACH ROUTE HAS ITS OWN STAGE, never a field on a shared row. A reader asking
"was this item released" must not match the row that says it deliberately was
NOT — the same discipline `_dispatcher_stall_disposition` keeps between its
release, its needs-human rest and its held row, and for the same reason: the
three are opposite dispositions.

THE HOLD ROW IS WRITTEN FOR EVERY HELD CLAIM, including the ones held because
something could not be measured. A hold nobody can see is indistinguishable
from a claim nobody surveyed, which is the exact absence this whole subsection
exists to end: before it, `reconcile-runs` returned `held: []` for an item
stranded `active` with its run long gone.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "REASON_RUN_ABSENT",
    "REASON_RUN_ABSENT_REPEATED",
    "RELEASE_COMMENT_MARKER",
    "REPEATED_COMMENT_MARKER",
    "STRANDED_CLAIM_HOLD_STAGE",
    "STRANDED_CLAIM_RELEASE_STAGE",
    "STRANDED_CLAIM_REPEATED_STAGE",
    "STRANDED_CLAIM_TERMINAL_STAGE",
    "HeldClaim",
    "RecoveredClaim",
    "hold_journal_record",
    "recovery_journal_record",
    "release_comment_body",
    "repeated_comment_body",
]

# The journal stage the absent-run release appends. The contract names this
# record by name — "one `stranded-claim-release` record naming the item, the
# run id, the factory and the reason `run-absent`" — so the literal is part of
# the ratified surface rather than an implementation detail.
STRANDED_CLAIM_RELEASE_STAGE = "stranded-claim-release"

# The second consecutive absent run's rest. Its OWN stage, because it is the
# bound on the release rather than an instance of it: a reading that counted it
# as a release would make the next absent run the third in a sequence the
# clause stops at two.
STRANDED_CLAIM_REPEATED_STAGE = "stranded-claim-run-absent-repeated"

# The terminal-run completion's announcement. The DISPOSITIONS it applies write
# their own records — a provider-limit release writes `provider-limit-release`,
# a first stall writes `stall-cancel-release` — so this row says only that
# reconciliation finished what a dead dispatcher left undone, and never
# restates a disposition it did not decide.
STRANDED_CLAIM_TERMINAL_STAGE = "stranded-claim-terminal-completion"

# Every held claim's row, carrying the reason of its first failing condition.
STRANDED_CLAIM_HOLD_STAGE = "stranded-claim-hold"

REASON_RUN_ABSENT = "run-absent"
REASON_RUN_ABSENT_REPEATED = "run-absent-repeated"

# The comment markers. Stable first lines, because the replay reads them back
# to decide whether its own comment already landed: an effect looked for by
# prose would be missed by a wording change and written twice.
RELEASE_COMMENT_MARKER = "livespec-stranded-claim-release"
REPEATED_COMMENT_MARKER = "livespec-stranded-claim-run-absent-repeated"


@dataclass(frozen=True, kw_only=True)
class HeldClaim:
    """One surveyed claim this pass left exactly as it found it.

    `remedy` is populated only where the clause requires the entry to name one
    — the `attribution-pending` hold, which nothing automatic can ever clear —
    and is `None` elsewhere rather than carrying generic advice: a remedy on
    every row would make the one row that genuinely needs reading look like
    boilerplate.
    """

    work_item_id: str
    run_id: str | None
    factory_name: str | None
    factory_server_url: str | None
    dispatching_host: str | None
    hold_reason: str
    remedy: str | None


@dataclass(frozen=True, kw_only=True)
class RecoveredClaim:
    """One claim this pass released, rested, or completed.

    `effects_written` names the effects THIS pass performed, which is how a
    replay is distinguishable from a first recovery: a convergent second pass
    reports the same route with an empty effect list rather than reporting that
    nothing happened.
    """

    work_item_id: str
    run_id: str
    factory_name: str
    factory_server_url: str | None
    reason: str
    route: str
    status: str
    effects_written: tuple[str, ...]


def recovery_journal_record(*, stage: str, recovered: RecoveredClaim) -> dict[str, object]:
    """The journal row one recovery leaves, whichever route it took."""
    return {
        "stage": stage,
        "work_item_id": recovered.work_item_id,
        "run_id": recovered.run_id,
        "factory": recovered.factory_name,
        "factory_server": recovered.factory_server_url,
        "reason": recovered.reason,
        "status": recovered.status,
        "effects_written": list(recovered.effects_written),
    }


def hold_journal_record(*, held: HeldClaim) -> dict[str, object]:
    """The journal row one held claim leaves."""
    return {
        "stage": STRANDED_CLAIM_HOLD_STAGE,
        "work_item_id": held.work_item_id,
        "run_id": held.run_id,
        "factory": held.factory_name,
        "factory_server": held.factory_server_url,
        "dispatching_host": held.dispatching_host,
        "reason": held.hold_reason,
        "remedy": held.remedy,
    }


def release_comment_body(
    *,
    work_item_id: str,
    run_id: str,
    factory_name: str,
    factory_server_url: str | None,
) -> str:
    """The durable account of one absent-run release."""
    server = _server_text(url=factory_server_url)
    return "\n".join(
        (
            RELEASE_COMMENT_MARKER,
            "",
            f"Work-item {work_item_id} returned to `ready`, `fabro` assignee cleared.",
            f"Reason: {REASON_RUN_ABSENT}.",
            f"Run {run_id} was reported ABSENT by factory {factory_name} ({server}),",
            "asked by that factory's own declared server target.",
            "No live dispatch owned the item on its stamped host; the forge reported no",
            "merged pull request for it; and its preceding dispatch did not end in an",
            "absent-run release.",
            "The dispatch claim therefore outlived its run, and reconciliation released",
            "it so the item can be admitted again.",
        )
    )


def repeated_comment_body(
    *,
    work_item_id: str,
    run_id: str,
    predecessor_run_id: str | None,
    factory_name: str,
    factory_server_url: str | None,
) -> str:
    """The durable account of a SECOND consecutive absent run.

    It names both runs, because that pair IS the finding: one vanished run is
    an incident and two in a row is a pattern no further automatic release may
    be spent on, and an operator cannot see the pattern from the newer run
    alone.
    """
    server = _server_text(url=factory_server_url)
    predecessor = _run_text(run_id=predecessor_run_id)
    return "\n".join(
        (
            REPEATED_COMMENT_MARKER,
            "",
            f"Work-item {work_item_id} rests at `blocked` / `needs-human`.",
            f"Reason: {REASON_RUN_ABSENT_REPEATED}.",
            f"Run {run_id} was reported ABSENT by factory {factory_name} ({server}).",
            f"Its preceding dispatch, run {predecessor}, already ended in an",
            "absent-run release.",
            "Two consecutive runs vanishing with no terminal outcome is not something a",
            "further automatic release can fix, so the decision rests with a human.",
            "Release it with `drive --action 'resolve-blocked:<work-item-id>:ready'`",
            "once the cause is understood.",
        )
    )


def _server_text(*, url: str | None) -> str:
    """The server a record names, or a statement that the stamp carried none."""
    return url if url is not None else "no server recorded on the claim stamp"


def _run_text(*, run_id: str | None) -> str:
    return run_id if run_id is not None else "(run id not recorded)"

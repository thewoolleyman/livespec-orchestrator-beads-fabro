"""Writing the retry-discipline record a dispatch's own ending earns.

The WRITER half of the retry guard: every record the NEXT dispatch's guard reads
is appended here, so the format has one writer and one reader rather than a
convention each venue remembers.

WHICH ENDINGS EARN A RECORD, stated here because the filter is the whole of the
capacity-deferral guarantee. A `failed` outcome earns a refusal signature — that
status covers both a run that failed and an item the admission valve HELD, which
is why `admission-held` needs no arm of its own. Everything else earns NOTHING,
and the ending that matters most there is `capacity-deferred`: the
work-in-progress cap defers an item nothing is wrong with, so a signature there
would demand a named change for the ordinary next act.

THE EXECUTING BUILD IS STAMPED HERE, and `executing_build` is public so the
guard can read the same identity rather than derive a second one. Two
derivations is how the writer and the reader come to disagree about which build
is running, and the disagreement would be invisible: each derivation returns a
perfectly plausible root. The INSTALLED root is the right one — the comparison
this feeds asks which INSTALLATION produced a decision, while the executing
payload root answers "where did this process load its code from", which on a
retained payload is a different tree.

EVERY WRITE IS FAIL-OPEN AND JOURNALED. This runs after the verdict is already
computed and immutable, so a ledger error here cannot change what the dispatch
reported, and raising would turn a bookkeeping failure into a traceback out of
the post-verdict tail. The failure is journaled under its OWN stage, because a
signature that was never written is a guard that will not arm and nothing else
would say so.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    DispatchOutcome,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    plugin_root,
    store_config,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_retry_records import (
    REFUSAL_SIGNATURE_KIND,
    UNCLASSIFIED_ERROR_CLASS,
    UNKNOWN_BUILD_VERSION,
    ExecutingBuild,
    RetryRecord,
    render_retry_record,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    read_build_version,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "RETRY_SIGNATURE_STAGE",
    "RETRY_WRITE_FAILED_STAGE",
    "executing_build",
    "outcome_error_class",
    "record_retry_outcomes",
]

# The journal stage a written record is reported under, and the one a failed
# write is reported under. Distinct, because a reader counting arming events
# must not be handed the writes that never landed.
RETRY_SIGNATURE_STAGE = "dispatcher-retry-discipline-signature"
RETRY_WRITE_FAILED_STAGE = "dispatcher-retry-discipline-write-failed"

_FAILED_STATUS = "failed"
_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


def executing_build() -> ExecutingBuild:
    """The build this process is executing, as a record names it."""
    root = plugin_root()
    version = read_build_version(install_path=root)
    return ExecutingBuild(
        version=UNKNOWN_BUILD_VERSION if version is None else version,
        plugin_root=str(root),
    )


def outcome_error_class(*, outcome: DispatchOutcome) -> str:
    """The error class one failed outcome is recorded under.

    The ENGINE's own category first, because it is the classification the factory
    assigned; then the degraded-step identifier, which is the closed vocabulary
    the post-merge steps report under. An outcome carrying neither is named
    `unclassified` rather than given an invented class: the repeat test compares
    two stated classes, and a fabricated one would make two unrelated failures
    compare equal under a name that claims to mean something.
    """
    for candidate in (outcome.fabro_failure_category, outcome.step):
        if candidate is not None and candidate != "":
            return candidate
    return UNCLASSIFIED_ERROR_CLASS


def record_retry_outcomes(
    *,
    repo: Path,
    outcomes: Sequence[DispatchOutcome],
    journal: JournalWriter,
    build: ExecutingBuild | None = None,
    now: str | None = None,
) -> None:
    """Write each outcome's retry-discipline record, when its ending earns one.

    The build and the instant are resolved ONCE for the whole wave rather than
    per outcome, so every record one dispatch pass writes names the same build
    and the same instant — two resolutions would let one pass report two.
    """
    resolved_build = executing_build() if build is None else build
    recorded_at = utc_now_iso() if now is None else now
    for outcome in outcomes:
        record = _record_for_outcome(outcome=outcome, build=resolved_build, recorded_at=recorded_at)
        if record is None:
            continue
        _append_retry_record(
            repo=repo,
            work_item_id=outcome.work_item_id,
            record=record,
            journal=journal,
            journal_stage=RETRY_SIGNATURE_STAGE,
        )


def _record_for_outcome(
    *, outcome: DispatchOutcome, build: ExecutingBuild, recorded_at: str
) -> RetryRecord | None:
    """The record one terminal outcome earns, or `None` when it earns none."""
    if outcome.status != _FAILED_STATUS:
        return None
    return RetryRecord(
        kind=REFUSAL_SIGNATURE_KIND,
        stage=outcome.stage,
        error_class=outcome_error_class(outcome=outcome),
        build=build,
        recorded_at=recorded_at,
    )


def _append_retry_record(
    *,
    repo: Path,
    work_item_id: str,
    record: RetryRecord,
    journal: JournalWriter,
    journal_stage: str,
) -> None:
    """Append one record to the item's ledger timeline and journal the write."""
    written = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)).add_comment(
            issue_id=work_item_id,
            body=render_retry_record(record=record),
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(written, AttemptFailure):
        journal.append(
            record={
                "stage": RETRY_WRITE_FAILED_STAGE,
                "work_item_id": work_item_id,
                "kind": record.kind,
                "reason": type(written.error).__name__,
            }
        )
        return
    journal.append(
        record={
            "stage": journal_stage,
            "work_item_id": work_item_id,
            "kind": record.kind,
            "refusing_stage": record.stage,
            "error_class": record.error_class,
            "build_version": record.build.version,
            "plugin_root": record.build.plugin_root,
            "recorded_at": record.recorded_at,
            "reason": record.reason,
        }
    )

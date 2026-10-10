"""Adopted assertion-count admission gate."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from returns.io import IOFailure, IOResult, IOSuccess
from returns.pipeline import is_successful
from returns.result import Failure, Result, Success
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    route_factory_size_decomposition,
    size_justification_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_assertion_count import (
    assertion_count_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_admission import (
    FACTORY_SIZE_ADMISSION_STAGE,
    record_factory_size_admission_decision,
    size_justified_at_admission,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
    read_dispatcher_config_value,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "FACTORY_SIZE_ADMISSION_STAGE",
    "FactorySizeDecision",
    "apply_factory_size_dispatch_entry",
    "consensus_groom_cut_size_refusal",
    "factory_size_configuration_refusal",
    "factory_size_decision",
    "record_factory_size_admission_decision",
    "resolve_adopted_assertion_count_ceiling",
    "resolved_stored_factory_size_decision",
    "size_justified_at_admission",
    "stored_factory_size_decision",
]

ADOPTED_ASSERTION_COUNT_CEILING = "adopted_assertion_count_ceiling"


@dataclass(frozen=True, kw_only=True)
class FactorySizeDecision:
    """One item's result at the conditional factory-size gate."""

    disposition: str
    adopted_ceiling: int | None
    assertion_count: int
    reason: str | None
    size_justified: bool


def consensus_groom_cut_size_refusal(
    *, cwd: Path, approving_invoker: str, items: tuple[WorkItem, ...]
) -> str | None:
    """Enforce the consensus tier's exception-free first-cut size rail."""
    if approving_invoker.partition(":")[0] != "consensus":
        return None
    resolution = resolve_adopted_assertion_count_ceiling(cwd=cwd)
    adopted_ceiling = unsafe_perform_io(resolution.unwrap())
    if adopted_ceiling is None:
        return (
            "consensus approval requires an adopted assertion-count ceiling; "
            "the draft must rest for a human"
        )
    for item in items:
        observed = assertion_count_for(item=item).count
        if observed > adopted_ceiling:
            return (
                "consensus approval requires every first-cut slice at or below "
                f"adopted assertion-count ceiling {adopted_ceiling}; slice {item.title!r} "
                f"has sanctioned-parser assertion count {observed}; "
                "size_justification cannot waive the consensus ceiling"
            )
    return None


def factory_size_decision(
    *, item: WorkItem, adopted_ceiling: int | None, raw_justification: object
) -> FactorySizeDecision:
    """Apply the adopted ceiling to the sanctioned effective-criteria count."""
    observed = assertion_count_for(item=item).count
    if adopted_ceiling is not None and observed > adopted_ceiling:
        if _valid_size_justification(raw=raw_justification):
            return FactorySizeDecision(
                disposition="proceed",
                adopted_ceiling=adopted_ceiling,
                assertion_count=observed,
                reason=None,
                size_justified=True,
            )
        return FactorySizeDecision(
            disposition="decompose",
            adopted_ceiling=adopted_ceiling,
            assertion_count=observed,
            reason=(
                f"adopted assertion-count ceiling {adopted_ceiling}; "
                f"sanctioned-parser assertion count {observed}; "
                "missing or invalid size_justification; route to backlog for decomposition"
            ),
            size_justified=False,
        )
    return FactorySizeDecision(
        disposition="proceed",
        adopted_ceiling=adopted_ceiling,
        assertion_count=observed,
        reason=None,
        size_justified=False,
    )


def stored_factory_size_decision(
    *, path: StoreConfig, item: WorkItem, adopted_ceiling: int | None
) -> FactorySizeDecision:
    """Apply the gate to the item's raw, ledger-held justification metadata."""
    return factory_size_decision(
        item=item,
        adopted_ceiling=adopted_ceiling,
        raw_justification=size_justification_for(path=path, work_item_id=item.id),
    )


def resolve_adopted_assertion_count_ceiling(
    *, cwd: Path
) -> IOResult[int | None, PolicySettingUnreadable]:
    """Read the committed-only ceiling, where absence means no adoption."""
    return read_dispatcher_config_value(cwd=cwd, key=ADOPTED_ASSERTION_COUNT_CEILING).bind_result(
        lambda value: _adopted_ceiling_value(value=value)
    )


def resolved_stored_factory_size_decision(
    *, cwd: Path, path_factory: Callable[[], StoreConfig], item: WorkItem
) -> IOResult[FactorySizeDecision, PolicySettingUnreadable]:
    """Resolve committed configuration before reading the item's exception."""
    return resolve_adopted_assertion_count_ceiling(cwd=cwd).map(
        lambda ceiling: (
            factory_size_decision(
                item=item,
                adopted_ceiling=None,
                raw_justification=None,
            )
            if ceiling is None
            else stored_factory_size_decision(
                path=path_factory(),
                item=item,
                adopted_ceiling=ceiling,
            )
        )
    )


def apply_factory_size_dispatch_entry(
    *,
    cwd: Path,
    path_factory: Callable[[], StoreConfig],
    items: Sequence[WorkItem],
    journal: JournalFile,
) -> IOResult[tuple[DispatchOutcome, ...], PolicySettingUnreadable]:
    """Apply the size gate before a public dispatch path selects or claims.

    Configuration is resolved once before any lifecycle mutation.  A valid
    exception is journaled at this admission moment so terminal telemetry can
    retain the decision even if committed configuration or ledger metadata
    changes while the factory run is in flight.
    """
    resolved = resolve_adopted_assertion_count_ceiling(cwd=cwd)
    if not is_successful(resolved):
        return IOFailure(unsafe_perform_io(resolved.failure()))
    ceiling = unsafe_perform_io(resolved.unwrap())
    path = path_factory() if ceiling is not None else None
    refused: list[DispatchOutcome] = []
    audit_started = _factory_size_audit_started(journal=journal)
    for item in items:
        decision = (
            factory_size_decision(
                item=item,
                adopted_ceiling=None,
                raw_justification=None,
            )
            if ceiling is None
            else stored_factory_size_decision(
                path=cast("StoreConfig", path),
                item=item,
                adopted_ceiling=ceiling,
            )
        )
        if decision.disposition == "proceed" and (decision.size_justified or audit_started):
            record_factory_size_admission_decision(
                journal=journal,
                item=item,
                decision=decision,
            )
            audit_started = True
        if decision.disposition == "decompose":
            reason = cast("str", decision.reason)
            route_factory_size_decomposition(
                path=cast("StoreConfig", path),
                work_item_id=item.id,
                reason=reason,
            )
            refused.append(
                failed_dispatch_outcome(
                    journal=journal,
                    work_item_id=item.id,
                    stage="size-decomposition",
                    detail=reason,
                )
            )
    return IOSuccess(tuple(refused))


def _factory_size_audit_started(*, journal: JournalWriter) -> bool:
    """Whether this durable journal already carries factory-size evidence."""
    if not isinstance(journal, JournalFile):
        return False
    return any(
        record.get("stage") == FACTORY_SIZE_ADMISSION_STAGE
        for record in read_journal_records(journal_path=journal.path)
    )


def factory_size_configuration_refusal(*, cwd: Path) -> str | None:
    """Return configured-ceiling refusal detail, or none when readable."""
    ceiling = resolve_adopted_assertion_count_ceiling(cwd=cwd)
    if is_successful(ceiling):
        return None
    return unsafe_perform_io(ceiling.failure()).detail


def _adopted_ceiling_value(*, value: object) -> Result[int | None, PolicySettingUnreadable]:
    if value is None:
        return Success(None)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return Success(value)
    return Failure(
        PolicySettingUnreadable(
            setting=ADOPTED_ASSERTION_COUNT_CEILING,
            detail=(
                "dispatcher.adopted_assertion_count_ceiling must be a positive integer; "
                f"got {value!r}"
            ),
        )
    )


def _valid_size_justification(*, raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    values = cast("dict[object, object]", raw)
    if set(values) != {"rationale", "author", "at"}:
        return False
    for key in ("rationale", "author", "at"):
        if not _non_empty_string(value=values[key]):
            return False
    at = cast("str", values["at"]).strip()
    normalized = at.removesuffix("Z") + ("+00:00" if at.endswith("Z") else "")
    return not isinstance(parse_iso_datetime(text=normalized), IsoDatetimeParseFailure)


def _non_empty_string(*, value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())

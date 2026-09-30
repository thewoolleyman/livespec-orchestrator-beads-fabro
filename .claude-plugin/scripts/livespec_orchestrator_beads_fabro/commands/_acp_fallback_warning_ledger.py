"""The append-only ledger of model-fallback warnings, and how one retires.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Later run failure does not erase it, and it never refuses or
disposes work. A primary node attempt clears only a warning from the same
primary-generation fingerprint when its attempt began after the warning
and completed successfully, regardless of the overall run's later
outcome. Older concurrent success, unrelated success, probes, and
unexecuted preflight selection cannot clear it. Primary replacement
retires the prior warning as append-only `superseded`."

THE CLEARANCE PREDICATE IS A CONJUNCTION OF FOUR CLAIMS, and each one
exists to refuse a different near-miss the clause enumerates:

- the attempt must have EXECUTED, which refuses a credential probe and an
  unexecuted preflight selection -- neither ran an adapter, so neither is
  evidence about the primary at all;
- it must have SUCCEEDED, and its success is read on its own terms, so a
  run that later failed in another node still clears;
- it must carry the SAME `primary_generation`, which refuses an unrelated
  candidate's success and a success by a primary that has since been
  replaced;
- it must have STARTED after the warning, which refuses an older
  concurrent attempt that was already running when the fallback fired.

WARNINGS ARE NEVER ERASED, ONLY OUT-VOTED BY A LATER APPENDED LINE, so
the journal still answers "what ran, and what retired it" after any
retirement. That is the same discipline the hold ledger keeps, and the
fold is deliberately written the same way -- forward, first write wins on
the id -- so re-projecting a run's events appends nothing and moves
nothing.

THE SUPERSEDE PASS IS DRIVEN BY THE REPOSITORY'S CURRENT PRIMARIES, not
by the arrival of a new event. A replaced primary may never produce
another failover event, and a warning about a primary nobody runs any
more is a row an operator cannot act on; comparing each live warning's
generation against the node's CURRENT one is what retires it. A
fallback-only edit leaves that generation untouched, so the same pass
leaves the warning standing -- the discrimination falls out of which
digest is compared rather than out of a rule about edits.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpEventScan
from livespec_orchestrator_beads_fabro.commands._acp_fallback_warning_records import (
    MODEL_FALLBACK_CLEARED_STAGE,
    MODEL_FALLBACK_STAGE,
    MODEL_FALLBACK_SUPERSEDED_STAGE,
    ModelFallbackWarning,
    parse_model_fallback_warning,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import parse_hold_instant
from livespec_orchestrator_beads_fabro.commands._acp_journal_records import journal_records

__all__: list[str] = [
    "AcpPrimaryAttempt",
    "ModelFallbackWarningLedger",
    "ingest_model_fallback_warning",
    "newest_warning_per_node",
    "primary_attempt_clears",
    "primary_attempts_from_scan",
    "primary_replacement_records",
    "primary_success_clearance_records",
    "read_model_fallback_warnings",
]

_RETIREMENT_STAGES = frozenset({MODEL_FALLBACK_CLEARED_STAGE, MODEL_FALLBACK_SUPERSEDED_STAGE})


class _Journal(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class AcpPrimaryAttempt:
    """One node attempt by candidate ZERO, as the clearance rule reads it.

    `executed` is separate from `succeeded` on purpose. A credential probe
    and a preflight selection both have "no failure" to report, so a type
    carrying only `succeeded` would let either of them answer True and
    clear a warning the contract says they cannot touch.
    """

    node: str
    primary_generation: str
    started_at: str
    executed: bool
    succeeded: bool


@dataclass(frozen=True, kw_only=True)
class ModelFallbackWarningLedger:
    """Every live model-fallback warning, plus what could not be read."""

    warnings: tuple[ModelFallbackWarning, ...]
    unobservable: tuple[Mapping[str, object], ...]
    warning_ids: frozenset[str]


def read_model_fallback_warnings(*, journal_path: Path | None) -> ModelFallbackWarningLedger:
    """Fold the journal into the warnings that still stand.

    There is no clock parameter and no expiry: a model-fallback warning
    has no bounded lifetime, because the contract retires it only on
    demonstrated primary success or on primary replacement. Handing this
    a `now` would invite exactly the silent third retirement route the
    hold ledger's bounded expiry is careful to be the ONLY instance of.
    """
    observed: dict[str, ModelFallbackWarning] = {}
    unobservable: list[Mapping[str, object]] = []
    seen: set[str] = set()
    retired: set[str] = set()
    for record in journal_records(journal_path=journal_path):
        stage = record.get("stage")
        if stage in _RETIREMENT_STAGES:
            retired.update(_retired_ids(record=record))
            continue
        if stage != MODEL_FALLBACK_STAGE:
            continue
        parsed = parse_model_fallback_warning(record=record)
        if isinstance(parsed, str):
            unobservable.append(record)
            continue
        seen.add(parsed.warning_id)
        _ = observed.setdefault(parsed.warning_id, parsed)
    live = tuple(warning for key, warning in observed.items() if key not in retired)
    return ModelFallbackWarningLedger(
        warnings=live, unobservable=tuple(unobservable), warning_ids=frozenset(seen)
    )


def ingest_model_fallback_warning(
    *, record: dict[str, object], ledger: ModelFallbackWarningLedger, journal: _Journal
) -> bool:
    """Append one warning unless this exact one is already recorded.

    Dedupe reads every id the journal has EVER carried rather than the
    live set, for the hold ledger's reason: checking live warnings would
    let the same event re-append a warning a later primary success had
    already cleared.
    """
    identifier = record.get("warning_id")
    if isinstance(identifier, str) and identifier in ledger.warning_ids:
        return False
    journal.append(record=record)
    return True


def newest_warning_per_node(
    *, ledger: ModelFallbackWarningLedger
) -> Mapping[str, ModelFallbackWarning]:
    """The newest live warning for each node, which supplies its fact summary.

    "The newest unresolved observation supplies the deterministic
    summary." Newest is decided by occurrence time with the warning id as
    the tiebreak, so two warnings stamped at the same second still order
    identically on every machine and the rendered fact stays byte-stable.
    """
    newest: dict[str, ModelFallbackWarning] = {}
    for warning in sorted(ledger.warnings, key=lambda entry: (entry.occurred_at, entry.warning_id)):
        newest[warning.node] = warning
    return newest


def primary_attempts_from_scan(
    *, scan: AcpEventScan, succeeded_nodes: frozenset[str]
) -> tuple[AcpPrimaryAttempt, ...]:
    """The primary attempts one run's event stream evidences, and their verdict.

    Two conditions must BOTH hold before an attempt is reported
    successful, and each refuses a different way of clearing a warning on
    no evidence:

    - the node visit must carry no transition or exhaustion of its own.
      A primary that fell over is the reason the warning exists; reading
      its start alone would clear the warning the same run raised.
    - the node must appear in `succeeded_nodes`, which the caller proves
      from the dispatch's own terminal outcome. A run whose outcome
      cannot establish a node's success contributes an EXECUTED attempt
      that did not succeed, so the warning stands.

    A `candidate_index` above zero is reported too, as an executed
    attempt that is not the primary: `primary_attempt_clears` refuses it
    on the generation-and-node test, which is the contract's "unrelated
    success ... cannot clear it" arriving as data rather than as a
    special case.
    """
    failed_visits = {(event.node, event.node_visit) for event in scan.events}
    return tuple(
        AcpPrimaryAttempt(
            node=start.node,
            primary_generation=start.primary_generation,
            started_at=start.occurred_at,
            executed=True,
            succeeded=(
                start.primary
                and (start.node, start.node_visit) not in failed_visits
                and start.node in succeeded_nodes
            ),
        )
        for start in scan.starts
    )


def primary_attempt_clears(*, warning: ModelFallbackWarning, attempt: AcpPrimaryAttempt) -> bool:
    """Whether this primary attempt retires that one warning."""
    if not attempt.executed or not attempt.succeeded:
        return False
    if attempt.node != warning.node:
        return False
    if attempt.primary_generation != warning.primary_generation:
        return False
    return _starts_after(warning=warning, started_at=attempt.started_at)


def primary_success_clearance_records(
    *, ledger: ModelFallbackWarningLedger, attempt: AcpPrimaryAttempt
) -> tuple[dict[str, object], ...]:
    """One appendable clearance per live warning this primary success retires."""
    return tuple(
        {
            "stage": MODEL_FALLBACK_CLEARED_STAGE,
            "node": warning.node,
            "warning_ids": [warning.warning_id],
            "primary_generation": warning.primary_generation,
            "cleared_by_attempt_started_at": attempt.started_at,
        }
        for warning in ledger.warnings
        if primary_attempt_clears(warning=warning, attempt=attempt)
    )


def primary_replacement_records(
    *, ledger: ModelFallbackWarningLedger, primary_generations: Mapping[str, str]
) -> tuple[dict[str, object], ...]:
    """One appendable `superseded` per warning whose primary has been replaced.

    A node ABSENT from `primary_generations` is left alone rather than
    treated as replaced: the mapping carries only the nodes whose chain
    currently resolves, so an unreadable configuration would otherwise
    retire every warning in the repository at once -- the loudest
    possible way to lose the evidence a person still needs.
    """
    return tuple(
        {
            "stage": MODEL_FALLBACK_SUPERSEDED_STAGE,
            "node": warning.node,
            "warning_ids": [warning.warning_id],
            "superseded_primary_generation": warning.primary_generation,
            "current_primary_generation": primary_generations[warning.node],
        }
        for warning in ledger.warnings
        if warning.node in primary_generations
        and primary_generations[warning.node] != warning.primary_generation
    )


def _starts_after(*, warning: ModelFallbackWarning, started_at: str) -> bool:
    """Whether the attempt began strictly after this warning was observed.

    An unreadable instant on either side reports False, keeping the
    warning: retirement is the destructive direction, and a clock nobody
    can read must not authorise one.
    """
    occurred = parse_hold_instant(text=warning.occurred_at)
    started = parse_hold_instant(text=started_at)
    if occurred is None or started is None:
        return False
    return started > occurred


def _retired_ids(*, record: Mapping[str, Any]) -> frozenset[str]:
    """The warning ids one clearance or supersede line names."""
    raw = record.get("warning_ids")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(item for item in cast("list[object]", raw) if isinstance(item, str))

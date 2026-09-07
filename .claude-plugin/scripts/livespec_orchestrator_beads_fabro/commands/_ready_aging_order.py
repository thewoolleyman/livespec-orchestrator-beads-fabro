"""The orchestrator-side ready-age input the canonical ready ordering needs.

`livespec_runtime.work_items.lifecycle.ready_sort_key` breaks equal-`rank` ties
by ready-age past `dispatcher.ready_aging_threshold_hours`
(the ranking-authority clause of `SPECIFICATION/contracts.md`), but the
runtime deliberately ships no
way to READ that age: the durable, clone-independent instant of an item's
latest transition into `ready` lives in the beads tenant, and reading it from
the runtime would be the same `runtime -> beads` back-edge that
`sibling_status_lookup` exists to avoid. This module is the orchestrator-side
injection for the age half.

`ready_aging_order` composes BOTH inputs a ready-ordering call site hands the
factory — the lookup and the bound — from ONE project root, so `next` and the
Dispatcher cannot resolve different orderings for the same tenant. The instants
come from `read_ready_dwell_instants`, which is the SAME durable `ready_since`
source the `hygiene:ready-aging:<repo>` attention fact reads; no machine-local
dispatch journal is consulted anywhere here, per the ratified clause.

The tenant read is LAZY and MEMOIZED, exactly as `make_sibling_status_lookup`
is: the factory invokes the lookup once per item, so a pass over an empty ready
set reads nothing and a pass over many items reads the tenant once. It is also
FAIL-SOFT, and that is the safe direction — an unreadable tenant or an
unparseable instant yields `None`, which the runtime reads as an unknowable
ready instant and orders by the `id` tiebreak with NO age advantage. Failing the
other way would let a substrate hiccup reorder the dispatch queue.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_READY_AGING_THRESHOLD_HOURS,
    resolve_ready_aging_threshold_hours,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    IsoDatetimeParseFailure,
    attempt,
    parse_iso_datetime,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.store import read_ready_dwell_instants

__all__: list[str] = [
    "ReadyAgingOrder",
    "ready_aging_order",
    "unaged_ready_order",
]

# The EXPECTED-error surface one dwell read (`resolve_store_config` +
# `read_ready_dwell_instants`) can raise. Catching exactly this set — never a
# blanket `except` — keeps an unconfigured, unreachable or malformed tenant on
# the unknowable-instant path instead of crashing the ranking pass that asked.
_DWELL_READ_ERRORS: tuple[type[Exception], ...] = (
    LivespecConfigUnreadableError,
    ConnectionPrefixMissingError,
    BeadsCredentialMissingError,
    BeadsConnectionError,
    BeadsTenantMissingError,
    BeadsCommandError,
    BeadsMappingError,
)

# Single-slot memo key for the once-read tenant-wide instant map.
_INSTANTS_KEY = "instants"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadyAgingOrder:
    """The two aging inputs one call site hands `ready_sort_key`.

    Carried as a pair rather than resolved twice at each site: the ratified
    clause requires `next` and the Dispatcher to compose the IDENTICAL key, and
    a pair resolved once per project root is what makes that structural instead
    of a convention two call sites must remember.
    """

    ready_since_lookup: Callable[[str], datetime | None]
    ready_aging_threshold_hours: float


def ready_aging_order(*, project_root: Path) -> ReadyAgingOrder:
    """Resolve the aging inputs for one ready-ordering pass over `project_root`.

    The bound is the governed repository's own
    `dispatcher.ready_aging_threshold_hours`, read through the same resolver the
    ready-aging attention fact reads it through, so the ordering and the
    surfacing can never disagree about when an item is starved. A repository
    that declares none gets the documented default.
    """
    return ReadyAgingOrder(
        ready_since_lookup=_DurableReadySince(project_root=project_root),
        ready_aging_threshold_hours=float(
            unsafe_perform_io(
                resolve_ready_aging_threshold_hours(cwd=project_root).value_or(
                    DEFAULT_READY_AGING_THRESHOLD_HOURS
                )
            )
        ),
    )


def unaged_ready_order() -> ReadyAgingOrder:
    """The inert order: every ready instant unknowable, so `id` breaks every tie.

    What a caller holding no project root composes — the pure-function tier of
    `rank_candidates`, whose callers pass items directly and have no tenant to
    read. It is the ratified unknowable-instant path rather than a special case:
    the ordering degrades to `(rank, id)` exactly as it did before aging.
    """
    return ReadyAgingOrder(
        ready_since_lookup=_UnknowableReadySince(),
        ready_aging_threshold_hours=float(DEFAULT_READY_AGING_THRESHOLD_HOURS),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _UnknowableReadySince:
    """Callable reporting every item's ready instant as unknowable.

    A callable class rather than a plain function for the same reason
    `_DurableReadySince` is one: the runtime invokes the lookup POSITIONALLY,
    and only a `__call__` dunder may take positional parameters under the
    keyword-only-args rule.
    """

    def __call__(self, item_id: str) -> datetime | None:
        _ = item_id
        return None


@dataclass(frozen=True, slots=True, kw_only=True)
class _DurableReadySince:
    """Callable resolving an item id to its durable `ready_since` instant.

    A callable class (not a closure) because the runtime invokes the lookup
    POSITIONALLY — `ready_since_lookup(item_id)` — and only a `__call__` dunder
    may take positional parameters under the keyword-only-args rule.
    `_instants_cache` is the lazily-populated single-slot memo holding the one
    tenant-wide read.
    """

    project_root: Path
    _instants_cache: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def __call__(self, item_id: str) -> datetime | None:
        return _parse_instant(instant=self._instants().get(item_id))

    def _instants(self) -> dict[str, str | None]:
        if _INSTANTS_KEY not in self._instants_cache:
            self._instants_cache[_INSTANTS_KEY] = _read_instants(project_root=self.project_root)
        return self._instants_cache[_INSTANTS_KEY]


def _read_instants(*, project_root: Path) -> dict[str, str | None]:
    read = attempt(
        action=lambda: read_ready_dwell_instants(
            path=resolve_store_config(cwd=project_root, work_items_arg=None)
        ),
        exceptions=_DWELL_READ_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return {}
    return read


def _parse_instant(*, instant: str | None) -> datetime | None:
    """Read a stored `ready_since` string as a UTC instant; `None` when unusable.

    The store writes the repo's canonical `...Z` form, which `fromisoformat`
    cannot read on the pinned Python floor, so the suffix is normalized to an
    explicit UTC offset before parsing.
    """
    if instant is None:
        return None
    parsed = parse_iso_datetime(text=instant.removesuffix("Z") + "+00:00")
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    return parsed.astimezone(timezone.utc)

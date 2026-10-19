"""Dispatcher factory ledger pinning."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    has_fabro_factories,
    has_fabro_factory,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_effective_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_overflow_selection import (
    OverflowSelection,
    journal_overflow_selection,
    overflow_selection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path, store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.store import (
    dispatch_factory_for,
    record_dispatch_factory,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "args_with_dispatch_factory_target",
    "dispatch_factory_targets",
    "resolve_dispatch_factory_target",
    "unrecorded_dispatch_factory_target",
]

_ENV_FABRO_FACTORY = "LIVESPEC_FABRO_FACTORY"

# The EXPECTED ledger-read faults a pre-claim pin read degrades through: an id
# the tenant does not hold, a connection it cannot resolve, and a configuration
# it cannot parse. A bug still raises.
_LEDGER_READ_FAULTS: tuple[type[Exception], ...] = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


def dispatch_factory_targets(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_ids: Sequence[str],
) -> tuple[FactoryTarget, ...]:
    """Every distinct factory target this selection would dispatch to, UNRECORDED.

    The same precedence `resolve_dispatch_factory_target` applies — explicit flag
    or environment, else the item's own recorded pin, else the configured default
    — with the WRITE deliberately absent. A pre-claim gate must leave the ledger
    exactly as it found it: the clause requires currency to be evaluated before
    any ledger mutation, so recording a factory here would be the mutation the
    refusal is supposed to precede.

    DISTINCT BY NAME, in first-appearance order. One wave can carry items pinned
    to two factories, and each must be evaluated against its own serving commit;
    evaluating the same target once per item would spend one engine round trip
    per item for one answer.
    """
    config = _pin_store(repo=repo)
    explicit = _explicit_factory(args=args)
    targets: dict[str, FactoryTarget] = {}
    for work_item_id in work_item_ids:
        target = _unrecorded_target(
            repo=repo, config=config, work_item_id=work_item_id, explicit=explicit
        )
        _ = targets.setdefault(target.name, target)
    return tuple(targets.values())


def unrecorded_dispatch_factory_target(
    *,
    repo: Path,
    work_item_id: str,
    explicit: str | None = None,
) -> FactoryTarget:
    """ONE item's factory target under the dispatch precedence, UNRECORDED.

    The single-item form of `dispatch_factory_targets`, for a caller that holds
    no `argparse.Namespace` to read an explicit flag out of — admission, which
    stamps the pending claim before any factory has been recorded. `explicit`
    is therefore a NAME rather than a namespace, defaulting to none, and the
    environment override is still honoured because `resolve_fabro_factory`
    reads it itself.

    Both forms route through `_unrecorded_target`, so the precedence exists
    once: a second spelling of "explicit, else pin, else default" is how two
    callers come to disagree about which factory an item dispatches to.
    """
    return _unrecorded_target(
        repo=repo,
        config=_pin_store(repo=repo),
        work_item_id=work_item_id,
        explicit=explicit,
    )


def _unrecorded_target(
    *,
    repo: Path,
    config: StoreConfig | None,
    work_item_id: str,
    explicit: str | None,
) -> FactoryTarget:
    """The precedence itself: explicit name, else the item's usable pin, else default."""
    recorded = _recorded_pin(config=config, work_item_id=work_item_id)
    factory = explicit or _usable_recorded_factory(repo=repo, recorded=recorded)
    return _placement(repo=repo, pinned=factory).target


@dataclass(frozen=True, kw_only=True)
class _Placement:
    """Where this dispatch goes, and the selection that chose it when one did.

    `selection` is non-None exactly when overflow selection APPLIED — the
    dispatch carried no pin and the repository declares a usable
    `dispatcher.overflow_factories` — which is also exactly when the clause
    requires a journal record. Carrying the two together is what keeps the
    record from being written for a pinned dispatch, which the clause forbids,
    and from being skipped for an unpinned one.
    """

    target: FactoryTarget
    selection: OverflowSelection | None


def _placement(*, repo: Path, pinned: str | None) -> _Placement:
    """Resolve a possibly-absent pinned name, ranking the candidates when absent.

    A PINNED dispatch returns before `overflow_selection` is reached, which is
    what satisfies the clause's "without reading either server's run count or
    `max_concurrent_runs`": the reads are not performed and discarded, they are
    not performed. An unpinned dispatch in a repository that configures no
    overflow array returns the same way, because the selection answers `None`
    before reading anything.
    """
    if pinned is not None:
        return _Placement(target=resolve_fabro_factory(cwd=repo, factory=pinned), selection=None)
    selection = overflow_selection(repo=repo)
    if selection is None:
        return _Placement(target=resolve_fabro_factory(cwd=repo), selection=None)
    return _Placement(
        target=resolve_fabro_factory(cwd=repo, factory=selection.chosen),
        selection=selection,
    )


def _pin_store(*, repo: Path) -> StoreConfig | None:
    """The tenant connection the pins are read through, or `None` when unresolvable.

    Wrapped for the same reason `_recorded_pin` is, and it is the arm that
    actually fires: `store_config` RAISES on a repository whose
    `connection.prefix` is unset or whose `.livespec.jsonc` will not parse, and
    that happens BEFORE any row is read — so an unwrapped resolution escaped the
    pre-dispatch wall as a traceback about the very file it was about to name.
    `None` means no pin can be read, which resolves every item onto the
    configured default: the same answer an unpinned item already gets.
    """
    config = attempt(action=lambda: store_config(repo=repo), exceptions=_LEDGER_READ_FAULTS)
    return None if isinstance(config, AttemptFailure) else config


def _recorded_pin(*, config: StoreConfig | None, work_item_id: str) -> str | None:
    """One item's recorded factory pin, degrading to none on a ledger fault.

    Wrapped because this runs inside the PRE-DISPATCH WALL, whose whole purpose
    is rendering actionable refusals: an unreadable or absent row would otherwise
    escape as a traceback from the one surface that must not produce one. An
    unreadable pin is also an answer the caller can act on — the configured
    default is exactly what a dispatch with no recorded pin resolves — whereas
    `resolve_dispatch_factory_target` runs after admission, where the row is
    known to exist, and deliberately keeps its unwrapped read.
    """
    if config is None:
        return None
    recorded = attempt(
        action=lambda: dispatch_factory_for(path=config, work_item_id=work_item_id),
        exceptions=_LEDGER_READ_FAULTS,
    )
    return None if isinstance(recorded, AttemptFailure) else recorded


def resolve_dispatch_factory_target(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> FactoryTarget:
    """Resolve and persist the Fabro factory target for one dispatch.

    This is the ONE path that journals an overflow selection, because it is the
    one that RECORDS the chosen factory. The pre-claim gates rank through
    `_unrecorded_target`, which writes nothing: a record per gate would make the
    clause's "one record" several, each describing a reading no dispatch acted
    on.
    """
    config = store_config(repo=repo)
    explicit = _explicit_factory(args=args)
    recorded = dispatch_factory_for(path=config, work_item_id=work_item_id)
    factory = explicit or _usable_recorded_factory(repo=repo, recorded=recorded)
    placement = _placement(repo=repo, pinned=factory)
    if placement.selection is not None:
        journal_overflow_selection(
            journal=_journal_for(args=args, repo=repo),
            work_item_id=work_item_id,
            selection=placement.selection,
        )
    record_dispatch_factory(path=config, work_item_id=work_item_id, factory=placement.target.name)
    return placement.target


def _journal_for(*, args: argparse.Namespace, repo: Path) -> JournalFile:
    """This dispatch's journal, read DEFENSIVELY off the invocation's arguments.

    `journal_path` reads `args.journal` directly, and not every caller of this
    resolution holds a dispatch namespace — a resume surface building its own
    arguments carries no `--journal` — so the attribute is read with a default
    rather than assumed. A record is still written in that case, to the
    repository's own default journal, because the clause requires one per
    selection and an unreadable override is not a reason to drop it.
    """
    namespace = argparse.Namespace(journal=getattr(args, "journal", None))
    return JournalFile(path=journal_path(args=namespace, repo=repo))


def args_with_dispatch_factory_target(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> argparse.Namespace:
    """Return an args clone carrying the ledger-pinned factory target.

    The engine binary travels WITH the target. The pin can select a different
    factory than the dispatch preamble resolved, and the candidate client
    cannot talk to the legacy server, so a clone carrying the new target beside
    the old factory's binary would send one factory's client at another
    factory's engine — with nothing in the record to say so.
    """
    cloned = argparse.Namespace(**vars(args))
    target = resolve_dispatch_factory_target(
        args=args,
        repo=repo,
        work_item_id=work_item_id,
    )
    cloned.fabro_factory_target = target
    effective = factory_effective_fabro_bin(args=args, factory=target)
    if effective is not None:
        cloned.fabro_bin = effective
    return cloned


def _explicit_factory(*, args: argparse.Namespace) -> str | None:
    factory = getattr(args, "factory", None)
    if isinstance(factory, str) and factory != "":
        return factory
    env_value = os.environ.get(_ENV_FABRO_FACTORY)
    if env_value is not None and env_value != "":
        return env_value
    return None


def _usable_recorded_factory(*, repo: Path, recorded: str | None) -> str | None:
    if recorded is None:
        return None
    if not has_fabro_factories(cwd=repo):
        return recorded
    if has_fabro_factory(cwd=repo, factory=recorded):
        return recorded
    return None

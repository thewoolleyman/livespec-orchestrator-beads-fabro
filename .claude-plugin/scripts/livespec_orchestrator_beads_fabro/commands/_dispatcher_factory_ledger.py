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
    "args_with_earlier_dispatch_factory_target",
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

    THE RANKING IS TAKEN ONCE FOR THE WHOLE INVOCATION, and the dedup above is
    not what delivers that: every unpinned item of one wave resolves to the same
    ranked choice, so a ranking reached inside the loop spends four engine round
    trips PER ITEM — four-fold the cost this dedup exists to avoid, and inside
    the pre-dispatch wall, whose whole purpose is to settle admission before
    anything further is spent. It is also several independent live readings,
    which can disagree with each other, while the `dispatcher.minimum_release`
    floor is graded only against the targets this one call returns.

    It is taken LAZILY, so a wave whose every item carries a pin — and an empty
    selection — still reads no server's capacity at all.
    """
    config = _pin_store(repo=repo)
    explicit = _explicit_factory(args=args)
    pinned = [
        _unrecorded_pin(repo=repo, config=config, work_item_id=work_item_id, explicit=explicit)
        for work_item_id in work_item_ids
    ]
    selection = _ranking(repo=repo, unpinned=any(name is None for name in pinned))
    targets: dict[str, FactoryTarget] = {}
    for name in pinned:
        target = _placement(repo=repo, pinned=name, selection=selection).target
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
    is therefore a NAME rather than a namespace, defaulting to none, and
    `LIVESPEC_FABRO_FACTORY` is honoured by the precedence itself rather than
    by `resolve_fabro_factory`'s own environment layer, which an unpinned
    placement no longer reaches.

    Both forms route through `_unrecorded_pin`, so the precedence exists once:
    a second spelling of "explicit, else pin, else environment, else default"
    is how two callers come to disagree about which factory an item dispatches
    to — and when THIS caller disagrees, the disagreement is a claim stamped
    with a factory the dispatch never reaches.
    """
    pinned = _unrecorded_pin(
        repo=repo,
        config=_pin_store(repo=repo),
        work_item_id=work_item_id,
        explicit=explicit,
    )
    return _placement(
        repo=repo,
        pinned=pinned,
        selection=_ranking(repo=repo, unpinned=pinned is None),
    ).target


def _unrecorded_pin(
    *,
    repo: Path,
    config: StoreConfig | None,
    work_item_id: str,
    explicit: str | None,
) -> str | None:
    """One item's pinned factory under the PRE-CLAIM read discipline, or `None`.

    The read discipline is the whole reason this is not `_pinned_factory`
    itself: a pre-claim caller reads the recorded pin DEFENSIVELY, through
    `_recorded_pin`, while the dispatch resolution reads it unwrapped from a
    row it knows exists. Both then apply one precedence.
    """
    return _pinned_factory(
        repo=repo,
        explicit=explicit,
        recorded=_recorded_pin(config=config, work_item_id=work_item_id),
    )


def _pinned_factory(*, repo: Path, explicit: str | None, recorded: str | None) -> str | None:
    """What PINS this dispatch, or `None` when nothing does and the ranking decides.

    The precedence itself: the explicit name, else the item's usable recorded
    pin, else `LIVESPEC_FABRO_FACTORY`. The environment layer is LAST, and it is
    the layer a caller holding no namespace depends on — `_explicit_factory` has
    already answered it for a caller that holds one, so for that caller this
    layer is unreachable rather than a second precedence. That is also why the
    variable ranks ABOVE a recorded pin through a namespace and BELOW one
    without, exactly as each caller's own prose has always described it.

    Returning the NAME rather than a resolved target is what keeps the ranking
    out of the precedence: whether a dispatch is pinned is settled before any
    server is asked anything, which is what the clause's "without reading any
    server's run count or `max_concurrent_runs`" requires of EVERY pin — and
    the environment pin is the one that reached the ranking when the layer below
    was `resolve_fabro_factory`'s rather than this one.
    """
    return explicit or _usable_recorded_factory(repo=repo, recorded=recorded) or _env_factory()


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


def _placement(
    *,
    repo: Path,
    pinned: str | None,
    selection: OverflowSelection | None,
) -> _Placement:
    """Place this dispatch on a pinned name, on a ranked choice, or on the default.

    Takes the ranking rather than performing it, so one ranking can place every
    unpinned item of one wave. The clause's "without reading either server's run
    count or `max_concurrent_runs`" is then answered by `_ranking` never being
    asked for one: a pinned name is placed here with no capacity read whether or
    not the invocation took a reading for some sibling item.

    A pinned name is honoured even when a `selection` was taken, which is not
    redundant — a wave mixing pinned and unpinned items ranks once for the
    unpinned ones, and the pinned ones must not inherit that choice.
    """
    if pinned is not None:
        return _Placement(target=resolve_fabro_factory(cwd=repo, factory=pinned), selection=None)
    if selection is None:
        return _Placement(target=resolve_fabro_factory(cwd=repo), selection=None)
    return _Placement(
        target=resolve_fabro_factory(cwd=repo, factory=selection.chosen),
        selection=selection,
    )


def _ranking(*, repo: Path, unpinned: bool) -> OverflowSelection | None:
    """The ONE overflow ranking of this invocation, taken only when it is needed.

    `unpinned` is a question about the whole INVOCATION rather than about one
    item, and passing it in rather than deriving it here is what lets the
    multi-item form ask it once over its whole list while the single-item forms
    ask it of their one item — without either spelling "rank only when unpinned"
    a second time, which is how one caller comes to rank where another does not.

    `None` is returned for a pinned invocation as well as for a repository that
    declares no overflow array, and both mean the same thing to `_placement`:
    nothing was read, so nothing was chosen.
    """
    return overflow_selection(repo=repo) if unpinned else None


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
    `_unrecorded_pin`, which writes nothing: a record per gate would make the
    clause's "one record" several, each describing a reading no dispatch acted
    on.

    The recorded pin is read UNWRAPPED here, unlike every pre-claim read, which
    is why the precedence is applied to a value rather than reached through
    `_unrecorded_pin`: this runs after admission, where the row is known to
    exist, so a fault is a bug rather than an item with no pin.
    """
    config = store_config(repo=repo)
    explicit = _explicit_factory(args=args)
    recorded = dispatch_factory_for(path=config, work_item_id=work_item_id)
    pinned = _pinned_factory(repo=repo, explicit=explicit, recorded=recorded)
    placement = _placement(
        repo=repo, pinned=pinned, selection=_ranking(repo=repo, unpinned=pinned is None)
    )
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


def args_with_earlier_dispatch_factory_target(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> argparse.Namespace:
    """Clone ``args`` for an earlier dispatch's persisted factory, without a write.

    Resume observation runs before admission and must inspect the earlier run on
    the factory that dispatched it.  It therefore ignores an invocation's
    explicit factory preference and resolves the item's recorded pin without
    persisting anything.  A missing historical pin degrades to the normal
    configured default for records created before factory pinning existed.
    """
    cloned = argparse.Namespace(**vars(args))
    config = _pin_store(repo=repo)
    recorded = _recorded_pin(config=config, work_item_id=work_item_id)
    factory = _usable_recorded_factory(repo=repo, recorded=recorded)
    target = resolve_fabro_factory(cwd=repo, factory=factory or "")
    cloned.fabro_factory_target = target
    cloned.fabro_bin = factory_effective_fabro_bin(args=args, factory=target) or cloned.fabro_bin
    return cloned


def _explicit_factory(*, args: argparse.Namespace) -> str | None:
    """The name an invocation NAMES: the `--factory` flag, else the environment.

    Both layers together, because for a namespace-carrying caller the variable
    outranks the item's own recorded pin — `--factory` and the variable are two
    spellings of one routing decision, and `drive.py` has only the second.
    """
    factory = getattr(args, "factory", None)
    if isinstance(factory, str) and factory != "":
        return factory
    return _env_factory()


def _env_factory() -> str | None:
    """A non-empty `LIVESPEC_FABRO_FACTORY`, or `None` when it names nothing."""
    env_value = os.environ.get(_ENV_FABRO_FACTORY)
    return env_value if env_value is not None and env_value != "" else None


def _usable_recorded_factory(*, repo: Path, recorded: str | None) -> str | None:
    if recorded is None:
        return None
    if not has_fabro_factories(cwd=repo):
        return recorded
    if has_fabro_factory(cwd=repo, factory=recorded):
        return recorded
    return None

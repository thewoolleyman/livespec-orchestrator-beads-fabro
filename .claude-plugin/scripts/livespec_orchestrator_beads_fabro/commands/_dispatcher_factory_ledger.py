"""Dispatcher factory ledger pinning."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    dispatcher_block,
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
    "explicit_dispatch_factory",
    "explicit_factory_selection_refusal",
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
    """Every distinct factory target this selection could dispatch to, UNRECORDED.

    Explicit flag, else the environment, else — on a resume — the item's own
    recorded pin, else the ranked or configured default, with the WRITE
    deliberately absent. A pre-claim gate must leave the ledger exactly as it
    found it: the clause requires currency to be evaluated before any ledger
    mutation, so recording a factory here would be the mutation the refusal is
    supposed to precede.

    BOTH ROUTES ARE RESOLVED AND THE TARGETS UNIONED, which is the one place
    this resolution differs from a dispatch's own, and it is forced by WHERE
    this runs. The recorded pin is a RESUME-only layer, and the route is
    assigned by recovery routing, which the clause places AFTER the
    pre-dispatch wall this gate runs inside — so at this point no item has a
    route and the question "is this a resume" has no answer yet. A gate that
    answered it anyway would be grading a factory by guess, and both guesses
    are wrong in their own direction. Assuming RESUME grades the engine the
    item merely used to run on while the fresh dispatch is submitted to
    `dispatcher.default_factory` or to an overflow-selected target that is
    never evaluated at all — the fail-OPEN this gate exists to close, and the
    common re-dispatch path, since every item that has ever dispatched carries
    a pin. Assuming FRESH refuses the whole selection on a condition of a
    factory a resume would never leave. The union grades both, so no route can
    reach an engine this gate has not graded.

    DISTINCT BY NAME, in first-appearance order, with the fresh placement first
    because every non-resume dispatch takes it. One wave can carry items pinned
    to two factories, and each must be evaluated against its own serving commit;
    evaluating the same target once per item — or once per route — would spend
    one engine round trip for an answer already held.

    THE RECORDED PIN IS READ ONCE PER ITEM, not once per route: the ledger read
    is the expensive half and the precedence is the cheap half, so `_route_pins`
    takes the row once and applies the precedence to it twice.

    THE RANKING IS TAKEN ONCE FOR THE WHOLE INVOCATION, and the dedup above is
    not what delivers that: every unpinned item of one wave resolves to the same
    ranked choice, so a ranking reached inside the loop spends four engine round
    trips PER ITEM — four-fold the cost this dedup exists to avoid, and inside
    the pre-dispatch wall, whose whole purpose is to settle admission before
    anything further is spent. It is also several independent live readings,
    which can disagree with each other, while the per-factory Fabro currency
    gate is graded only against the targets this one call returns.

    It is taken LAZILY, and the union is what decides when: an invocation whose
    every ROUTE is pinned — an explicit `--factory`, or `LIVESPEC_FABRO_FACTORY`,
    which pin both routes alike — and an empty selection still read no server's
    capacity at all. A recorded pin no longer suppresses the reading, because the
    fresh route it leaves unpinned is exactly the one an overflow ranking places.
    """
    config = _pin_store(repo=repo)
    explicit = explicit_dispatch_factory(args=args)
    pinned = [
        name
        for work_item_id in work_item_ids
        for name in _route_pins(
            repo=repo, config=config, work_item_id=work_item_id, explicit=explicit
        )
    ]
    selection = _ranking(repo=repo, unpinned=any(name is None for name in pinned))
    targets: dict[str, FactoryTarget] = {}
    for name in pinned:
        target = _placement(repo=repo, pinned=name, selection=selection).target
        _ = targets.setdefault(target.name, target)
    return tuple(targets.values())


def _route_pins(
    *,
    repo: Path,
    config: StoreConfig | None,
    work_item_id: str,
    explicit: str | None,
) -> tuple[str | None, ...]:
    """One item's pin under EACH route, fresh first, from ONE ledger read.

    The pre-dispatch wall precedes recovery routing, so it must grade both
    routes; reading the recorded row twice to do so would double the per-item
    ledger cost of every gated dispatch for a value that cannot change between
    the two reads. The precedence itself stays in `_pinned_factory`, so this
    adds a second ROUTE rather than a second spelling of the order.

    FRESH FIRST, because that is the route every non-resume dispatch takes and
    the gate reports the FIRST refusal it finds: a selection whose fresh target
    and recorded pin are both unadmissible should name the one the dispatch is
    most likely to reach.
    """
    recorded = _recorded_pin(config=config, work_item_id=work_item_id)
    return tuple(
        _pinned_factory(repo=repo, explicit=explicit, recorded=recorded, resume=resume)
        for resume in (False, True)
    )


def unrecorded_dispatch_factory_target(
    *,
    repo: Path,
    work_item_id: str,
    resume: bool = False,
    explicit: str | None = None,
) -> FactoryTarget:
    """ONE item's factory target under the dispatch precedence, UNRECORDED.

    The single-item, single-ROUTE form of `dispatch_factory_targets`, for a
    caller that holds no `argparse.Namespace` to read an explicit flag out of —
    admission, which stamps the pending claim before any factory has been
    recorded. It takes a stated route rather than grading both, because a stamp
    names ONE factory where the gate grades every factory a selection could
    reach. `explicit` is therefore a NAME rather than a namespace, and
    `LIVESPEC_FABRO_FACTORY` is honoured by the precedence itself rather than
    by `resolve_fabro_factory`'s own environment layer, which an unpinned
    placement no longer reaches.

    `resume` is the ROUTE recovery routing assigned this item before the
    admission valve ran, which the clause makes the stamp's own input: "The
    admission claim stamp MUST apply the same order, using the route recovery
    routing assigned before the admission valve". It defaults to the FRESH
    answer because that is what the clause makes every other dispatch — "Every
    other dispatch is a FRESH dispatch, whatever entry point carries it" — and
    because the default has to fail in the safe direction: a caller that states
    nothing never reads the pin, which is a dispatch sent to the repository's
    own default, whereas a resume-by-default would send a fresh dispatch to a
    factory the item merely used to run on.

    Both forms route through `_unrecorded_pin`, so the precedence exists once:
    a second spelling of "explicit, else environment, else pin, else default"
    is how two callers come to disagree about which factory an item dispatches
    to — and when THIS caller disagrees, the disagreement is a claim stamped
    with a factory the dispatch never reaches.
    """
    pinned = _unrecorded_pin(
        repo=repo,
        config=_pin_store(repo=repo),
        work_item_id=work_item_id,
        explicit=explicit,
        resume=resume,
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
    resume: bool,
) -> str | None:
    """One item's pinned factory under the PRE-CLAIM read discipline, or `None`.

    The read discipline is the whole reason this is not `_pinned_factory`
    itself: a pre-claim caller reads the recorded pin DEFENSIVELY, through
    `_recorded_pin`, while the dispatch resolution reads it unwrapped from a
    row it knows exists. Both then apply one precedence.

    `resume` is REQUIRED here rather than defaulted, unlike on the public entry
    point above: the two pre-claim resolutions answer the route question
    differently — the pre-dispatch wall precedes routing and grades both routes
    through `_route_pins`, while the admission stamp follows routing and states
    the one route it was assigned — and a default would let whichever caller is
    written next inherit the other one's answer silently.
    """
    return _pinned_factory(
        repo=repo,
        explicit=explicit,
        recorded=_recorded_pin(config=config, work_item_id=work_item_id),
        resume=resume,
    )


def _pinned_factory(
    *, repo: Path, explicit: str | None, recorded: str | None, resume: bool
) -> str | None:
    """What PINS this dispatch, or `None` when nothing does and the ranking decides.

    The precedence itself, and it is the RATIFIED one in one place: the explicit
    `--factory` name, then `LIVESPEC_FABRO_FACTORY`, then the item's usable
    recorded pin. The environment layer sits HERE rather than inside
    `explicit_dispatch_factory`, which is what makes the order identical for a caller
    that holds an `argparse.Namespace` and one that does not — admission holds
    none, and when its order differed the disagreement was a claim stamped with
    a factory the dispatch never reaches.

    THE RECORDED PIN IS A RESUME-ONLY LAYER, which is what `resume` decides:
    "for a resume only, the item's recorded factory", and "a fresh dispatch MUST
    NOT read the item's recorded factory as a pin. When no explicit selection is
    made it MUST proceed as an unpinned dispatch, so changing
    `dispatcher.default_factory` re-routes the next fresh dispatch of every item
    onto the new default factory". A resume is the one route that CONTINUES the
    run lineage the recorded factory belongs to; every other dispatch starts a
    lineage of its own, and reading the pin there sends an item back to whichever
    factory it last ran on however far the repository's default has since moved.
    Measured 2026-10-23 on `tdd-proof-lv352h`, whose repository defaults to
    `petri`: a probe launched with nothing pinned resolved
    `--server https://hp-xubuntu.perch-rudd.ts.net:32276`, because the item's
    metadata still recorded `legacy` from an earlier failed run — and fifteen
    open items across seven tenants were in that state.

    THE VARIABLE OUTRANKS THE RECORDED PIN, which is the whole point of its
    position: a pinned item is pinned by its OWN dispatch history, while the
    variable is this invocation's routing decision, and the item an operator
    re-routes is precisely one that has been dispatched elsewhere before.
    Measured 2026-10-19: an item with fifteen hp journal rows, dispatched with
    the variable naming `petri`, was stamped `hp`, and the reconcile pass then
    held that claim against hp for a run living on gmktec.

    Returning the NAME rather than a resolved target is what keeps the ranking
    out of the precedence: whether a dispatch is pinned is settled before any
    server is asked anything, which is what the clause's "without reading any
    server's run count or `max_concurrent_runs`" requires of EVERY pin — and
    the environment pin is the one that reached the ranking when the layer below
    was `resolve_fabro_factory`'s rather than this one.
    """
    if not resume:
        return explicit or _env_factory()
    return explicit or _env_factory() or _usable_recorded_factory(repo=repo, recorded=recorded)


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
    resume: bool = False,
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

    `resume` is this item's assigned ROUTE, carried from the launch path on that
    item's own copy of the arguments, and it defaults to the FRESH answer for
    the reason `unrecorded_dispatch_factory_target` gives: that is what the
    clause makes every other dispatch, and it is the direction a forgotten
    statement fails safely in.
    """
    config = store_config(repo=repo)
    explicit = explicit_dispatch_factory(args=args)
    recorded = dispatch_factory_for(path=config, work_item_id=work_item_id)
    pinned = _pinned_factory(repo=repo, explicit=explicit, recorded=recorded, resume=resume)
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
    resume: bool = False,
) -> argparse.Namespace:
    """Return an args clone carrying the ledger-pinned factory target.

    The engine binary travels WITH the target. The pin can select a different
    factory than the dispatch preamble resolved, and the candidate client
    cannot talk to the legacy server, so a clone carrying the new target beside
    the old factory's binary would send one factory's client at another
    factory's engine — with nothing in the record to say so.

    `resume` is this item's ROUTE and is passed straight through, because the
    route is a property of the ITEM and this is the per-item step that applies
    its pins. It must never be inferred from the resume ATTRIBUTES a caller
    sets on the clone — `recovery_launch_args` resolves the factory before it
    writes them, and a `seeded` route sets a head of its own — so a reader of
    those attributes would answer the route question for the wrong routes in
    both directions.
    """
    cloned = argparse.Namespace(**vars(args))
    target = resolve_dispatch_factory_target(
        args=args,
        repo=repo,
        work_item_id=work_item_id,
        resume=resume,
    )
    cloned.fabro_factory_target = target
    effective = factory_effective_fabro_bin(args=args, factory=target)
    if effective is not None:
        cloned.fabro_bin = effective
    return cloned


def explicit_dispatch_factory(*, args: argparse.Namespace) -> str | None:
    """The name an invocation NAMES on its command line: the `--factory` flag.

    The FLAG alone. `LIVESPEC_FABRO_FACTORY` is the layer immediately below it
    and is read by `_pinned_factory`, so reading it here as well would give a
    namespace-carrying caller its own copy of the precedence — and a copy is
    what let the two orders drift apart. The attribute is read with a default
    because not every caller of the resolution holds a dispatch namespace.

    PUBLIC because the ADMISSION path needs it and holds no namespace of its
    own: the valve stamps the pending claim and the flag is the one layer the
    environment cannot stand in for, so the dispatch paths read the flag here
    and hand the valve the NAME. A second reader spelling `args.factory` for
    itself is how the stamp came to answer differently from the dispatch.
    """
    factory = getattr(args, "factory", None)
    return factory if isinstance(factory, str) and factory != "" else None


def explicit_factory_selection_refusal(*, args: argparse.Namespace, repo: Path) -> str | None:
    """Refuse an explicit name absent from a declared factory table.

    An implicit target and a recorded pin deliberately do not pass through this
    grade: an unconfigured repository retains its ambient single-factory target,
    and a stale recorded pin remains an unpinned dispatch.  Only a caller's flag
    or non-empty environment selection is an instruction to address that exact
    declared factory.
    """
    selected = explicit_dispatch_factory(args=args) or _env_factory()
    if selected is None:
        return None
    factories_raw = dispatcher_block(cwd=repo).get("factories")
    if not isinstance(factories_raw, dict):
        return None
    factories = cast("dict[str, object]", factories_raw)
    if selected in factories:
        return None
    declared = ", ".join(repr(name) for name in factories)
    return (
        f"ERROR: explicit factory selection {selected!r} is not declared by"
        f" dispatcher.factories; declared factories are: {declared}. This dispatch"
        " is refused rather than falling back to another factory or this host's"
        " local Fabro server\n"
    )


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

"""The host registry a registry-backed factory resolves through, GRADED.

`_factory_registry` reads the `dispatcher.factories` entry's `registry` key and
whatever the host registry said; this module is the GRADE of that reading, and
the split is the same pure-from-impure one `_dispatcher_factory_environment`
makes in its own direction: the reading is a leaf `_config` imports, so a grade
living beside it could not reach `FactoryTarget` without closing an import
cycle.

AN UNRESOLVABLE REGISTRY IS REFUSED BEFORE THE CLAIM, and this one has no later
surface at which the fault is legible at all. An unusable `bin` fails at the
launch; an unusable `environment` at least lands the run somewhere and dies in a
prepare step. A registry that does not resolve leaves `FactoryTarget.server` at
None, which is the SAME value an unconfigured repository carries and which every
downstream surface therefore reads as "this factory declares no server" — the
ambient local Fabro. So the dispatch succeeds, on the dispatching host's own
engine, and the item's record names a factory the work never reached. There is
nothing to triage afterwards, because nothing failed. The reading has to be
graded while the item is still unclaimed.

THE REFUSAL NAMES THE FACTORY AND THE PATH, and both are load-bearing. A
dispatch resolves its factory from an explicit flag, the environment, the item's
own recorded pin or `dispatcher.default_factory`, so a message about "a
registry-backed factory" does not say which entry of `dispatcher.factories` the
operator is looking at. And WHICH registry file was read is itself a
configuration answer — the `LIVESPEC_FABRO_FACTORY_REGISTRY` override and the
host default are different files, and an operator told only that the registry
did not resolve has an even chance of provisioning the one this host does not
read. The path comes off the READING rather than from a second environment
lookup, so the message cannot name a file the resolution did not use.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._factory_registry import (
    FLEET_DEFAULT_FACTORY,
)

__all__: list[str] = [
    "factory_registry_refusal",
    "factory_registry_unobservable",
    "registry_sourced_path",
]


def registry_sourced_path(*, factory: FactoryTarget, key: str) -> str | None:
    """The registry file that supplied one client key's value, or None for the committed entry.

    The reading the `bin` and `environment` grades name their source from. Both
    facts come off the resolved target — which keys the registry supplied, and
    which file was read — rather than from a second configuration read, so a
    refusal cannot name a file this resolution did not use or a source this
    merge did not take.

    It lives HERE, with the registry reading's other grades, because the pair it
    joins is the registry's: the per-key decision `_factory_client_settings`
    made, and the path `_factory_registry` read. `_factory_client_source`, which
    renders the refusal's words, deliberately takes neither — it is a pure
    renderer shared with the transport grade, which holds no `FactoryTarget` at
    all.

    `None` for a committed key rather than a separate answer for "no source
    declared it": a key no source declared is never graded, so every caller has
    already returned by the time it could ask.
    """
    if key not in factory.registry_sourced_client_keys:
        return None
    return factory.registry.path


def factory_registry_unobservable(*, factory: FactoryTarget) -> str | None:
    """Why a registry-backed factory cannot be ADDRESSED, naming it; else None.

    The REFUSAL below is for the dispatch path, which may still decline to place
    work. This is for the OBSERVING surfaces the same clause names — plan run
    liveness, the merge-hold liveness guard — which run after the work was
    placed and may decline nothing: each owes the failure behaviour already
    ratified for an unreachable factory on that surface, which is to report the
    factory as unobservable and to name it.

    WHY A SURFACE CANNOT JUST READ `server is None`, which is the reading every
    one of them already performed. It is the same value an unconfigured
    repository carries, and THERE it means the ambient local Fabro — so a
    consumer that opened a port on it surveyed whichever engine the dispatching
    host runs and answered cleanly about the wrong machine. Asking whether the
    entry was registry-BACKED is what separates "this factory declares no
    server" from "this factory's address did not resolve", and only the first of
    those may be surveyed locally.

    THE DETAIL NAMES THE FACTORY AND, WHERE THE REGISTRY DECIDED IT, THE PATH.
    A liveness verdict naming neither leaves an operator to read every declared
    entry; and WHICH registry file was read is a configuration answer of its own,
    because the `LIVESPEC_FABRO_FACTORY_REGISTRY` override and the host default
    are different files. The CONFLICT arm names no path, for the reason the
    refusal below gives: that fault is in the governed repository's own committed
    configuration, which the registry had no part in deciding, so naming the file
    would point an operator at something that decided nothing.

    `factory` is REQUIRED where the refusal's is optional, because every caller
    here resolves a target before it can ask: a surface holding none has no
    factory it could report, which is a different absence from an unresolved one.
    """
    if not factory.registry.declared or factory.server is not None:
        return None
    if factory.registry.conflicting_keys:
        return (
            f"factory {factory.name} declares its registry together with a"
            " committed address, so its address is unresolved"
        )
    return (
        f"factory {factory.name} is registry-backed and its address did not"
        f" resolve from the factory registry at {factory.registry.path}"
    )


def factory_registry_refusal(*, factory: FactoryTarget | None) -> str | None:
    """Refuse a registry-backed factory whose address did not resolve, else None.

    An entry that is not registry-backed refuses nothing: `server` keeps its
    existing meaning and remains the supported form for an adopter outside this
    fleet.

    The CONFLICT arm is graded ahead of the registry's own answer, because the
    two faults live in different files and only one of them is this
    repository's: a committed entry that declares both sources is wrong whatever
    the host registry happens to say, and reporting the registry's answer first
    would send an operator to edit host state over a fault in a tracked file.

    `factory` is optional for the same reason the `bin` and `environment`
    refusals' are: a caller that never ran the dispatch preamble — the
    needs-attention and standalone reconcile surfaces build their own arguments
    — has no target to consult, and that is the pre-clause behaviour rather than
    a fault.
    """
    if factory is None or not factory.registry.declared:
        return None
    if factory.registry.conflicting_keys:
        return _conflict_refusal(factory=factory)
    if factory.registry.detail is None:
        return None
    if factory.registry.fleet:
        return _fleet_refusal(factory=factory)
    return (
        f"ERROR: factory {factory.name} declares"
        f" dispatcher.factories.{factory.name}.registry, so its server address"
        f" must come from the factory registry at {factory.registry.path} —"
        f" and {factory.registry.detail}. Render that registry entry on this"
        " host, or point LIVESPEC_FABRO_FACTORY_REGISTRY at the file that"
        f" carries it; this dispatch is refused rather than sent to whichever"
        " Fabro this host runs\n"
    )


def _fleet_refusal(*, factory: FactoryTarget) -> str:
    """The refusal a dispatch resolving its default through `fleet` earns.

    Separate from the message above because the remedy is in a different place:
    that one tells an operator to provision the entry their own
    `dispatcher.factories` names, while here the repository has committed only
    the reserved value and every fact the operator needs — which file, and what
    it lacked — is the registry's. A message naming
    `dispatcher.factories.<name>.registry` would point at a key no fleet
    repository commits, and on the designation-unresolved arm `<name>` is the
    reserved value itself, so it would name a factory nobody declared.
    """
    return (
        f"ERROR: dispatcher.default_factory is {FLEET_DEFAULT_FACTORY!r}, so this"
        " dispatch's factory must come from the factory registry at"
        f" {factory.registry.path} — and {factory.registry.detail}. Designate a"
        " fleet default in that registry, or point"
        " LIVESPEC_FABRO_FACTORY_REGISTRY at the file that carries one; this"
        " dispatch is refused rather than sent to whichever Fabro this host"
        " runs\n"
    )


def _conflict_refusal(*, factory: FactoryTarget) -> str:
    """The refusal a registry-backed entry that also commits an address earns.

    Every conflicting key is enumerated rather than only the first, because they
    are ONE fault in ONE entry with ONE remedy — delete the committed address
    lines — and an operator told about half of it edits the entry, re-dispatches,
    and is refused again.
    """
    keys = ", ".join(
        f"dispatcher.factories.{factory.name}.{key}" for key in factory.registry.conflicting_keys
    )
    return (
        f"ERROR: factory {factory.name} declares"
        f" dispatcher.factories.{factory.name}.registry together with {keys};"
        " a registry-backed entry names no machine, so its addresses come from"
        " the factory registry and a committed one beside it is a second answer"
        " with no rule for choosing between them. Remove the committed"
        f" address(es), or remove the registry key and let factory"
        f" {factory.name} keep naming its machine itself\n"
    )

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

__all__: list[str] = [
    "factory_registry_refusal",
]


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
    return (
        f"ERROR: factory {factory.name} declares"
        f" dispatcher.factories.{factory.name}.registry, so its server address"
        f" must come from the factory registry at {factory.registry.path} —"
        f" and {factory.registry.detail}. Render that registry entry on this"
        " host, or point LIVESPEC_FABRO_FACTORY_REGISTRY at the file that"
        f" carries it; this dispatch is refused rather than sent to whichever"
        " Fabro this host runs\n"
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

"""The two grades of one host-factory-registry reading, and what each is FOR.

`factory_registry_refusal` is the DISPATCH path's grade and is bound end to end
by `tests/integration/test_factory_registry_resolution_scenario182.py`, which
drives it through `dispatch_preamble` over a real registry file on disk.
`factory_registry_unobservable` is the OBSERVING surfaces' grade and is bound
end to end by `tests/integration/test_factory_registry_consumers_scenario182.py`,
which drives it through plan run liveness and the merge-hold arm guard.

What is left for this module is the one input shape neither journey can reach
through its own entry point: an entry declaring `"registry": true` BESIDE a
committed address. On the dispatch path that entry is refused by
`factory_registry_refusal` before any observing surface is consulted, and no
observing surface can be reached with it in a repository the dispatch path
would run — so the conflict arm of the observing grade has no journey to ride.

WHY THE CONFLICT ARM EXISTS AT ALL, rather than the two grades sharing one
message. The two faults live in different FILES: a conflict is in the governed
repository's own committed `.livespec.jsonc` and is fixed by a commit, while an
unresolvable registry is host state the provisioning renders. The registry had
no part in deciding a conflict, so a detail naming the registry path there would
send an operator to provision a file that decided nothing — which is why the
conflict detail names no path and the registry detail does.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry import (
    factory_registry_unobservable,
)
from livespec_orchestrator_beads_fabro.commands._factory_registry import FactoryRegistryReading

_FACTORY = "petri"
_REGISTRY_PATH = "/etc/livespec/fabro-factories.json"
_SERVER = "https://petri.example:32276"


def _target(*, registry: FactoryRegistryReading, server: str | None = None) -> FactoryTarget:
    return FactoryTarget(name=_FACTORY, server=server, dev_token=None, registry=registry)


def test_a_registry_backed_entry_carrying_a_committed_address_is_unobservable_naming_no_path() -> (
    None
):
    """A conflicting entry reports unresolved, names the factory, and names no file.

    The absent path is asserted as a NEGATIVE rather than left unstated, because
    it is the whole difference between this arm and the one below: both leave
    `server` at None and both must report the factory as unobservable, and only
    one of them has a registry file an operator could act on.
    """
    detail = factory_registry_unobservable(
        factory=_target(
            registry=FactoryRegistryReading(
                declared=True, path=_REGISTRY_PATH, conflicting_keys=("server",)
            )
        )
    )

    assert detail is not None
    assert _FACTORY in detail
    assert "its address is unresolved" in detail
    assert _REGISTRY_PATH not in detail


def test_an_unresolvable_registry_backed_entry_names_the_factory_and_the_file_it_read() -> None:
    """The registry arm names the file, because which file was read is an answer.

    The override and the host default are two different paths, so an operator
    told only that the registry did not resolve has an even chance of
    provisioning the one this host does not read.
    """
    detail = factory_registry_unobservable(
        factory=_target(
            registry=FactoryRegistryReading(
                declared=True, path=_REGISTRY_PATH, detail="it holds no object entry named 'petri'"
            )
        )
    )

    assert detail is not None
    assert _FACTORY in detail
    assert _REGISTRY_PATH in detail


def test_an_entry_that_is_not_registry_backed_and_a_resolved_one_are_both_observable() -> None:
    """Neither an ordinary entry nor a resolved registry-backed one reports anything.

    The two are asserted together because they are the SAME `None` reached for
    opposite reasons, and a build that answered for only one of them would be
    wrong in a way no single case could see: an opinion about an ordinary
    `server` entry would make every unconfigured repository's liveness read
    unobservable, while an opinion about a resolved registry-backed entry would
    make every registry-backed factory permanently unreadable.
    """
    ordinary = _target(registry=FactoryRegistryReading(), server=_SERVER)
    resolved = _target(
        registry=FactoryRegistryReading(declared=True, path=_REGISTRY_PATH, server=_SERVER),
        server=_SERVER,
    )

    assert factory_registry_unobservable(factory=ordinary) is None
    assert factory_registry_unobservable(factory=resolved) is None

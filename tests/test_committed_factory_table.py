"""This repository's committed factory table names factories, never machines.

`dispatcher.factories` used to carry a `server` and a `docker_host` per entry,
which binds each factory to a MACHINE: moving one is then a commit, a release
and a plugin refresh in every governed repository, for a fact the provisioning
inventory already holds. The registry-backed form
(`_factory_registry`, Scenario 182) moves the address into host state, so an
entry names only the factory and the move is a provisioning change.

These are a LINT over whatever this repository commits, in the shape
`test_committed_routing_guard` uses: they read the real block and assert a
property of it rather than pinning a value a fixture could have supplied. The
registry-backing assertion is the durable one — it is the property that keeps a
hostname from reappearing in a tracked file, and it holds however many entries
the table grows. The two naming assertions are narrower by design and say so:
the entry NAMES are what every other committed key cross-references, so a
rename that leaves one of them behind is a configuration fault this suite
should report rather than a dispatch should discover.

The address keys are spelled literally rather than imported, because
`_factory_registry` keeps its own `_SERVER_KEY` / `_DOCKER_HOST_KEY` private
and a cross-module private import is refused by both pyright strict and the
`private_calls` check. `REGISTRY_KEY` is public and is imported, so the one key
whose SPELLING the reader branches on cannot drift away from this lint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._factory_registry import REGISTRY_KEY

_REPO_ROOT = Path(__file__).resolve().parents[1]
# The address keys a registry-backed entry may not also carry: each names an
# address the registry is the source of, so an entry declaring one has two
# answers and no rule for choosing between them.
_COMMITTED_ADDRESS_KEYS = ("server", "docker_host")


def _committed_factories() -> dict[str, Any]:
    factories: object = dispatcher_block(cwd=_REPO_ROOT)["factories"]
    assert isinstance(factories, dict), factories
    return factories


def test_the_committed_table_declares_exactly_legacy_and_petri() -> None:
    """The two live instances, each named for the instance and not its host.

    `legacy` is the hp-xubuntu :32276 instance running the pinned 0.254 engine
    and `petri` is the gmktec-xubuntu :32276 Petri-era server. Both names are
    the ones the control node's rendered registry declares, and a committed
    entry whose name the registry does not declare resolves to no address at
    all.
    """
    assert sorted(_committed_factories()) == ["legacy", "petri"]


def test_every_committed_entry_is_registry_backed_and_names_no_machine() -> None:
    """The durable invariant: no tracked file in this repository holds an address.

    Asserted over EVERY entry rather than over the two named above, so an entry
    added later cannot reintroduce a committed hostname without this failing.
    """
    for name, entry in _committed_factories().items():
        assert entry.get(REGISTRY_KEY) is True, (name, entry)
        for key in _COMMITTED_ADDRESS_KEYS:
            assert key not in entry, (name, key)


def test_the_committed_default_factory_names_a_registry_backed_entry() -> None:
    """`legacy` is the default, and it is an entry the table actually declares.

    The second half is what makes the first worth asserting: a default naming
    no declared entry refuses every dispatch from this repository, and nothing
    about the key's own value says whether it does.
    """
    default: object = dispatcher_block(cwd=_REPO_ROOT)["default_factory"]

    assert default == "legacy"
    assert default in _committed_factories()

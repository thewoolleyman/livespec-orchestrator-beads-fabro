"""Collect ended runs of closed work-items whichever repository dispatched them.

A factory is shared: a dozen repositories submit to one server, and each run is
attributed by the journal and ledger of the repository that dispatched it.  The
host timer starts the pass from ONE repository, so the pass's own attribution
reaches only that repository's runs, and every other repository collected only
inside its own dispatch or resume reconcile -- one that never dispatched on the
timer's host collected nothing at all.  This module widens the periodic pass to
every repository the host's plugin install registry names, so one pass per
dispatching host suffices and a repository's runs never depend on a pass of that
repository's own.

THE COLLECTION ITSELF IS NOT REPEATED HERE.  Each other repository's inventory is
rebuilt from that repository's own recorded facts -- its journal's launch stamps,
its ledger's run stamps and its ledger's item statuses -- and handed to the same
`collect_closed_ended_runs` the pass's own repository goes through, with `repo`
naming the dispatching repository so its preservation refs are deleted from ITS
origin.  The deletion pacing, the unforced provider delete and the retry rule are
therefore the one mechanism, not a copy.

A RUN IS COLLECTED THROUGH THE FIRST REPOSITORY THAT ATTRIBUTES IT.  The pass's
own repository attributes first, so a run it already collects or refuses is never
journaled a second time; each further repository sees only the runs no earlier one
claimed.  A run no repository attributes -- the factory's clearance and
availability-probe runs -- is claimed by none and is left in place unjournaled.

AN UNREADABLE LEDGER IS NOT AN EMPTY ONE.  A repository whose ledger cannot be read
contributes an EMPTY status mapping, which reads every run it attributes as having
no status, so those runs are refused and left in place; reading the failure as
"nothing is open" is the one direction that would delete a sandbox a human may
still need.  A registered repository carrying no `.livespec.jsonc` dispatches
nothing and is passed over.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_collection import (
    collect_closed_ended_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    plugin_install_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    FactoryRunInventory,
    JournaledRuns,
    attributed_runs,
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_stamp import (
    repo_run_attribution,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DispatchingRepository",
    "collect_fleet_closed_ended_runs",
    "read_dispatching_repository",
    "registered_dispatching_repositories",
]

_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")
_CONFIG_NAME = ".livespec.jsonc"

# What reading another repository's ledger absorbs rather than propagates: every
# entry is an EXPECTED failure of a surface this pass merely reads.  A bug still
# raises.
_LEDGER_UNREADABLE: tuple[type[Exception], ...] = (
    OSError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)


@dataclass(frozen=True, kw_only=True)
class DispatchingRepository:
    """One repository that dispatches to the factory, as its own records read.

    `item_statuses` is EMPTY when the repository's ledger could not be read, which
    reads every item as having no status rather than as closed.
    """

    repo: Path
    id_prefix: str
    item_statuses: Mapping[str, str]
    journaled: JournaledRuns
    attribution: RunAttribution


def registered_dispatching_repositories(
    *, own_repo: Path, install_record: Path
) -> tuple[Path, ...]:
    """Every OTHER repository this host's plugin install registry names, once each."""
    seen = {own_repo.resolve()}
    repositories: list[Path] = []
    for record in plugin_install_records(install_record=install_record):
        path = record.project_path.resolve()
        if path in seen or not path.is_dir():
            continue
        seen.add(path)
        repositories.append(path)
    return tuple(repositories)


def read_dispatching_repository(*, repo: Path) -> DispatchingRepository | None:
    """One repository's own records, or None for one that dispatches nothing."""
    if not (repo / _CONFIG_NAME).is_file():
        return None
    prefix, statuses = _ledger_reading(repo=repo)
    return DispatchingRepository(
        repo=repo,
        id_prefix=prefix,
        item_statuses=statuses,
        journaled=read_journaled_runs(path=repo.joinpath(*_JOURNAL_SUBPATH)),
        attribution=repo_run_attribution(repo=repo),
    )


def collect_fleet_closed_ended_runs(
    *,
    inventory: FactoryRunInventory,
    port: FabroPort,
    runner: CommandRunner,
    journal: JournalWriter,
    dry_run: bool,
    repositories: Sequence[DispatchingRepository],
) -> None:
    """Collect every other repository's ended runs of closed items on one factory.

    A dry run and a targeted pass collect nothing here: the first writes nothing,
    and the second is asked about one item of the pass's own repository.
    """
    if dry_run or inventory.only_work_item_id is not None:
        return
    claimed = _attributed_run_ids(inventory=inventory)
    for dispatching in repositories:
        runs = tuple(run for run in inventory.runs if run.run_id not in claimed)
        if not runs:
            return
        scoped = replace(
            inventory,
            runs=runs,
            item_statuses=dispatching.item_statuses,
            journaled=dispatching.journaled,
            id_prefix=dispatching.id_prefix,
            attribution=dispatching.attribution,
        )
        claimed |= _attributed_run_ids(inventory=scoped)
        collect_closed_ended_runs(
            inventory=scoped,
            port=port,
            runner=runner,
            repo=dispatching.repo,
            journal=journal,
            dry_run=False,
        )


def _attributed_run_ids(*, inventory: FactoryRunInventory) -> set[str]:
    return {row.run.run_id for row in attributed_runs(inventory=inventory, include_terminal=True)}


def _ledger_reading(*, repo: Path) -> tuple[str, dict[str, str]]:
    config = _store_config(repo=repo)
    if config is None:
        return "", {}
    try:
        return config.prefix, {item.id: item.status for item in load_items(repo=repo)}
    except _LEDGER_UNREADABLE:
        return config.prefix, {}


def _store_config(*, repo: Path) -> StoreConfig | None:
    try:
        return store_config(repo=repo)
    except _LEDGER_UNREADABLE:
        return None

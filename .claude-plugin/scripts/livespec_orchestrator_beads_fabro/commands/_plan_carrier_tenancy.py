"""Which repository a plan carrier's id names, read off each tenant's own prefix.

A carrier-map scope event names carriers by WORK-ITEM ID and nothing else, while
the shared authoritative result reader resolves a target by REPOSITORY IDENTITY —
so a reader that wants one carrier's status has to bridge the two. Every tenant
of this family stamps its own short create-prefix onto every id it mints
(`StoreConfig.prefix`, decoupled from the tenant database name), so the prefix a
carrier id opens with is the one thing in the id that names where the carrier
lives: `livespec-driver-codex-extptf` is the codex driver's tenant, `ob-5qlusq`
is openbrain's, `bd-ib-evrynu` is this repository's.

WHY THE PREFIXES ARE READ AND NEVER TABULATED. A table of prefix-to-repository
pairs would be a second account of a value every sibling already declares in its
own `.livespec.jsonc`, and the two would drift silently: a sibling that changed
its create-prefix, or a new sibling added to `cross_repo_targets`, would keep
resolving to whatever the table said. So the tenancy is built by RESOLVING each
configured repository and asking its own configuration what prefix it creates.

WHY THE LONGEST PREFIX WINS. The prefixes are not disjoint by construction —
`livespec-driver-codex` and `livespec-driver-pi` share four segments, and a
shorter prefix can be a prefix of a longer one — so a first-match scan over an
arbitrary order would attribute a sibling's carrier to whichever repository the
manifest happened to list first. Ordering by prefix length makes the match the
most specific one available, which is the only answer that cannot be wrong for a
carrier whose own tenant is configured.

WHY AN UNRESOLVABLE REPOSITORY IS SIMPLY ABSENT. A sibling configured but never
cloned on this host, and a sibling whose clone declares no tenant connection, are
both repositories the result reader cannot read — the clause puts "missing
repository-resolution failures" in the `unobservable` set — so neither belongs in
a tenancy whose whole purpose is to name a repository a read can be aimed at. A
carrier whose prefix matches none of them is reported as naming no repository,
which the caller turns into its own finding rather than into a read it cannot
take.

WHY THE PROJECT'S OWN IDENTITY COMES FROM `project_repository_identity`. That is
the identity this project NAMES its own repository by when it writes a pointer,
and a carrier obligation derived from this tenancy is exactly such a pointer: an
identity chosen any other way resolves in this checkout and stops resolving the
moment another checkout of the same repository reads the record it landed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._cross_repo import load_manifest
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    ResultRepository,
    project_repository_identity,
    resolve_result_repository,
    result_store_config,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CarrierTenancy",
    "carrier_tenancy",
    "repository_for_carrier",
]


@dataclass(frozen=True, kw_only=True)
class CarrierTenancy:
    """Every resolvable repository, keyed by the id prefix its tenant creates.

    `project_root` rides along because it is resolved by the SAME reading that
    builds the index and every caller needs both: the index says which repository
    a carrier lives in, and the root is what the shared result reader resolves
    that repository's name against. A caller deriving the root for itself would
    be a second resolution of one value, and the two can only be shown to agree
    by comparing them.

    `by_prefix` is ordered LONGEST PREFIX FIRST, which is what makes a
    first-match scan the most-specific match. Nothing re-sorts it.
    """

    project_root: Path
    by_prefix: tuple[tuple[str, ResultRepository], ...]


def carrier_tenancy(*, config: StoreConfig) -> CarrierTenancy:
    """Resolve every configured repository and index it by its own id prefix."""
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    names = (
        project_repository_identity(config=config),
        *sorted(load_manifest(project_root=project_root).targets),
    )
    indexed: list[tuple[str, ResultRepository]] = []
    claimed: set[str] = set()
    for name in names:
        prefixed = _prefixed(project_root=project_root, name=name)
        if prefixed is None or prefixed[0] in claimed:
            continue
        claimed.add(prefixed[0])
        indexed.append(prefixed)
    return CarrierTenancy(
        project_root=project_root,
        by_prefix=tuple(sorted(indexed, key=lambda one: len(one[0]), reverse=True)),
    )


def repository_for_carrier(*, tenancy: CarrierTenancy, carrier_id: str) -> ResultRepository | None:
    """The repository one carrier id names, or `None` when none is configured.

    The separator is required as well as the prefix, so a tenant whose prefix is
    `li` cannot claim an id minted by a tenant whose prefix is `livespec`: both
    ids open with `li`, and only one of them opens with `li-`.
    """
    for prefix, repository in tenancy.by_prefix:
        if carrier_id.startswith(f"{prefix}-"):
            return repository
    return None


def _prefixed(*, project_root: Path, name: str) -> tuple[str, ResultRepository] | None:
    """One configured repository with the prefix its own tenant creates.

    `None` covers both ways a configured name is unusable here, deliberately
    together: a repository that does not resolve to a clone on this host, and one
    whose clone resolves no tenant connection. Neither can answer a read, so
    neither is a repository a carrier could be observed in, and distinguishing
    them would be distinguishing two diagnostics this reader never renders — the
    caller reports the carrier it could not place, not the configuration behind
    it.

    The FIRST name claiming a prefix keeps it, which is what makes this
    project's own identity win over a sibling that happens to declare the same
    prefix: a carrier id this project could have minted is read from the tenant
    that mints them, not from a sibling misconfigured to share it.
    """
    repository = resolve_result_repository(project_root=project_root, name=name)
    if repository is None:
        return None
    resolved = result_store_config(repository=repository)
    if resolved is None or resolved.prefix == "":
        return None
    return (resolved.prefix, repository)

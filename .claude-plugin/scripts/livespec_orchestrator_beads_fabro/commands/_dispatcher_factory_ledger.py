"""Dispatcher factory ledger pinning."""

from __future__ import annotations

import argparse
import os
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.store import (
    dispatch_factory_for,
    record_dispatch_factory,
)

__all__: list[str] = [
    "args_with_dispatch_factory_target",
    "resolve_dispatch_factory_target",
    "selected_dispatch_factory_target",
]

_ENV_FABRO_FACTORY = "LIVESPEC_FABRO_FACTORY"


def resolve_dispatch_factory_target(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> FactoryTarget:
    """Resolve and persist the Fabro factory target for one dispatch."""
    target = selected_dispatch_factory_target(
        args=args,
        repo=repo,
        work_item_id=work_item_id,
    )
    config = store_config(repo=repo)
    record_dispatch_factory(path=config, work_item_id=work_item_id, factory=target.name)
    return target


def selected_dispatch_factory_target(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> FactoryTarget:
    """Resolve one dispatch's selected target without mutating its ledger row."""
    config = store_config(repo=repo)
    explicit = _explicit_factory(args=args)
    recorded = dispatch_factory_for(path=config, work_item_id=work_item_id)
    factory = explicit or _usable_recorded_factory(repo=repo, recorded=recorded)
    return resolve_fabro_factory(cwd=repo, factory=factory)


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

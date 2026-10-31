"""Report whether a governed project's registered plugin install lags release."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    default_plugin_install_registry,
    registered_plugin_root,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_core_roots import version_key
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    default_release_adoption_bases,
    read_build_version,
    release_tip_version,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["main", "registered_plugin_currency_warning"]

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"


def registered_plugin_currency_warning(
    *, repo: Path, install_record: Path, marketplace_record: Path
) -> str | None:
    """Return the non-blocking warning when ``repo`` resolves an older release."""
    root = registered_plugin_root(repo=repo, install_record=install_record)
    registered = None if root is None else read_build_version(install_path=root)
    latest = release_tip_version(
        marketplace_record=marketplace_record,
        plugin_name=_PLUGIN_NAME,
    )
    if (
        registered is None
        or latest is None
        or version_key(name=registered) >= version_key(name=latest)
    ):
        return None
    return f"WARNING: registered build {registered} lags latest released version {latest}"


def main(*, argv: Sequence[str] | None = None) -> int:
    """Print any registered-install currency warning for ``--repo``."""
    parser = argparse.ArgumentParser(prog="registered_plugin_currency")
    _ = parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args(argv)
    bases = default_release_adoption_bases()
    warning = registered_plugin_currency_warning(
        repo=args.repo,
        install_record=default_plugin_install_registry(),
        marketplace_record=bases.marketplace_record,
    )
    if warning:
        _ = write_stdout(text=warning + "\n")
    return 0

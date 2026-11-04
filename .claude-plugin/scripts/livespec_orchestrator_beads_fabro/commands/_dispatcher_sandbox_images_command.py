"""The read-only `sandbox-images` subcommand: which repositories, and what it prints.

The operator surface over `_dispatcher_sandbox_images` (which resolves ONE
repository's entries) and `_dispatcher_sandbox_image_builds` (which answers which
builds are executing). What is decided HERE is the scope and the reporting: which
repositories are enumerated, which build each one's registered install names, the
one JSON array, and the exit code.

IT CHANGES NOTHING, which is the clause's own first requirement and holds
structurally rather than carefully: this module writes nothing but stdout, the
two readers it composes make no write call, and it reaches neither the ledger,
the dispatch journal nor a factory. There is no write, no claim and no run to
suppress.

AN UNREADABLE SOURCE EARNS A NON-ZERO EXIT AND LOSES NO OTHER ENTRY. The two
halves are one requirement: a survey that stopped at the first unreadable
repository would report a partial enumeration as a complete one, and a survey
that reported every entry and exited zero would hand a warm timer a tag list
with a silent hole in it. So the whole array is printed and the exit code is the
only thing the unreadable entry moves.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_install_registry import (
    PluginInstallRecord,
    default_plugin_install_registry,
    plugin_install_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_builds import (
    default_build_discovery_roots,
    executing_builds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import (
    UNREADABLE_SOURCE,
    SandboxImageEntry,
    sandbox_images,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "add_sandbox_images_arguments",
    "run_sandbox_images_command",
]

# An unreadable source is a finding rather than a usage error, so it rides the
# ordinary findings code this repository's other read-only check subcommands use.
_EXIT_UNREADABLE_SOURCE = 1

_EMPTY_REPORT_LINE = "(no sandbox-image entries)\n"


def add_sandbox_images_arguments(*, parser: argparse.ArgumentParser) -> None:
    """The subcommand's flag surface: the factory it reports on, and its scope."""
    _ = parser.add_argument("--factory", dest="factory", required=True)
    _ = parser.add_argument("--repo", dest="repos", action="append", default=None)
    _ = parser.add_argument("--json", dest="as_json", action="store_true")


def run_sandbox_images_command(*, args: argparse.Namespace) -> int:
    """Enumerate and print every sandbox-image source, changing nothing."""
    records = plugin_install_records(install_record=default_plugin_install_registry())
    repositories = _repositories(args=args, records=records)
    builds = executing_builds(
        install_paths=_registered_builds(records=records),
        roots=default_build_discovery_roots(),
    )
    entries = tuple(
        entry
        for repository in repositories
        for entry in sandbox_images(factory=args.factory, repo=repository, builds=builds)
    )
    _emit(entries=entries, as_json=args.as_json)
    unreadable = any(entry.source == UNREADABLE_SOURCE for entry in entries)
    return _EXIT_UNREADABLE_SOURCE if unreadable else 0


def _repositories(
    *, args: argparse.Namespace, records: tuple[PluginInstallRecord, ...]
) -> tuple[Path, ...]:
    """The enumerated repositories: the named ones, else this plugin's registrations.

    `--repo` REPLACES registry discovery rather than adding to it, which is what
    makes the flag usable as a scope: a consumer asking about one repository must
    not be handed every other repository on the host as well.
    """
    named: list[str] | None = args.repos
    if named is not None:
        return tuple(Path(repository) for repository in named)
    return tuple(record.project_path for record in records)


def _registered_builds(*, records: tuple[PluginInstallRecord, ...]) -> tuple[Path, ...]:
    """Every host-registered build, whether or not `--repo` selected its project.

    Repository selection changes only the repositories whose resolutions are
    printed. A dispatch to any selected repository can execute from any build a
    host registration currently reaches, so narrowing this route to matching
    projects would hide bundled configs that remain resolvable now.
    """
    return tuple(record.install_path for record in records)


def _emit(*, entries: tuple[SandboxImageEntry, ...], as_json: bool) -> None:
    if as_json:
        payload = [entry.record() for entry in entries]
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not entries:
        _ = write_stdout(text=_EMPTY_REPORT_LINE)
        return
    for entry in entries:
        _ = write_stdout(text=_human_line(entry=entry))


def _human_line(*, entry: SandboxImageEntry) -> str:
    """One entry as a line: its source, its repository, then whatever it evidenced.

    Absent fields are OMITTED rather than rendered as a placeholder, because
    each one is the evidence of its own arm and a line padded with empty
    columns reads as a resolution that produced nothing.
    """
    detail = "  ".join(
        f"{label}={value}"
        for label, value in (
            ("environment", entry.environment_id),
            ("image", entry.image),
            ("build", entry.build),
            ("variant", entry.variant),
            ("path", None if entry.path is None else str(entry.path)),
        )
        if value is not None
    )
    return f"{entry.source}  {entry.repository}  {detail}\n"

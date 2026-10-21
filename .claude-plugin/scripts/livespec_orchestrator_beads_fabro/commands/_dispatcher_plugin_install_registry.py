"""WHICH repositories this plugin is installed for, and at which build.

The host's Claude Code install registry (`~/.claude/plugins/installed_plugins.json`)
is the only record of the repositories this plugin governs on a host, so it is
what a host-wide read-only survey enumerates when it is given no explicit
repository. Each record pairs the governed project root (`projectPath`) with the
cache build the registry resolves for it (`installPath`).

ONE READER FOR BOTH CONSUMERS. `_dispatcher_registered_install_currency` asks
this registry a narrower question — which build does THIS repository resolve —
and consulted it through a private copy of the same traversal. That copy is now
this module's single public read, because the two questions are answered from
one file and a second traversal of it is a second set of tolerances that can
drift: a shape one side drops and the other keeps makes the currency finding and
the enumeration disagree about which repositories exist, with nothing announcing
it.

EVERY MALFORMED SHAPE IS DROPPED RATHER THAN REFUSED, which is the posture a
registry read has to take: the file is written by the harness and not by this
fleet, so a record carrying a shape this reader does not expect is a harness
version this build has not seen, not an operator error anybody here can fix. A
refusal would retire both consumers over one unfamiliar row.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "PluginInstallRecord",
    "default_plugin_install_registry",
    "plugin_install_records",
]

# The plugin whose records are read -- this one, wherever the dispatcher happens
# to run. Never read from a governed repository's own manifest, which names that
# repository rather than this plugin.
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"

# The registry keys records under `<plugin>@<marketplace>`, so the plugin is
# matched on the part BEFORE the separator: the same plugin installed from two
# marketplaces carries two keys, and both are this plugin's.
_MARKETPLACE_SEPARATOR = "@"

_PLUGINS_KEY = "plugins"
_PROJECT_PATH_KEY = "projectPath"
_INSTALL_PATH_KEY = "installPath"


@dataclass(frozen=True, kw_only=True)
class PluginInstallRecord:
    """ONE install record: the governed project root, and the build it resolves."""

    project_path: Path
    install_path: Path


def default_plugin_install_registry() -> Path:  # pragma: no cover
    """The production registry under the real HOME (integration-covered)."""
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def plugin_install_records(*, install_record: Path) -> tuple[PluginInstallRecord, ...]:
    """Every usable install record of THIS plugin, in registry order."""
    plugins = _parsed_object(path=install_record).get(_PLUGINS_KEY)
    if not isinstance(plugins, dict):
        return ()
    records: list[PluginInstallRecord] = []
    for key, entries in cast("dict[str, Any]", plugins).items():
        if _names_this_plugin(key=key) and isinstance(entries, list):
            records.extend(_records_of(entries=cast("list[Any]", entries)))
    return tuple(records)


def _names_this_plugin(*, key: str) -> bool:
    return key.split(_MARKETPLACE_SEPARATOR, maxsplit=1)[0] == _PLUGIN_NAME


def _records_of(*, entries: list[Any]) -> Iterator[PluginInstallRecord]:
    for entry in entries:
        record = _record_of(entry=entry)
        if record is not None:
            yield record


def _record_of(*, entry: object) -> PluginInstallRecord | None:
    if not isinstance(entry, dict):
        return None
    fields = cast("dict[str, Any]", entry)
    project_path = fields.get(_PROJECT_PATH_KEY)
    install_path = fields.get(_INSTALL_PATH_KEY)
    if not isinstance(project_path, str) or not isinstance(install_path, str):
        return None
    if project_path == "" or install_path == "":
        return None
    return PluginInstallRecord(project_path=Path(project_path), install_path=Path(install_path))


def _parsed_object(*, path: Path) -> dict[str, Any]:
    """The JSON object at `path`, or an empty mapping for any read or parse failure."""
    if not path.is_file():
        return {}
    text = attempt(
        action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError, ValueError)
    )
    if isinstance(text, AttemptFailure):
        return {}
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return {}
    return cast("dict[str, Any]", parsed)

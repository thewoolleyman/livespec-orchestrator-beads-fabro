# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""_fork_only_settings — the settings keys a graph's copy loses before validation.

`fabro_graph_validity` validates every graph in a scratch copy of its payload,
and CI pins the UPSTREAM fabro 0.254.0 release to do it. That release cannot parse
this repository's `workflow.toml`: `run.checkpoint.commit_timeout` is a key only
the factory's FORK build reads (fork PR #552, which upstream carries only from
v0.289, past the 0.254 ceiling). Upstream then drops the whole settings file and
renders every `inputs.*` default empty, so it refuses even a valid graph. With
that one key removed its verdicts match the fork build's.

THE LIST IS EXACT, NEVER A PATTERN. A key missing from `FORK_ONLY_SETTINGS`
leaves the upstream engine refusing the settings file, which fails the gate
LOUDLY; it can never make an invalid graph pass. `settings_failures` is the
control that the removal took nothing else: it re-parses both texts and requires
the copy to equal the original minus the named keys, and an unparseable settings
file is itself a finding.

Imported only by `fabro_graph_validity`, whose path setup puts the shared
dev-tooling package's vendored `tomli` on `sys.path` first; this repository's
3.10 floor predates `tomllib`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

import tomli

__all__: list[str] = [
    "FORK_ONLY_SETTINGS",
    "SETTINGS_NAME",
    "Normalized",
    "normalized_settings",
    "settings_failures",
]

SETTINGS_NAME = "workflow.toml"

# Settings keys the fork build reads and the pinned upstream release rejects as
# unknown, as `(table, key)`.
FORK_ONLY_SETTINGS: tuple[tuple[str, str], ...] = (("run.checkpoint", "commit_timeout"),)

# A `[table]` header and a bare `key =` line. A header this does not recognise
# leaves the current table in force; `settings_failures` then catches any key
# stripped under the wrong table, because the copy would differ by more than it.
_TABLE_RE = re.compile(r"^[ \t]*\[(?P<table>[^\[\]]+)\][ \t]*(?:#.*)?$")
_KEY_RE = re.compile(r"^[ \t]*(?P<key>[A-Za-z0-9_-]+)[ \t]*=")


@dataclass(frozen=True, kw_only=True)
class Normalized:
    """A settings text with the fork-only keys removed, and the dotted keys that were."""

    text: str
    stripped: list[str]


def normalized_settings(*, text: str) -> Normalized:
    """`text` with every `FORK_ONLY_SETTINGS` key line removed, tracking the table in force."""
    kept: list[str] = []
    stripped: list[str] = []
    table = ""
    for line in text.splitlines(keepends=True):
        header = _TABLE_RE.match(line)
        table = table if header is None else header.group("table").strip()
        key = _KEY_RE.match(line)
        if key is not None and (table, key.group("key")) in FORK_ONLY_SETTINGS:
            stripped.append(f"{table}.{key.group('key')}")
            continue
        kept.append(line)
    return Normalized(text="".join(kept), stripped=stripped)


def settings_failures(*, where: str, original: str, normalized: Normalized) -> list[str]:
    """Why the normalized copy cannot stand in for the committed settings file."""
    try:
        before = tomli.loads(original)
        after = tomli.loads(normalized.text)
    except tomli.TOMLDecodeError as error:
        return [f"settings control: {where}: {SETTINGS_NAME} is not parseable TOML ({error})"]
    expected = before
    for dotted in normalized.stripped:
        expected = _without(table=expected, dotted=dotted)
    drift = f"normalizing {SETTINGS_NAME} changed more than {', '.join(normalized.stripped)}"
    return [] if expected == after else [f"settings control: {where}: {drift}"]


def _without(*, table: dict[str, object], dotted: str) -> dict[str, object]:
    """`table` with the one key `dotted` names removed, nested tables copied, never mutated."""
    head, _, rest = dotted.partition(".")
    if rest == "":
        return {key: value for key, value in table.items() if key != head}
    inner = cast("dict[str, object]", table[head])
    return {**table, head: _without(table=inner, dotted=rest)}

"""The committed-only `dispatcher.idle_slot_audit` object, read and graded.

The idle-slot clause among the orchestrator-owned attention facts in
`SPECIFICATION/contracts.md` gives this object THREE outcomes, and keeping them
three is the whole job of this module. An ABSENT object means the audit is not
configured, which is an answer rather than a fault: a repository that declares
no priority set has nothing to audit and composes no fact. A MALFORMED object
is a refusal that must NAME the offending key, because the alternative — a
tolerant read that drops the unreadable half — would report a partial priority
set as the whole one, which reads exactly like a healthy audit over fewer
tenants. A WELL-FORMED object is the parsed value.

So the return type is `IdleSlotAuditConfig | str | None`, the same
answer-or-finding shape `resolve_node_timeouts` uses: `None` for absent, a
finding string for malformed, the value otherwise. There is deliberately no
partially-parsed variant.

The object carries NO concurrency or slot value, and this module refuses to
invent one: the clause reads no ceiling and derives no available capacity, per
`SPECIFICATION/contracts.md` section "Host concurrency belongs to the Fabro
scheduler". `factory` is validated against `dispatcher.factories` HERE rather
than at the board read, because a factory name that names no declared entry
would otherwise reach `FactoryRunReader` and come back as an unobservable
board — a configuration error reported as a factory outage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    has_fabro_factory,
)

__all__: list[str] = [
    "IDLE_SLOT_AUDIT_KEY",
    "IdleSlotAuditConfig",
    "PriorityEntry",
    "priority_entry_root",
    "resolve_idle_slot_audit",
]

IDLE_SLOT_AUDIT_KEY = "idle_slot_audit"
_CONFIG_PREFIX = f"dispatcher.{IDLE_SLOT_AUDIT_KEY}"


@dataclass(frozen=True, kw_only=True)
class PriorityEntry:
    """One priority set: a tenant checkout plus EITHER an epic or named items.

    The two subject forms are exclusive by construction — `epic` is non-None
        exactly when `items` is empty — because the `items` form exists for a
    priority epic whose children live in a different tenant from the epic, and
    an entry carrying both would leave the audit to pick one silently.
    """

    repo: str
    epic: str | None
    items: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class IdleSlotAuditConfig:
    """The whole configured audit: one factory and the priority sets, in order.

    `priority` preserves CONFIGURATION ORDER, which is load-bearing: the
    finding line names its child ids in configuration order, so re-sorting
    here would put a second ordering authority behind that line.
    """

    factory: str
    priority: tuple[PriorityEntry, ...]


def resolve_idle_slot_audit(*, cwd: Path) -> IdleSlotAuditConfig | str | None:
    """Read the committed audit object: value, finding, or `None` when absent."""
    block = dispatcher_block(cwd=cwd)
    raw = block.get(IDLE_SLOT_AUDIT_KEY)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return _finding(key=_CONFIG_PREFIX, detail="is not an object")
    mapping = cast("dict[str, Any]", raw)
    factory = _factory_name(cwd=cwd, mapping=mapping)
    if not isinstance(factory, str):
        return factory.detail
    priority = _priority_entries(mapping=mapping)
    if isinstance(priority, _Finding):
        return priority.detail
    return IdleSlotAuditConfig(factory=factory, priority=priority)


def priority_entry_root(*, project_root: Path, entry: PriorityEntry) -> Path:
    """Resolve one entry's `repo` against this repository's root.

    The clause states the path is "resolved relative to this repository's
    root", so a relative value is joined to `project_root`; an absolute value
    is taken as given, which is what the fleet's own `/data/projects` layout
    writes.
    """
    candidate = Path(entry.repo)
    return candidate if candidate.is_absolute() else project_root / candidate


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """A configuration refusal naming the offending key."""

    detail: str


def _factory_name(*, cwd: Path, mapping: dict[str, Any]) -> str | _Finding:
    factory = mapping.get("factory")
    key = f"{_CONFIG_PREFIX}.factory"
    if not isinstance(factory, str) or factory == "":
        return _Finding(detail=_finding(key=key, detail="is not a non-empty string"))
    if not has_fabro_factory(cwd=cwd, factory=factory):
        return _Finding(
            detail=_finding(key=key, detail=f"names no dispatcher.factories entry: {factory!r}")
        )
    return factory


def _priority_entries(*, mapping: dict[str, Any]) -> tuple[PriorityEntry, ...] | _Finding:
    raw = mapping.get("priority")
    key = f"{_CONFIG_PREFIX}.priority"
    if not isinstance(raw, list) or not raw:
        return _Finding(detail=_finding(key=key, detail="is not a non-empty array"))
    entries: list[PriorityEntry] = []
    for position, entry in enumerate(cast("list[object]", raw)):
        parsed = _priority_entry(entry=entry, position=position)
        if isinstance(parsed, _Finding):
            return parsed
        entries.append(parsed)
    return tuple(entries)


def _priority_entry(*, entry: object, position: int) -> PriorityEntry | _Finding:
    key = f"{_CONFIG_PREFIX}.priority[{position}]"
    if not isinstance(entry, dict):
        return _Finding(detail=_finding(key=key, detail="is not an object"))
    mapping = cast("dict[str, Any]", entry)
    repo = mapping.get("repo")
    if not isinstance(repo, str) or repo == "":
        return _Finding(detail=_finding(key=f"{key}.repo", detail="is not a non-empty string"))
    return _priority_subject(mapping=mapping, key=key, repo=repo)


def _priority_subject(*, mapping: dict[str, Any], key: str, repo: str) -> PriorityEntry | _Finding:
    epic = mapping.get("epic")
    items_raw = mapping.get("items")
    if epic is not None and items_raw is not None:
        return _Finding(detail=_finding(key=key, detail="carries both epic and items"))
    if epic is not None:
        if not isinstance(epic, str) or epic == "":
            return _Finding(detail=_finding(key=f"{key}.epic", detail="is not a non-empty string"))
        return PriorityEntry(repo=repo, epic=epic, items=())
    items = _item_ids(raw=items_raw)
    if items is None:
        return _Finding(
            detail=_finding(key=f"{key}.items", detail="is not a non-empty array of work-item ids")
        )
    return PriorityEntry(repo=repo, epic=None, items=items)


def _item_ids(*, raw: object) -> tuple[str, ...] | None:
    if not isinstance(raw, list) or not raw:
        return None
    values = cast("list[object]", raw)
    if any(not isinstance(value, str) or value == "" for value in values):
        return None
    return tuple(cast("list[str]", values))


def _finding(*, key: str, detail: str) -> str:
    return f"configuration finding: {key} {detail}"

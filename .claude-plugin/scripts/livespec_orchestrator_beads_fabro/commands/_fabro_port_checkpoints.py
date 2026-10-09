"""The checkpoint sequence on one Fabro run record, as the engine writes it.

This is ONE reading of the engine's record shape, and it is its own module
because it belongs to neither of the two questions that ask it. `_fabro_escalation`
reads `next_node_id` plus `loop_failure_signatures` off these checkpoints to tell
an engine-routed escalation from a human gate; `_dispatcher_resume_run_record`
reads `next_node_id` alone to learn which node a terminated run was executing.
Two copies of this walk is how those two would come to disagree about which
checkpoint is newest -- and the newest one is precisely what both of them take.

It is a leaf: it imports no other port module, because the only thing it needs is
the already-normalized record mapping its callers hand it.
"""

from __future__ import annotations

from typing import Any, cast

__all__: list[str] = [
    "fabro_inspect_checkpoints",
]


def fabro_inspect_checkpoints(*, record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Every checkpoint mapping on one run record, oldest first.

    `checkpoints[]` entries wrap their state under a nested `checkpoint` key
    (the shape the measured run carries), so the nested mapping is appended
    AFTER its wrapper and therefore wins for the same index. The record's own
    top-level `checkpoint` is appended last as the newest state of all.
    """
    found: list[dict[str, Any]] = []
    entries_raw: object = record.get("checkpoints")
    if isinstance(entries_raw, list):
        for entry in cast("list[object]", entries_raw):
            if not isinstance(entry, dict):
                continue
            typed = cast("dict[str, Any]", entry)
            found.append(typed)
            nested: object = typed.get("checkpoint")
            if isinstance(nested, dict):
                found.append(cast("dict[str, Any]", nested))
    top_level: object = record.get("checkpoint")
    if isinstance(top_level, dict):
        found.append(cast("dict[str, Any]", top_level))
    return tuple(found)

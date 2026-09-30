"""The ONE reader of a per-repository catalog table, shared by both catalogs.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" grants the same
permission twice -- "A repository MAY add or override agent entries under
`dispatcher.agent_catalog`" and "A repository MAY add or override entries under
`dispatcher.model_catalog`" -- with the same closed grammar and the same
before-claim refusal. The SHAPE of that table is identical in both cases: a
table of catalog key to entry table. Only what an ENTRY means differs.

So the shape question is asked here once. Two copies of it is how the two
catalogs would come to disagree about whether a non-table entry refuses or is
skipped, and the answer has to be "refuses": a skipped entry leaves the shipped
snapshot standing while the operator reads their override as applied.

AN ABSENT KEY IS NOT A FAULT. A repository that configures no additions is the
overwhelmingly common case and the contract's default, so an absent table
resolves to the empty mapping rather than to a refusal. A PRESENT table of the
wrong type is the operator's configuration being wrong, which is a different
claim and gets a different answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

__all__: list[str] = [
    "catalog_overrides",
]


def catalog_overrides(
    *, block: Mapping[str, Any], config_key: str
) -> Mapping[str, Mapping[str, Any]] | str:
    """The per-repository entries under `dispatcher.<config_key>`, or refuse.

    Keys are returned in SORTED order so a table with two faults always
    refuses on the same one, which is what makes a refusal message
    reproducible across dispatches rather than a function of dict insertion.

    A blank catalog key is refused rather than normalized away: it is not an
    agent id and it is not a `provider/model` pair, and accepting it would put
    an unnameable entry into a catalog whose whole job is lookup by name.
    """
    qualified = f"dispatcher.{config_key}"
    raw = block.get(config_key)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        return f"{qualified} must be a table of catalog key to entry table; got {raw!r}"
    table = cast("dict[str, Any]", raw)
    entries: dict[str, Mapping[str, Any]] = {}
    for key in sorted(table):
        if key.strip() == "":
            return f"{qualified} carries a blank catalog key; every entry is keyed by name"
        entry = table[key]
        if not isinstance(entry, dict):
            return f"{qualified}.{key} must be an entry table; got {entry!r}"
        entries[key] = cast("dict[str, Any]", entry)
    return entries

"""Per-repository product-`.py` classification for the factory-bypass audit.

The audit's question — "did this merged PR change PRODUCT code?" — has a
DIFFERENT answer in every fleet repository, because every repository declares
its own first-party source layout. `livespec-dev-tooling` is a flat-layout
library rooted at `livespec_dev_tooling/`; `livespec` roots at
`.claude-plugin/scripts/livespec/`; this orchestrator roots at
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/`. A single hardcoded
tuple can only ever be right for ONE of them, and it is wrong SILENTLY: an
unrecognised layout classifies every changed path as non-product, so the audit
reports zero bypasses for a repository it cannot see into at all.

So the prefix set is DERIVED per repository, from the audited repository's own
`[tool.livespec_dev_tooling]` declaration in its `pyproject.toml` — the same
two keys the fleet's shared `config.derive_source_prefixes` unions
(`source_trees` and `source_tree_prefixes`), normalised to trailing-slash
prefixes and de-duplicated preserving first-seen order. This module holds a
local reader rather than importing that helper because the plugin has NO
runtime dependency on the dev-tooling package, and because the audit reads a
REMOTE repository's declaration over `gh`, where no local checkout exists.

THE FAIL-OPEN THIS MODULE REFUSES TO HAVE: `str.startswith(())` is False for
every input, so an empty prefix set makes the audit exit 0 with "no bypasses"
however much product code went around the factory. `product_policy` therefore
NEVER returns an empty set — an unreadable or undeclaring repository falls back
to `FLEET_FALLBACK_PRODUCT_PREFIXES`, and the `origin` field records which arm
answered so the rendered report states how the instrument was aimed rather than
leaving the reader to assume it was aimed at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

__all__: list[str] = [
    "FLEET_FALLBACK_PRODUCT_PREFIXES",
    "PolicyOrigin",
    "ProductPathPolicy",
    "derive_product_prefixes",
    "is_product_py",
    "product_policy",
]

# The dev-tooling declaration table, and the two keys inside it whose UNION is
# the repository's first-party source universe.
_DECLARATION_TABLE = "[tool.livespec_dev_tooling]"
_PREFIX_KEYS = ("source_trees", "source_tree_prefixes")

# The last-resort prefix set for a repository that declares neither key (or
# whose declaration could not be read). Deliberately BROAD: over-classifying a
# path costs a reviewable false finding, while under-classifying costs a silent
# miss, and this is a report-only attention surface.
FLEET_FALLBACK_PRODUCT_PREFIXES = (
    ".claude-plugin/scripts/",
    ".claude-plugin/hooks/",
    ".claude/hooks/",
    "dev-tooling/",
)

PolicyOrigin = Literal["declared", "fleet-fallback", "operator-override"]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductPathPolicy:
    """Which path prefixes count as product code, and how that set was resolved."""

    prefixes: tuple[str, ...]
    origin: PolicyOrigin


def _table_body(*, text: str, table: str) -> str:
    """Return the lines of `text` belonging to the named TOML table."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("["):
            inside = line.strip() == table
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines)


def _string_values(*, body: str, key: str) -> tuple[str, ...]:
    """Return the double-quoted strings of a `key = [...]` array in `body`."""
    match = re.search(rf"^{re.escape(key)}\s*=\s*\[(.*?)\]", body, re.MULTILINE | re.DOTALL)
    if match is None:
        return ()
    # A `#` inside an array line starts a TOML comment; a path prefix never
    # contains one, so splitting on it cannot truncate a real value.
    inner = "\n".join(part.split("#", 1)[0] for part in match.group(1).splitlines())
    return tuple(re.findall(r'"([^"]*)"', inner))


def derive_product_prefixes(*, pyproject_text: str) -> tuple[str, ...]:
    """Union the repository's declared source trees and prefixes into one prefix set."""
    body = _table_body(text=pyproject_text, table=_DECLARATION_TABLE)
    values = [value for key in _PREFIX_KEYS for value in _string_values(body=body, key=key)]
    return tuple(dict.fromkeys(f"{value.strip('/')}/" for value in values))


def product_policy(
    *, pyproject_text: str | None, overrides: tuple[str, ...] = ()
) -> ProductPathPolicy:
    """Resolve the product-path policy for one repository, never to an empty set."""
    if overrides:
        return ProductPathPolicy(
            prefixes=tuple(f"{value.strip('/')}/" for value in overrides),
            origin="operator-override",
        )
    declared = (
        () if pyproject_text is None else derive_product_prefixes(pyproject_text=pyproject_text)
    )
    if not declared:
        return ProductPathPolicy(prefixes=FLEET_FALLBACK_PRODUCT_PREFIXES, origin="fleet-fallback")
    return ProductPathPolicy(prefixes=declared, origin="declared")


def is_product_py(*, path: str, policy: ProductPathPolicy) -> bool:
    """Classify a changed repo path as product `.py` (the bypass trigger)."""
    if not path.endswith(".py"):
        return False
    if path.startswith("tests/"):
        return False
    if "/_vendor/" in path or "/__pycache__/" in path:
        return False
    return path.startswith(policy.prefixes)

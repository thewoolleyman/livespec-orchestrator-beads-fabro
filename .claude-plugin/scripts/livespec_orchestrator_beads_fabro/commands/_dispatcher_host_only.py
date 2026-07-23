"""Factory-safety routing predicate for the Dispatcher planning layer.

The Dispatcher refuses to sandbox work-items whose first-class
``factory_safety`` field is non-null. Store adapters may still map legacy
routing markers into that field on read, but the Dispatcher itself consumes
the structured WorkItem field.
"""

from __future__ import annotations

import re

from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "host_only_refusal_detail",
    "is_host_only_item",
]

_WORKFLOW_PREFIX = ".github/workflows/"
_EDIT_VERB = (
    r"edit(?:s|ing)?|modif(?:y|ies|ying)|update(?:s|d|ing)?|"
    r"rewrite(?:s|ing)?|touch(?:es|ing)?|chang(?:e|es|ing)"
)
_DECLARED_WORKFLOW_EDIT_PATTERN = "".join(
    (
        rf"\b(?:{_EDIT_VERB})\b[^\n]{{0,80}}{re.escape(_WORKFLOW_PREFIX)}",
        rf"|{re.escape(_WORKFLOW_PREFIX)}[^\n]{{0,80}}\b(?:{_EDIT_VERB})\b",
    )
)
_DECLARED_WORKFLOW_EDIT = re.compile(
    _DECLARED_WORKFLOW_EDIT_PATTERN,
    re.IGNORECASE,
)
_NEGATED_WORKFLOW_SCOPE = re.compile(
    rf"\bno\s+files?\s+(?:under|in)\s+{re.escape(_WORKFLOW_PREFIX)}",
    re.IGNORECASE,
)


def is_host_only_item(*, item: WorkItem) -> bool:
    """Return True when a work-item is intrinsically unsafe for the factory."""
    return item.factory_safety is not None or _declares_workflow_edit(item=item)


def host_only_refusal_detail(*, item_id: str) -> str:
    """Build the actionable refusal message for a factory-unsafe item."""
    return (
        f"factory-safety refusal: work-item {item_id} carries non-null "
        "factory_safety or declares an edit under .github/workflows/, a "
        "withheld sandbox capability. It MUST NOT be dispatched to a fabro "
        "sandbox. host-route it through an attended host session instead; the item "
        "remains open for that route. If the workflow path is citation-only, "
        "use the existing drive valve surfaces (`set-admission:<id>:manual` "
        "and `approve:<id>` after the scope is corrected or split) before "
        "retrying factory dispatch."
    )


def _declares_workflow_edit(*, item: WorkItem) -> bool:
    return any(_text_declares_workflow_edit(text=part) for part in _scope_text_parts(item=item))


def _scope_text_parts(*, item: WorkItem) -> tuple[str, ...]:
    parts = [item.title, item.description]
    if item.reason is not None:
        parts.append(item.reason)
    return tuple(parts)


def _text_declares_workflow_edit(*, text: str) -> bool:
    normalized = text.replace("`", "")
    for line in normalized.splitlines() or (normalized,):
        if _WORKFLOW_PREFIX not in line.lower():
            continue
        if _NEGATED_WORKFLOW_SCOPE.search(line) is not None:
            continue
        if _DECLARED_WORKFLOW_EDIT.search(line) is not None:
            return True
    return False

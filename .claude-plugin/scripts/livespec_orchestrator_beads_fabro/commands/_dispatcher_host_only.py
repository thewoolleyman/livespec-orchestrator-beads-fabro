"""Factory-safety routing predicate for the Dispatcher planning layer.

The Dispatcher refuses to sandbox work-items whose first-class
``factory_safety`` field is non-null. Store adapters may still map legacy
routing markers into that field on read, but the Dispatcher itself consumes
the structured WorkItem field.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "WORKFLOW_SCOPE_OVERRIDE_LABEL",
    "declares_workflow_scope_refusal",
    "host_only_refusal_detail",
    "is_host_only_item",
]

_WORKFLOW_PREFIX = ".github/workflows/"
WORKFLOW_SCOPE_OVERRIDE_LABEL = "workflow-scope-override:citation-only"
# The approval labels that declare a workflow edit. They are exact labels, not
# prefixes, and the citation-only override never lifts them: that override says
# a workflows path in the TEXT is a citation, while one of these labels says the
# item itself edits a workflow.
_WORKFLOW_EDIT_APPROVAL_LABELS = (
    "approval:workflow-edit",
    "approval:workflow-edit-additive",
)
_EDIT_VERB = (
    r"edit(?:s|ing)?|modif(?:y|ies|ying)|update(?:s|d|ing)?|"
    r"rewrite(?:s|ing)?|touch(?:es|ing)?|chang(?:e|es|ing)"
)
_EDIT_VERB_MATCH = re.compile(rf"\b(?:{_EDIT_VERB})\b", re.IGNORECASE)
_VERB_WINDOW = 80
# A negator governs an edit verb only when it sits directly before it (an
# auxiliary such as "does" or "will" precedes the negator, never follows it).
_NEGATOR_BEFORE_VERB = re.compile(
    r"(?:\b(?:not|never|without)|n't)\s+(?:(?:ever|also|then|actually)\s+)?$",
    re.IGNORECASE,
)
# The noun form: "no changes/edits/updates to <path>".
_NOUN_NEGATOR_BEFORE_VERB = re.compile(r"\bno\s+$", re.IGNORECASE)
_TO_AFTER_VERB = re.compile(r"\s+to\b", re.IGNORECASE)
_NEGATED_WORKFLOW_SCOPE = re.compile(
    rf"\bno\s+files?\s+(?:under|in)\s+{re.escape(_WORKFLOW_PREFIX)}",
    re.IGNORECASE,
)


def is_host_only_item(*, item: WorkItem, raw_labels: Sequence[str] = ()) -> bool:
    """Return True when a work-item is intrinsically unsafe for the factory."""
    if item.factory_safety is not None:
        return True
    if _matched_workflow_edit_labels(raw_labels=raw_labels):
        return True
    if WORKFLOW_SCOPE_OVERRIDE_LABEL in raw_labels:
        return False
    return declares_workflow_scope_refusal(item=item, raw_labels=raw_labels)


def declares_workflow_scope_refusal(*, item: WorkItem, raw_labels: Sequence[str] = ()) -> bool:
    """Return True when the declared workflow-edit heuristic refuses the item."""
    if item.factory_safety is not None:
        return False
    if WORKFLOW_SCOPE_OVERRIDE_LABEL in raw_labels:
        return False
    return _declares_workflow_edit(item=item)


def host_only_refusal_detail(*, item_id: str, raw_labels: Sequence[str] = ()) -> str:
    """Build the actionable refusal message for a factory-unsafe item.

    When a workflow-edit approval label caused the refusal, the message names
    every label that matched and omits the citation-only remedy, which does not
    lift a label.
    """
    matched = _matched_workflow_edit_labels(raw_labels=raw_labels)
    if matched:
        names = ", ".join(f"`{label}`" for label in matched)
        return (
            f"factory-safety refusal: work-item {item_id} carries the workflow-edit "
            f"approval label {names}, so its change touches the GitHub Actions "
            "workflows directory, a withheld sandbox capability. It MUST NOT be "
            "dispatched to a fabro sandbox. host-route it through an attended host "
            "session instead; the item remains open for that route."
        )
    return (
        f"factory-safety refusal: work-item {item_id} carries non-null "
        "factory_safety or declares an edit under .github/workflows/, a "
        "withheld sandbox capability. It MUST NOT be dispatched to a fabro "
        "sandbox. host-route it through an attended host session instead; the item "
        "remains open for that route. If the workflow path is citation-only, "
        "set the recorded override with "
        "`set-workflow-scope-override:<id>:citation-only`, or add an inline "
        "negation declaration stating that the item ships no files under "
        ".github/workflows/, before retrying factory dispatch."
    )


def _matched_workflow_edit_labels(*, raw_labels: Sequence[str]) -> tuple[str, ...]:
    return tuple(label for label in _WORKFLOW_EDIT_APPROVAL_LABELS if label in raw_labels)


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
        if _line_has_unnegated_workflow_edit(line=line):
            return True
    return False


def _line_has_unnegated_workflow_edit(*, line: str) -> bool:
    """Return True when any edit verb near the workflows path is not negated.

    A false refusal is the safe failure and a false admission the unsafe one,
    so every nearby edit verb must be governed by a negator for the line to
    pass; anything ambiguous stays refused.
    """
    return any(
        _verb_near_workflow_prefix(line=line, verb=verb)
        and not _verb_is_negated(line=line, verb=verb)
        for verb in _EDIT_VERB_MATCH.finditer(line)
    )


def _verb_near_workflow_prefix(*, line: str, verb: re.Match[str]) -> bool:
    lowered = line.lower()
    reach = _VERB_WINDOW + len(_WORKFLOW_PREFIX)
    after = lowered[verb.end() : verb.end() + reach]
    before = lowered[max(0, verb.start() - reach) : verb.start()]
    return _WORKFLOW_PREFIX in after or _WORKFLOW_PREFIX in before


def _verb_is_negated(*, line: str, verb: re.Match[str]) -> bool:
    preceding = line[: verb.start()]
    if _NEGATOR_BEFORE_VERB.search(preceding) is not None:
        return True
    return (
        _NOUN_NEGATOR_BEFORE_VERB.search(preceding) is not None
        and _TO_AFTER_VERB.match(line, verb.end()) is not None
    )

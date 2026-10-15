"""Whether one terminated run's tree has to be published to a preservation ref.

THE WHOLE DECISION, AND NOTHING ELSE. `_dispatcher_preserved_tree` reads and
publishes, `_dispatcher_preserved_tree_record` writes the ledger comment and
the journal row; this answers only "does this run need that done at all", so
the answer can be exercised across every state without a factory or a forge.

TWO CONDITIONS, AND THE SECOND ONE IS WHERE THE DANGER IS. The run must have
ended on a failed engine CHECKPOINT, and the Dispatcher must not have OBSERVED
a terminal patch on the run's terminal event. The second is three-valued and
only one of its three answers suppresses the publication: a patch that was
read, a terminal event that carried none, and a stream that could not be read
at all. The ratified clause makes the third behave like the second -- "a
terminal patch the Dispatcher could not observe because the run's events cannot
be read does not count as observed, so the publication above MUST be
attempted: a duplicate preservation is recoverable, while a missed one is not."

So the one coding mistake this module exists to prevent is reaching for a patch
field, finding nothing because the stream was unreadable, and suppressing the
publication on it. That reads as the measured-and-absent case at every surface,
and the cost of getting it wrong is an hour of agent work that nothing else
carries. `records=None` is therefore handled BEFORE anything looks for a patch.

THE RECOGNIZER IS DELIBERATELY SHARED-SHAPED rather than private to the
preservation path. `bd-ib-6jkjzm` owns the ATTRIBUTION of the same ending (its
outcome detail, its `checkpoint-failure` journal row and its
`livespec-checkpoint-failure` comment) and must key on the same event and the
same engine message, so both public readings live here and neither path grows a
second recognizer that could disagree about whether a run failed its
checkpoint. That module also owns recording the terminal patch's size and
digest in ITS records; the figures are carried here because the SUPPRESSION
needs them -- a suppression that recorded neither would be indistinguishable
from a reading that never looked.

THE ENGINE MESSAGE IS THE FALLBACK AND THE EVENT IS THE PREFERENCE, because a
`checkpoint.failed` event NAMES its node while the message has to be parsed for
one. Both are read: the clause requires the disposition to apply when the
events cannot be read, and then the message is the only evidence left.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "PreservationTrigger",
    "failed_checkpoint_node",
    "preservation_trigger",
    "terminal_patch_digest",
]

# The engine's own wording for the ending, as measured on run
# 01M4YJGC55V86C9V1X07QG3Y2H and as `scenarios.md` Scenario 170 quotes it:
# `git checkpoint commit failed for node implement: git commit failed (exit 1)`.
# Anchored on NEITHER end, because the message arrives wrapped in whatever
# outcome prose the terminal mapper built around it -- an anchored pattern is
# the measured instrument-aim failure this repository's own catalogue records.
_NODE_IN_MESSAGE_RE = re.compile(r"checkpoint[^\n]*?\bfor node (?P<node>[A-Za-z0-9_.-]+)")

# The ending without a node in it. A Petri-era engine reports the class rather
# than the sentence, so the condition is present and the node is not; that is a
# checkpoint failure whose node is unknown, never a run that did not fail one.
_CHECKPOINT_FAILURE_MARKERS = ("checkpoint.failed", "checkpoint_failed")

_FAILED_EVENT_SUFFIX = "run.failed"
_CHECKPOINT_FAILED_EVENT_SUFFIX = "checkpoint.failed"

# Where a terminal patch rides. Every spelling is read because the shape was
# unmeasured when this was written, and the direction of a miss is asymmetric:
# a patch read where none exists suppresses a needed publication, while a patch
# missed where one exists costs one recoverable duplicate ref.
_PATCH_KEYS = ("terminal_patch", "patch", "diff")
_NESTED_KEYS = ("data", "payload", "event")


@dataclass(frozen=True, kw_only=True)
class PreservationTrigger:
    """The decision, the node it was taken for, and what the patch reading saw.

    `terminal_patch_bytes` and `terminal_patch_sha256` are BOTH null whenever no
    patch was observed, and the clause requires that of the unreadable-stream
    case too: the figures describe a patch that was READ, so inventing a zero
    for one that was not would assert the run carried no work.
    """

    preserves: bool
    reason: str
    node: str | None
    terminal_patch_bytes: int | None
    terminal_patch_sha256: str | None


def failed_checkpoint_node(*, failure_text: str) -> str | None:
    """The node named by a checkpoint-failure message, or None for any other text.

    PUBLIC because `bd-ib-6jkjzm`'s attribution reads the same message for the
    same node, and two parses of one sentence drift silently -- each one's own
    tests keep passing while they disagree about a node nobody re-checks.
    """
    matched = _NODE_IN_MESSAGE_RE.search(failure_text)
    return None if matched is None else matched.group("node")


def terminal_patch_digest(*, patch: str) -> tuple[int, str]:
    """The patch's byte size and sha256 digest, measured over its UTF-8 bytes.

    Bytes rather than characters, for the reason this fleet's proof-budget
    module records about the same distinction: the two agree on ASCII, which is
    exactly why a character count passes every ordinary diff and misreports the
    one carrying a non-ASCII path or an em dash in a comment.
    """
    raw = patch.encode("utf-8")
    return len(raw), hashlib.sha256(raw).hexdigest()


def preservation_trigger(
    *, failure_text: str, records: tuple[dict[str, Any], ...] | None
) -> PreservationTrigger:
    """Decide whether this run's tree must be published to a preservation ref."""
    node = _node(failure_text=failure_text, records=records)
    if node is _NO_CHECKPOINT_FAILURE:
        return PreservationTrigger(
            preserves=False,
            reason="the run records no failed engine checkpoint, so no tree is unpreserved",
            node=None,
            terminal_patch_bytes=None,
            terminal_patch_sha256=None,
        )
    # BEFORE any patch lookup. See the module docstring: an unreadable stream
    # that fell through to a patch search would report "no patch" and suppress
    # the one publication the clause makes mandatory.
    if records is None:
        return PreservationTrigger(
            preserves=True,
            reason=(
                "the run ended on a failed engine checkpoint and its events could not be read,"
                " so a terminal patch is unobserved rather than absent"
            ),
            node=node,
            terminal_patch_bytes=None,
            terminal_patch_sha256=None,
        )
    patch = _terminal_patch(records=records)
    if patch is None:
        return PreservationTrigger(
            preserves=True,
            reason=(
                "the run ended on a failed engine checkpoint and its terminal event carries"
                " no terminal patch, so nothing else carries the tree"
            ),
            node=node,
            terminal_patch_bytes=None,
            terminal_patch_sha256=None,
        )
    byte_size, digest = terminal_patch_digest(patch=patch)
    return PreservationTrigger(
        preserves=False,
        reason=(
            "the run's terminal event carries an observed terminal patch, so the"
            " preserve-by-reference pointer stands alone"
        ),
        node=node,
        terminal_patch_bytes=byte_size,
        terminal_patch_sha256=digest,
    )


# The sentinel for "this run did not fail a checkpoint", kept apart from the
# `None` that means "it did, and no node was named". Collapsing the two would
# make an unnamed node suppress the publication.
_NO_CHECKPOINT_FAILURE = "\x00no-checkpoint-failure"


def _node(*, failure_text: str, records: tuple[dict[str, Any], ...] | None) -> str | None:
    """The failed checkpoint's node, or the no-failure sentinel.

    The EVENT wins over the message because it names its node as a field, and
    the message is parsed for one. Either establishing the ending is enough:
    the events can be unreadable, and an engine can report the class without
    the sentence.
    """
    for record in records or ():
        kind = record.get("type")
        if isinstance(kind, str) and kind.endswith(_CHECKPOINT_FAILED_EVENT_SUFFIX):
            named = record.get("node")
            return named if isinstance(named, str) and named else None
    named = failed_checkpoint_node(failure_text=failure_text)
    if named is not None:
        return named
    if any(marker in failure_text for marker in _CHECKPOINT_FAILURE_MARKERS):
        return None
    return _NO_CHECKPOINT_FAILURE


def _terminal_patch(*, records: tuple[dict[str, Any], ...]) -> str | None:
    """The patch the run's terminal failure event carries, when it carries one.

    Read off the TERMINAL event alone and never off the stream at large: an
    earlier node's own diff event would satisfy a whole-stream search while
    saying nothing about the failed node's work, which is the one thing a
    terminal patch has to carry for the suppression to be safe.
    """
    for record in reversed(records):
        kind = record.get("type")
        if not isinstance(kind, str) or not kind.endswith(_FAILED_EVENT_SUFFIX):
            continue
        held = _patch_in(mapping=record)
        if held is not None:
            return held
    return None


def _patch_in(*, mapping: dict[str, Any]) -> str | None:
    """A non-empty patch string held directly or one level down.

    An EMPTY patch is no patch: the engine renders an absent field as the empty
    string on at least one measured surface, and a zero-length diff asserts the
    run changed nothing -- the single conclusion this clause exists to prevent.
    """
    for key in _PATCH_KEYS:
        held = mapping.get(key)
        if isinstance(held, str) and held:
            return held
    for key in _NESTED_KEYS:
        nested = mapping.get(key)
        if isinstance(nested, dict):
            held = _patch_in(mapping=cast("dict[str, Any]", nested))
            if held is not None:
                return held
    return None

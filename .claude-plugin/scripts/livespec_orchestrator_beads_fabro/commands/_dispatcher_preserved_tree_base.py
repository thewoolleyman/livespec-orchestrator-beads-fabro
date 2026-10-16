"""The commit a dispatch's sandbox was staged at, read back off its own journal.

The preservation commit's PARENT has to be this run's base, and the ratified
clause says where that comes from: "the commit the dispatch's sandbox checked
out and which the dispatch record MUST name". `SourceStagingRunner` already
writes it -- the `source-checkout-stage` row's `staged_at` -- so the base is
read back rather than re-derived.

RE-DERIVING IT WOULD BE WRONG AND NOT MERELY REDUNDANT, which is why this
module exists instead of a `git rev-parse` at disposition time. The staging
base is NOT simply the dispatching checkout's head: `_staging_base` freshly
fetches the default branch and stages at ORIGIN's head whenever the local one
is behind it. So a disposition that asked git would get this host's head, which
on a drain that has run for an hour is routinely a different commit from the one
the sandbox cloned -- and the resulting tree would be a diff against a commit
the run never saw, with every intervening change of master folded into it as
though the run had made it. That artifact looks exactly like a large successful
implement stage.

PURE, and a reading rather than a measurement: every answer is a fact the
dispatch already recorded. An unestablished base is `None`, which the
disposition reports as the publication step that failed rather than papering
over with a plausible commit.
"""

from __future__ import annotations

__all__: list[str] = [
    "SOURCE_STAGE",
    "STAGED_AT_KEY",
    "run_base_commit",
]

# The row and the key, named here rather than spelled at the read: this is the
# consumer end of `_dispatcher_source_staging`'s own record, and a reader
# spelling either differently from its writer finds nothing and reports an
# unestablished base -- which is indistinguishable at every surface from a
# dispatch that genuinely never staged.
SOURCE_STAGE = "source-checkout-stage"
STAGED_AT_KEY = "staged_at"

_WORK_ITEM_KEY = "work_item_id"
_STAGE_KEY = "stage"


def run_base_commit(*, records: tuple[dict[str, object], ...], work_item_id: str) -> str | None:
    """The commit this item's newest staging row names, or None for no such row.

    The LATEST matching row wins, because one journal accumulates every
    dispatch this checkout ever made: a re-dispatch appends a second staging
    row for the same item, and this run's base is the last one staged. Taking
    the first would parent the tree on the base of a dispatch that has already
    ended.

    A row that names no usable commit is passed over rather than treated as the
    answer, and so cannot mask an earlier row that does name one. The empty
    string is the dangerous reading here: it would reach the forge as a parent
    and be refused for its shape, which reports as a publication fault rather
    than as the unestablished base it is.
    """
    for record in reversed(records):
        if record.get(_STAGE_KEY) != SOURCE_STAGE:
            continue
        if record.get(_WORK_ITEM_KEY) != work_item_id:
            continue
        staged = record.get(STAGED_AT_KEY)
        if isinstance(staged, str) and staged.strip():
            return staged.strip()
    return None

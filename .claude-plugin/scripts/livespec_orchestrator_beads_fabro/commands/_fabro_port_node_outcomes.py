"""The per-node grading on one Fabro run record, whichever engine wrote it.

This is ONE reading of the engine's grading, and it is its own module for the
same reason `_fabro_port_checkpoints` is: it belongs to neither of the two
questions that ask it. `_fabro_terminal_evidence` grades a needs-human
terminal's predecessors against it, to say which stage failed before the
escalation; `_dispatcher_successful_terminal` asks whether the stages
dominating the configured green terminal are recorded succeeded, to tell a
completed workflow from a genuinely failed one. Two copies of this walk is how
those two would come to disagree about whether the same run is READABLE AT ALL
-- and "unreadable" is the answer that keeps an already-merged pull request
classified as a failed dispatch.

THE PETRI ENGINE RECORDS NO `node_outcomes` AT ALL, which is why this reading
has two inputs rather than two readers. A terminated run's checkpoint on that
engine carries only `current_node`, `git_commit_sha` and `timestamp`; the
per-stage results live in the record's own top-level `stages` map, keyed
`<node>@<visit>`, each entry carrying `handler`, `state`, `output` and
`response`. Reading that map is what keeps a Petri ending from being graded
against nothing -- measured 2026-10-15 on run `01M4Y7EJWTQWK5CWWS0NKDHY7T`,
whose `inspect` named 48 succeeded stages and 2 failed ones while a reader of
`node_outcomes` alone saw an empty map.

The stage map is a FALLBACK and never a merge: a record carrying
`node_outcomes` is graded from them alone, because that map is the checkpoint's
own account of the ending while the stage map is the run's account of its whole
history, and a reader preferring the broader one would answer a different
question on the engine that supplies both. Only the `state` field is projected,
and an entry carrying none is dropped rather than counted -- an ungradeable
entry must not make the map look readable, because every caller distinguishes
"graded, and nothing failed" from "nothing to grade" and collapsing the two is
the direction that invents evidence.

BEING THE WHOLE HISTORY, THAT MAP IS COLLAPSED TO ONE VISIT PER NODE BEFORE IT
IS RETURNED. `node_outcomes` is keyed by NODE and carries that node's CURRENT
status, which is why a retried node reports `succeeded` there; the stage map is
keyed `<node>@<visit>` and the engine never retires an entry, so a visit that
failed and was then repaired by the graph's bounded fix loop keeps its own
`failed` entry for the life of the record. Grading entry-by-entry therefore
attributes a repaired node on the ORDINARY shape of every run the fix loop
rescued -- `janitor@1` failed, `fix@1` succeeded, `janitor@2` succeeded -- which
blames a stage nobody should look at on one caller, and refuses a completed
workflow on the other. That per-visit entries persist is measured rather than
supposed: the run this reading was filed from carries `proof_capture@1`
succeeded beside `proof_capture@2` failed.

The latest visit is chosen by the suffix AS A NUMBER, because neither
alternative holds. Map order is a caller's ordering fallback for SEQUENCE but is
not evidence of visit order, and a text comparison puts `@10` before `@9` --
both agree with the numeric answer on the measured record and disagree on a
longer loop, so a fixture that never crossed ten would pass against either
wrong rule. A suffix carrying no number is left to document order, which is the
only ordering evidence such a record offers; retaining both entries because
neither can be ranked would be the attribution defect returning through the one
shape no engine writes.

The collapse runs AFTER the ungradeable entries are dropped, which keeps one
rule rather than two: an entry with no readable `state` is not a reading at
all, so it is not a visit that can outlive an earlier one. Collapsing first
would let an unreadable latest entry suppress its node's last readable state.

THE KEYS ARE RETURNED AS THE ENGINE WROTE THEM, visit suffix included, because
`proof_capture@2` says WHICH visit the engine recorded and discarding that half
would destroy a fact one caller renders. `fabro_stage_node` is exported beside
the map so a caller asking about a NODE divides the key the same way the
collapse above did; after the collapse that projection is one-to-one, so a
caller may re-key by it without merging two readings of one node.

It is a leaf: it imports no other port module, because the only thing it needs
is the already-normalized record and checkpoint mappings its callers hand it.
"""

from __future__ import annotations

from typing import Any, cast

__all__: list[str] = [
    "fabro_node_outcomes",
    "fabro_stage_node",
]


def fabro_node_outcomes(
    *,
    record: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """One record's graded outcomes, in the engine's own order, malformed dropped.

    An empty map means the record offers NOTHING TO GRADE AGAINST, which every
    caller reads as unavailable evidence rather than as an absence of failure.
    """
    return _checkpoint_outcomes(checkpoint=checkpoint) or _stage_state_outcomes(record=record)


def fabro_stage_node(*, stage: str) -> str:
    """The node half of a `<node>@<visit>` stage key, or the key as it stands.

    A pinned-engine key carries no `@` and is returned unchanged, so one
    reading serves both shapes. The caller that excluded a NODE id by comparing
    it directly against a Petri key silently matched nothing, which is the
    whole reason this division has one owner rather than one per caller.
    """
    return stage.split("@", maxsplit=1)[0].strip()


def _checkpoint_outcomes(*, checkpoint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The per-node outcome map, keyed by node id, in the record's own order.

    JSON object order is preserved by the parser, so the map's own order is the
    engine's document order -- a better fallback than sorting, which would
    impose an alphabetical answer on a question about sequence.
    """
    return _mapping_entries(raw=checkpoint.get("node_outcomes"))


def _stage_state_outcomes(*, record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The Petri `stages` map projected onto the outcome shape, in record order.

    The projection keeps ONE grading path rather than giving the engine its own
    reader: every caller asks whether a node is recorded failed or succeeded and
    in what order, which `state` answers exactly as `status` does.
    """
    graded = {
        stage: {"status": state}
        for stage, entry in _mapping_entries(raw=record.get("stages")).items()
        if (state := _text(value=entry.get("state"))) is not None
    }
    newest = _newest_visits(stages=tuple(graded))
    return {stage: outcome for stage, outcome in graded.items() if stage in newest}


def _newest_visits(*, stages: tuple[str, ...]) -> frozenset[str]:
    """One stage key per node -- the newest visit of each, by visit number.

    A frozenset of the SURVIVING KEYS rather than a node-to-key map, so the
    caller filters its own already-ordered mapping and each retained entry
    keeps its own position in the record. Carrying the node half out of here
    would place every multi-visit node at its FIRST visit's position instead.
    """
    newest: dict[str, str] = {}
    for stage in stages:
        held = newest.get(fabro_stage_node(stage=stage))
        if held is None or _stage_visit(stage=stage) >= _stage_visit(stage=held):
            newest[fabro_stage_node(stage=stage)] = stage
    return frozenset(newest.values())


def _stage_visit(*, stage: str) -> int:
    """The visit number of a `<node>@<visit>` key; 0 for one carrying none.

    `>=` at the call site is what makes the no-number case fall back to
    document order: two unnumbered visits of one node compare equal, so the
    later-written entry replaces the earlier one.
    """
    visit = stage.partition("@")[2].strip()
    return int(visit) if visit.isdigit() else 0


def _mapping_entries(*, raw: object) -> dict[str, dict[str, Any]]:
    """One engine-written map of node id to mapping, malformed entries dropped.

    Shared by both inputs so a record whose keys or values are unusable
    degrades the same way whichever engine wrote it.
    """
    if not isinstance(raw, dict):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for key, value in cast("dict[object, object]", raw).items():
        if isinstance(key, str) and key.strip() and isinstance(value, dict):
            entries[key.strip()] = cast("dict[str, Any]", value)
    return entries


def _text(*, value: object) -> str | None:
    """One field as non-empty text, or None for anything else -- null included."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None

"""The `release-spec-tier:<id>:<heading>` valve — a human's way through a misjudged hold.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` holds a spec-change-tier
item out of `ready` until its linked proposal ratifies and the judgement returns
`stated`. "Because the judgement can miss a clause the ratified specification
already carries, a held item MUST also have a human way through that needs no
ratification and no agreeing model run", and this valve is it: the human names an
existing H2 heading and attests that it states the item's asked-for behaviour.

THE VALVE ATTESTS AND CLEARS, AND WRITES NO STATUS. It appends the attestation
comment (`_spec_tier_attestation`), journals the act, and then asks the same
classification gate every cadence point asks, which now finds a standing
attestation and records a `none` tier. Routing is delegated: an `active` item
carrying `rework:pending` keeps its status and marker for the rework route, and
every other item goes back through intake Definition-of-Ready routing, whose
admission policy, mechanical findings, dependencies and size gate all still
apply. "The valve MUST NOT write a status itself" is therefore structural — there
is no status write in this module to forget.

THE REFUSALS RUN IN THE ORDER OF WHAT THEY COST TO CHECK, and every one precedes
the first write. The lane and the standing hold are ledger reads; the run
inventory is a subprocess; the heading is a specification read. A refusal after
the attestation comment would leave a standing override on an item the valve
reported it had not released, and beads comments are append-only.

A RUN OF THE ITEM THAT CANNOT BE MEASURED REFUSES, the direction this fleet's
gauges fail in. An unanswered `fabro ps` is not a factory known to hold nothing,
and releasing beside a live run would re-route an item whose claim is in flight.

THE HEADING IS TAKEN AS THE REST OF THE ACTION ID, so a title carrying a colon
survives, and a heading named without its `## ` marker resolves the same clause.
Matching is by the specification's own heading text after that normalization;
nothing fuzzier, because the attestation is a claim about one clause.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_arm_guard import (
    observe_item_run_liveness,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SPEC_DIRNAME
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_RELEASE,
    recorded_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import (
    attestation_comment,
    clause_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import clauses_named
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
    from livespec_orchestrator_beads_fabro.commands._drive_reject_valve import HumanValveRunner
    from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import CondensedClause
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "RELEASE_SPEC_TIER_ACTION",
    "RELEASE_SPEC_TIER_STAGE",
    "release_spec_tier",
]

RELEASE_SPEC_TIER_ACTION = "release-spec-tier"
RELEASE_SPEC_TIER_STAGE = "human-valve-release-spec-tier"

# The same journal the Dispatcher and the other journaled drive doors append to,
# so a release and the dispatch it unblocks are readable from one file.
_JOURNAL_RELATIVE_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"
_VALID_LANES = frozenset({"backlog", "pending-approval", "ready", "blocked"})
_ACTIVE = "active"
_HEADING_MARKER = "## "
# Every gate intake asks the capture dialogue about is already answered for an
# item that is filed; the real admission requirements are re-graded by intake
# itself (dependencies, findings, size, policy), which is what "preserving every
# other admission requirement" means.
_FILED_ITEM = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)


def release_spec_tier(  # noqa: PLR0913 - each argument is one input of the act.
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    heading: str,
    identity: InvokerIdentity,
    runner: HumanValveRunner | None,
) -> dict[str, Any]:
    """Attest `heading` for `item`, clear its hold, and route it through intake."""
    refusal = _eligibility_refusal(repo=repo, config=config, item=item, aid=aid, runner=runner)
    if refusal is not None:
        return refusal
    resolved = _resolved_clause(repo=repo, item=item, aid=aid, heading=heading)
    if isinstance(resolved, dict):
        return resolved
    version, clause = resolved
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=attestation_comment(
            item=item, actor=identity.invoker, clause=clause, spec_version=version
        ),
    )
    record = _journal_attestation(
        repo=repo, identity=identity, item=item, clause=clause, version=version
    )
    cleared = classify_item_spec_change_tier(item=item, repo=repo, path=config, stage=STAGE_RELEASE)
    if cleared.recorded is None or cleared.is_spec_change:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="hold-not-cleared",
            msg=(
                f"{RELEASE_SPEC_TIER_ACTION} attested {clause.heading.rstrip()} for {item.id} but"
                f" the classification could not clear the hold ({cleared.cause}); the attestation"
                " stands and the next classification pass will clear it."
            ),
        )
    routed = _routed_status(config=config, item=item, aid=aid)
    if isinstance(routed, dict):
        return routed | {"journal": record}
    return valve_success(
        aid=aid,
        wid=item.id,
        stage=RELEASE_SPEC_TIER_STAGE,
        status=routed,
        assignee=item.assignee,
        msg=(
            f"Released {item.id} from its spec-change-tier hold on the attestation that"
            f" {clause.heading.rstrip()} states its asked-for behaviour; status {routed}."
        ),
    ) | {"journal": record}


def _eligibility_refusal(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    runner: HumanValveRunner | None,
) -> dict[str, Any] | None:
    """The first reason this item may not be released, or `None` when it may."""
    standing = _standing_refusal(config=config, item=item, aid=aid)
    if standing is not None:
        return standing
    return _activity_refusal(repo=repo, item=item, aid=aid, runner=runner)


def _standing_refusal(*, config: StoreConfig, item: WorkItem, aid: str) -> dict[str, Any] | None:
    """Refuse an item outside the valid lanes, or one the ledger does not show held."""
    if item.status not in _VALID_LANES and not (item.status == _ACTIVE and item.rework_pending):
        return invalid_source_state(
            aid=aid,
            item=item,
            expected="backlog, pending-approval, ready, blocked, or active with rework:pending",
        )
    comments = item_comment_bodies(path=config, work_item_id=item.id)
    recorded = recorded_spec_change_tier(comments=comments or ())
    if recorded is None or not recorded.is_spec_change:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="not-held",
            msg=f"{RELEASE_SPEC_TIER_ACTION} refused: {item.id} carries no spec-change-tier hold.",
        )
    return None


def _activity_refusal(
    *, repo: Path, item: WorkItem, aid: str, runner: HumanValveRunner | None
) -> dict[str, Any] | None:
    """Refuse while a run of the item is live, unmeasured, or its ownership lock is held."""
    liveness = observe_item_run_liveness(repo=repo, work_item_id=item.id, runner=runner)
    if not liveness.observed:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="live-run",
            msg=(
                f"{RELEASE_SPEC_TIER_ACTION} refused: whether a run of {item.id} is live could not"
                " be established, because the configured factory did not answer with a run"
                " inventory; the hold stands."
            ),
        )
    if liveness.live_run_ids:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="live-run",
            msg=(
                f"{RELEASE_SPEC_TIER_ACTION} refused: {', '.join(liveness.live_run_ids)} is still"
                f" non-terminal, so a run of {item.id} is live; the hold stands."
            ),
        )
    if live_dispatch_lock(repo=repo, work_item_id=item.id) is not None:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="dispatch-lock-held",
            msg=(
                f"{RELEASE_SPEC_TIER_ACTION} refused: a live process holds the dispatch-scoped"
                f" ownership lock of {item.id}; the hold stands."
            ),
        )
    return None


def _resolved_clause(
    *, repo: Path, item: WorkItem, aid: str, heading: str
) -> tuple[str, CondensedClause] | dict[str, Any]:
    """The specification version and the clause `heading` names, else the refusal."""
    named = heading.strip()
    if not named.startswith(_HEADING_MARKER):
        named = f"{_HEADING_MARKER}{named}"
    read = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPEC_DIRNAME),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if not isinstance(read, AttemptFailure):
        clauses = clauses_named(spec_tree=read.files, headings=[named])
        if clauses:
            return str(read.version), clauses[0]
    return valve_refusal(
        aid=aid,
        wid=item.id,
        err="unresolved-heading",
        msg=(
            f"{RELEASE_SPEC_TIER_ACTION} refused: {named!r} is not an H2 heading of the"
            f" ratified specification; the hold on {item.id} stands."
        ),
    )


def _journal_attestation(
    *,
    repo: Path,
    identity: InvokerIdentity,
    item: WorkItem,
    clause: CondensedClause,
    version: str,
) -> dict[str, object]:
    """Append the durable attestation record and return what was written.

    The `invoker` field is stamped by the append layer, the only place the
    attribution contract lets it come from; the object is returned so the result
    payload republishes the SAME record rather than a second hand-built
    description of it.
    """
    record: dict[str, object] = {
        "actor": "operator",
        "stage": RELEASE_SPEC_TIER_STAGE,
        "work_item_id": item.id,
        "heading": clause.heading.rstrip(),
        "spec_file": clause.path,
        "spec_version": version,
        "clause_digest": clause_digest(clause=clause),
    }
    JournalFile(path=repo / _JOURNAL_RELATIVE_PATH, identity=identity).append(record=record)
    return record


def _routed_status(*, config: StoreConfig, item: WorkItem, aid: str) -> str | dict[str, Any]:
    """The status the item rests at, routed by its existing owner — or the refusal.

    A `rework:pending` item keeps its status and marker, with no intake routing
    and no fresh approval: its execution belongs to the rework route. Every other
    item goes back through intake, which re-grades everything but the hold.
    """
    if item.status == _ACTIVE:
        return item.status
    routed = apply_intake_dor(path=config, item_id=item.id, checklist=_FILED_ITEM)
    if not is_successful(routed):
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="intake-routing-failed",
            msg=(
                f"intake could not route {item.id} after the release:"
                f" {unsafe_perform_io(routed.failure())}"
            ),
        )
    return unsafe_perform_io(routed.unwrap())

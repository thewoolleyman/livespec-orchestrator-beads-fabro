"""The Proof of Done hygiene lanes: two pending legs, and a stale pointer.

Every fact here is required by `SPECIFICATION/contracts.md`. The
human-attested-leg clause (v114) says `needs-attention` MUST surface the pending
leg as an attention item carrying the pull request link; the host-captured leg
(v115) says it MUST surface a pending host leg "as an attention item naming the
item, the pull request and the assertions"; and the pointer clause says a pointer
"whose run id or comment id does not match the latest record on the pull request
is stale and MUST be surfaced by `needs-attention` as a hygiene fact naming the
item and the pull request."

WHY NEITHER PENDING-LEG FACT ADVERTISES THE `accept` VALVE. Both exist precisely
because that valve REFUSES the item, so handing an operator `accept:<id>` would
hand them a command this very row says will fail — the misdirecting-handoff defect
the unrunnable-acceptance lane records. What the operator is handed instead is the
item's own record, because the thing they have to do — publish a Proof of Done
record on the pull request — is not an action any `drive` verb performs.

WHY THE TWO PENDING LANES ARE SEPARATE ROWS AND NOT ONE. They are cleared by
different parties doing different work: an agent session on an operator host
captures and a second session replays the host leg, while a HUMAN attests the
other. One merged row would name a mixed set of assertions under a single remedy,
and an operator clearing the half addressed to them would find the item still
parked with no row saying which half remains.

WHY THE HOST LANE READS NEITHER THE FORGE NOR THE POINTER'S HOST LINK. An item
rests in `acceptance` precisely until its host leg lands — the acceptance pass
lists the assertion as pending under every policy, and the accept valve refuses
until a `host_verified` record lists it as reproduced — so "in `acceptance` and
carrying a host-captured assertion" IS "the host leg is pending", decided from the
ledger alone. The pointer carries no host link to read in this build (it gains one
with the posting primitive), and a forge read per parked item would make the
snapshot pay a round trip for an answer the status already gives.

WHY THE STALE LANE READS THE FORGE AND THE PENDING LANES DO NOT. Staleness is a
comparison between the pointer and the pull request's latest record OF THE KIND
THE POINTER CITES, so there is no way to decide it from the ledger alone. The
kind is the pointer's own verdict rather than a fixed `verified`, because a
host-only item's pointer cites its independent `host_verified` replay —
`_is_stale` carries why a fixed comparison reported every such pointer stale.
The read is scoped to items that have NOT closed and that carry a pointer, which
bounds it to the work in flight: a closed item's pointer is frozen history, and
re-reading every closed item's pull request on every snapshot would make the
attention pass a function of the whole ledger's size.

AN UNREADABLE PULL REQUEST IS NOT A STALE POINTER. A failed read and a pull
request carrying no record of the cited kind both yield NO fact, because the lane
would otherwise manufacture a staleness finding out of an absent observation —
the same rule the acceptance pass's evidence legs obey.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    ProofPointer,
    pointer_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HOST_RECORDED,
    VERDICT_HOST_VERIFIED,
    VERDICT_HUMAN_ATTESTED,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "pending_host_leg_items",
    "pending_human_attestation_items",
    "stale_proof_pointer_items",
]

_ACCEPTANCE_STATUS = "acceptance"
_CLOSED_STATUS = "done"


def pending_host_leg_items(
    *, project_root: Path, repo: str, items: list[WorkItem]
) -> list[AttentionItem]:
    """One fact per parked item still waiting for its independent host replay.

    A POINTER is required, for the reason the human lane requires one: the clause
    says the fact names the pull request, and the pointer is the only surface that
    identifies it. A parked item with no pointer at all is the missing-pointer
    lane's row, and reporting it here as well would give an operator two rows for
    one repair.
    """
    return [
        _pending_host_item(project_root=project_root, repo=repo, item=item, pointer=pointer)
        for item in items
        if item.status == _ACCEPTANCE_STATUS
        if effective_criteria(item=item).host_captured_assertions
        for pointer in (pointer_in(description=item.description),)
        if pointer is not None
    ]


def pending_human_attestation_items(
    *, project_root: Path, repo: str, items: list[WorkItem]
) -> list[AttentionItem]:
    """One fact per parked item still waiting for its human-attested record."""
    return [
        _pending_item(project_root=project_root, repo=repo, item=item, pointer=pointer)
        for item in items
        if item.status == _ACCEPTANCE_STATUS
        if effective_criteria(item=item).human_attested_assertions
        for pointer in (pointer_in(description=item.description),)
        if pointer is not None and pointer.human_attested_url is None
    ]


def stale_proof_pointer_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    runner: CommandRunner | None = None,
) -> list[AttentionItem]:
    """One fact per in-flight item whose pointer disagrees with its pull request."""
    active = ShellCommandRunner() if runner is None else runner
    return [
        _stale_item(project_root=project_root, repo=repo, item=item, pointer=pointer)
        for item in items
        if item.status != _CLOSED_STATUS
        for pointer in (pointer_in(description=item.description),)
        if pointer is not None
        if _is_stale(project_root=project_root, pointer=pointer, runner=active)
    ]


def _is_stale(*, project_root: Path, pointer: ProofPointer, runner: CommandRunner) -> bool:
    """Whether the pull request's latest record OF THE POINTER'S KIND is not the cited one.

    Both the run id and the comment link are compared, because the clause names
    both and they fail independently: a re-dispatch publishes a record under a new
    RUN id, while a corrected record from the same run publishes under a new
    COMMENT id — and a check on either alone is blind to the other.

    THE COMPARISON IS SCOPED TO THE POINTER'S OWN VERDICT, not fixed at `verified`.
    A pointer cites the record its acceptance pass rested on, and for a HOST-ONLY
    item — one declaring no `factory_captured` assertion, which therefore owes no
    factory record — that is the independent `host_verified` replay. Comparing such
    a pointer against the latest `verified` record compares two different kinds of
    record and reports a correct pointer as stale on every snapshot, naming as "the
    latest verified record" the very record the acceptance pass is required NOT to
    cite. That is a hygiene row an operator cannot clear: repairing the pointer to
    satisfy it would mean citing an unattributed record, which the evidence rule
    forbids. Scoping to the kind keeps the fact meaningful in BOTH directions — a
    newer `host_verified` replay, which is how a correction is published, still
    makes a host-only pointer stale.

    An UNREADABLE pointer whose verdict bullet is missing carries the empty string,
    which matches no record and yields no fact — the same answer an unreadable pull
    request gives, and the right one: the lane disposes on observed evidence, and a
    pointer nobody can read is evidence of nothing.
    """
    records = read_pull_request_records(
        repo=project_root, pr_number=pointer.pull_request, runner=runner
    )
    if records is None:
        return False
    latest = latest_proof_record(records=records, verdict=pointer.verdict)
    if latest is None:
        return False
    return latest.run_id != pointer.run_id or latest.url != pointer.record_url


def _pending_host_item(
    *, project_root: Path, repo: str, item: WorkItem, pointer: ProofPointer
) -> AttentionItem:
    """The host-leg row, naming the item, the pull request and the assertions.

    All three are the clause's own list and none substitutes for another: the item
    says which record to repair, the pull request says where the records go, and the
    assertions say what the host session has to capture. The INDEPENDENCE
    requirement rides in the summary too, because it is the whole content of the
    host leg — an operator who publishes both records from one session has done the
    work and cleared nothing.
    """
    assertions = effective_criteria(item=item).host_captured_assertions
    named = "; ".join(repr(assertion) for assertion in assertions)
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:pending-host-leg:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {item.id} rests in {_ACCEPTANCE_STATUS} awaiting an independent"
            f" host replay of {named}. Capture the proof on an operator host against the"
            f" RELEASED build and publish `{PROOF_RECORD_TITLE} — {VERDICT_HOST_RECORDED}"
            f" — session <session identity> — <UTC timestamp>` on pull request"
            f" #{pointer.pull_request} ({pointer.record_url}) naming the build identity"
            f" exercised; a DIFFERENT session identity then replays those steps and"
            f" publishes `{VERDICT_HOST_VERIFIED}`. The accept valve refuses the item"
            " until a host_verified record lists each assertion as reproduced."
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_inspect_command(project_root=project_root, item=item)
        ),
    )


def _pending_item(
    *, project_root: Path, repo: str, item: WorkItem, pointer: ProofPointer
) -> AttentionItem:
    assertions = effective_criteria(item=item).human_attested_assertions
    named = "; ".join(repr(assertion) for assertion in assertions)
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:pending-human-attestation:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {item.id} rests in {_ACCEPTANCE_STATUS} awaiting human"
            f" attestation of {named}. Post one new comment on pull request"
            f" #{pointer.pull_request} ({pointer.record_url}) whose first line is"
            f" `{PROOF_RECORD_TITLE} — {VERDICT_HUMAN_ATTESTED} — <human identity> —"
            " <UTC timestamp>`, carrying each assertion's steps and proof; the"
            " accept valve refuses the item until that record exists."
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_inspect_command(project_root=project_root, item=item)
        ),
    )


def _stale_item(
    *, project_root: Path, repo: str, item: WorkItem, pointer: ProofPointer
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:stale-proof-pointer:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {item.id} carries a STALE Proof of Done pointer: it names"
            f" run {pointer.run_id!r} and record {pointer.record_url}, which is not"
            f" the latest verified record on pull request #{pointer.pull_request}."
            " Re-read the pull request's records and repair the pointer section of"
            " the item's description."
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_inspect_command(project_root=project_root, item=item)
        ),
    )


def _inspect_command(*, project_root: Path, item: WorkItem) -> str:
    """Read the item's own record, which is the surface both repairs edit."""
    wrapper = Path(__file__).parents[2] / "bin" / "context.py"
    return (
        f"python3 {shlex.quote(str(wrapper))} "
        f"--project-root {shlex.quote(str(project_root))} {shlex.quote(item.id)} --json"
    )

"""The two Proof of Done hygiene lanes: a pending human leg, and a stale pointer.

Both facts are required by `SPECIFICATION/contracts.md` (v114). The
human-attested-leg clause says `needs-attention` MUST surface the pending leg as
an attention item carrying the pull request link; the pointer clause says a
pointer "whose run id or comment id does not match the latest record on the pull
request is stale and MUST be surfaced by `needs-attention` as a hygiene fact
naming the item and the pull request."

WHY NEITHER FACT ADVERTISES THE `accept` VALVE. The pending-leg fact exists
precisely because that valve REFUSES the item, so handing an operator
`accept:<id>` would hand them a command this very row says will fail — the
misdirecting-handoff defect the unrunnable-acceptance lane records. What the
operator is handed instead is the item's own record, because the thing they have
to do — post a Proof of Done record on the pull request — is not an action any
`drive` verb performs.

WHY THE STALE LANE READS THE FORGE AND THE PENDING LANE DOES NOT. Staleness is a
comparison between the pointer and the pull request's LATEST record, so there is
no way to decide it from the ledger alone; the pending leg, by contrast, is
answered entirely by the pointer the Dispatcher already wrote. The read is scoped
to items that have NOT closed and that carry a pointer, which bounds it to the
work in flight: a closed item's pointer is frozen history, and re-reading every
closed item's pull request on every snapshot would make the attention pass a
function of the whole ledger's size.

AN UNREADABLE PULL REQUEST IS NOT A STALE POINTER. A failed read and a pull
request carrying no `verified` record both yield NO fact, because the lane would
otherwise manufacture a staleness finding out of an absent observation — the same
rule the acceptance pass's evidence legs obey.
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
    VERDICT_HUMAN_ATTESTED,
    VERDICT_VERIFIED,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "pending_human_attestation_items",
    "stale_proof_pointer_items",
]

_ACCEPTANCE_STATUS = "acceptance"
_CLOSED_STATUS = "done"


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
    """Whether the pull request's latest verified record is not the one cited.

    Both the run id and the comment link are compared, because the clause names
    both and they fail independently: a re-dispatch publishes a record under a new
    RUN id, while a corrected record from the same run publishes under a new
    COMMENT id — and a check on either alone is blind to the other.
    """
    records = read_pull_request_records(
        repo=project_root, pr_number=pointer.pull_request, runner=runner
    )
    if records is None:
        return False
    latest = latest_proof_record(records=records, verdict=VERDICT_VERIFIED)
    if latest is None:
        return False
    return latest.run_id != pointer.run_id or latest.url != pointer.record_url


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

"""The record-or-reuse decision taken by repository preflight.

The shell preflight is a host transport concern: this module owns the judgement
decision itself so a fake comment store and a counting command runner can prove
that a prior repository-preflight verdict binds an unchanged later taking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import parse_adapter_string
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_record import (
    GoverningHeadingReceipt,
    governing_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
    reusable_governing_heading_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    DodJudgementDecision,
    judge_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingReader,
)
from livespec_orchestrator_beads_fabro.commands._dod_preflight_governing_reading import (
    PreflightGoverningReading,
    preflight_governing_heading_reading,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "RepositoryPreflightCommentStore",
    "preflight_dod_gate_candidates",
    "repository_preflight_governing_reading",
    "repository_preflight_reading",
]

_STAGE = "repository-preflight"


class RepositoryPreflightCommentStore(Protocol):
    """The append-only item comment sidecar the repository preflight receives."""

    def comments(self) -> tuple[str, ...]:
        """Return the item's comment bodies in their ledger order."""
        ...

    def append(self, *, body: str) -> None:
        """Append one durable preflight receipt to the item."""
        ...


def preflight_dod_gate_candidates(*, cwd: Path) -> tuple[AcpCandidate, ...] | None:
    """The `dod_gate` chain, bridging the legacy string form the gate no longer reads.

    The legacy string form predates candidate metadata. A recognisable Claude
    adapter in it is bridged into the same candidate resolver until the
    configuration is migrated, so a repository still carrying it is judged rather
    than reported as having no eligible model.
    """
    resolved = dod_gate_candidates(cwd=cwd)
    if resolved is not None:
        return resolved
    nodes: object = dispatcher_block(cwd=cwd).get("acp_nodes")
    entry: object = (
        cast("dict[str, object]", nodes).get("dod_gate") if isinstance(nodes, dict) else None
    )
    if not isinstance(entry, str):
        return None
    adapter = parse_adapter_string(text=entry)
    if "claude-agent-acp" in adapter.command:
        return (AcpCandidate(adapter=adapter, agent_id="claude-acp"),)
    return None


def _unobserved_governing_heading(*, item: WorkItem, repo: Path) -> None:
    """The governing-heading reader of a taking whose heading verdict is already settled."""
    del item, repo


def repository_preflight_reading(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    item: WorkItem,
    repo: Path,
    store: RepositoryPreflightCommentStore,
    runner: CommandRunner,
    payload_root: Path,
    governing_heading: GoverningHeadingReader | None = None,
    governing_observed: bool = True,
) -> DodJudgementDecision:
    """Reuse or take one repository-preflight Definition-of-Done judgement.

    `governing_observed` is False when the caller's own governing-heading taking
    could not be observed. That outage fails open and leaves no record, so this
    taking must not spawn the judge a second time for the verdict the caller has
    already settled; a recorded verdict is found through `store` either way.
    """
    if not governing_observed and governing_heading is None:
        governing_heading = _unobserved_governing_heading
    return judge_definition_of_done(
        item=item,
        repo=repo,
        stage=_STAGE,
        comments=store.comments(),
        append=store.append,
        runner=runner,
        payload_root=payload_root,
        governing_heading=governing_heading,
        candidate_resolver=preflight_dod_gate_candidates,
    )


def repository_preflight_governing_reading(
    *,
    item: WorkItem,
    repo: Path,
    store: RepositoryPreflightCommentStore,
    runner: CommandRunner,
) -> PreflightGoverningReading:
    """Take the governing-heading reading, recording a verdict this taking had to take.

    A verdict the component's reuse rule already allows decides and is not recorded
    again. A fresh one is appended BEFORE the rubric judgement runs, because that
    judgement reads the item's comments to reuse the verdict, and it appends its own
    record only when the rubric ran: without this record an outage of the rubric
    judge leaves the governing-heading taking unrecorded and the next launch re-takes
    it, which can flip the verdict on identical bytes.
    """
    comments = store.comments()
    reusable = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    reading = preflight_governing_heading_reading(
        item=item, repo=repo, comments=comments, runner=runner
    )
    if reusable is None and reading.verdict is not None:
        lines = [
            JUDGEMENT_COMMENT_MARKER,
            "",
            f"work-item: {item.id}",
            f"stage: {_STAGE}",
            *governing_record_lines(
                governing=GoverningHeadingReceipt(
                    verdict=reading.verdict,
                    subject_digest=governing_heading_subject_digest(item=item, comments=comments),
                )
            ),
        ]
        store.append(body="\n".join(lines))
    return reading

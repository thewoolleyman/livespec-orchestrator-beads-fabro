"""The needs-human ending leaves a DURABLE record on the item, not a rendering.

WHY A COMMENT AND NOT A RENDERER. `needs_human_question_summary` already shows
this ending in the attention lane, and it looked like the ledger surface the
clause asks for — but it re-inspects Fabro ON DEMAND. Its answer therefore
lasts exactly as long as the run record does: once the factory prunes the run,
or the factory is unreachable, or `fabro rm` reaps it, the lane renders a
default and the causal fault is gone from every surface at once. The clause
names "the item's ledger record", and the only thing on this tenant that
outlives the run is a comment. So the fault is WRITTEN, once, at the
escalation, and the attention rendering is kept beside it rather than replaced.

WHAT THE RECORD MAY NOT DO, which is most of what these cases assert. It must
not invent a stage for an ending that recorded none, must not classify a
transport fault the cause does not support, must not say a question awaits when
no agent asked, and must not say none awaits when one does. Each of those is a
claim a reader acts on, and the record outlives everything that could correct
it: `bd comments` offers add and list, with no edit and no delete.

TWO HAZARDS THE WRITE ITSELF CARRIES, both asserted below, and both arising
because the text is ENGINE-AUTHORED rather than ours.

A MiniJinja opener anywhere in a ledger comment makes every later dispatch of
that item refuse at the goal preflight — permanently, because the comment
cannot be repaired. An engine cause quoting a shell command is exactly where
one arrives, so the body is asserted to carry none, using the SAME detector the
dispatch preflight refuses on rather than a second pattern that could drift
from it. The record also says on its own face that the substitution is in
force, so a reader who sees a bracket form does not read it as the command the
agent actually ran.

And a `pr`-stage cause can quote a push against a tokenized origin URL, which
would put a live credential in an append-only record. The credential-shaped
value is replaced WHOLESALE rather than partially, which is the fleet's
fail-closed policy for exactly this shape.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
    record_needs_human_cause,
)
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
    UNESTABLISHED,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import REDACTION_MARKER
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.work_items.types import StoredBlockedReason, WorkItemStatus

_ITEM = "bd-ib-anfa5t"
_RUN = "01M44F9E56XCEWZNMVJX4M14Z6"
_VALVE = f"`resolve-blocked:{_ITEM}:ready`"
_STAGES_FIELD = "needs_human_stages"

# The measured backgrounded-tool cause, in the engine's own wording. The
# command sits INSIDE the engine's prose, which is why a surface that merely
# echoed the cause would satisfy "names the command" while classifying nothing.
_COMMAND = "git push --force-with-lease origin HEAD:feat/bd-ib-anfa5t"
_TASK = "task_7"
_CAUSE = (
    f"ACP tool call call_1 ({_COMMAND}) continued in background as task {_TASK}; "
    "Fabro terminated the turn"
)
_SIGNATURE = "pr|deterministic|acp turn failed"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(project_root: Path) -> None:
    _ = (project_root / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )


def _item(
    *,
    status: WorkItemStatus = "active",
    blocked_reason: StoredBlockedReason | None = None,
) -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status=status,
        title="Preserve causal ACP transport faults through needs_human terminals",
        description="A transport fault is not a question.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-08T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason=blocked_reason,
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _outcome(
    *,
    kind: str,
    stages: tuple[str, ...] | None = None,
    cause: str | None = None,
    category: str | None = None,
    signature: str | None = None,
    provider: str | None = None,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM,
        status="blocked",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="rendered elsewhere; this case is about the durable record",
        fabro_run_id=_RUN,
        fabro_failure_cause=cause,
        fabro_failure_category=category,
        fabro_failure_signature=signature,
        provider_usage_limit=provider is not None,
        provider_usage_limit_provider=provider,
        needs_human_kind=kind,
        **{_STAGES_FIELD: stages},
    )


def _recorded(*, tmp_path: Path, outcome: DispatchOutcome) -> str:
    """Write the record, then read it back off the item through the store seam.

    The read is `read_work_item_comments`, which indexes the beads-native
    `text` key. That is the point of reading it back rather than asserting the
    rendered return value: a record this function cannot find on the item is
    not a durable ledger record, however well it rendered.
    """
    _write_config(tmp_path)
    append_work_item(path=_config(), item=_item())
    record_needs_human_cause(
        repo=tmp_path,
        item=_item(),
        outcome=outcome,
        journal=_RecordingJournal(),
    )
    bodies = [
        comment.text
        for comment in read_work_item_comments(path=_config(), work_item_id=_ITEM)
        if NEEDS_HUMAN_CAUSE_MARKER in comment.text
    ]
    assert len(bodies) == 1
    return bodies[0]


def _assert_field_exists() -> None:
    """The causal stages the record names, asserted before an outcome uses them."""
    names = {entry.name for entry in dataclasses.fields(DispatchOutcome)}
    assert _STAGES_FIELD in names


def test_a_backgrounded_tool_fault_is_persisted_on_the_item(tmp_path: Path) -> None:
    """The fault arm: stage, innermost cause, classification and the command."""
    _assert_field_exists()

    body = _recorded(
        tmp_path=tmp_path,
        outcome=_outcome(
            kind=STAGE_FAILURE,
            stages=("pr",),
            cause=_CAUSE,
            category="deterministic",
            signature=_SIGNATURE,
        ),
    )

    assert "pr" in body
    assert _CAUSE in body
    assert "backgrounded-tool" in body
    # The command named AS a command, on its own labelled line — not merely
    # present because the quoted cause happens to contain it.
    assert f"backgrounded command: {_COMMAND}" in body
    assert f"backgrounded task: {_TASK}" in body
    assert "deterministic" in body
    assert _SIGNATURE in body
    assert "no answer is owed" in body
    assert _VALVE in body


def test_a_genuine_request_record_claims_no_fault(tmp_path: Path) -> None:
    """The request arm: a question awaits, and nothing is attributed to a stage."""
    _assert_field_exists()

    body = _recorded(tmp_path=tmp_path, outcome=_outcome(kind=AGENT_REQUEST))

    assert "an agent asked" in body
    assert _VALVE in body
    assert "transport fault" not in body
    assert "failed stage" not in body
    assert "no answer is owed" not in body


def test_an_unestablished_record_claims_neither_ending(tmp_path: Path) -> None:
    """The third arm: says the record grounds neither answer rather than picking."""
    _assert_field_exists()

    body = _recorded(tmp_path=tmp_path, outcome=_outcome(kind=UNESTABLISHED))

    assert "does not establish" in body
    assert "transport fault" not in body
    assert "failed stage" not in body
    assert "an agent asked" not in body


def test_a_fault_with_no_classifiable_cause_invents_none(tmp_path: Path) -> None:
    """A stage fault whose cause is not a transport fault classifies nothing.

    The guard against the opposite failure the item names: do NOT treat every
    ACP failure as a backgrounded tool. The stage and the cause are still
    reported, because those were measured; the classification is not, because
    it was not.
    """
    _assert_field_exists()

    body = _recorded(
        tmp_path=tmp_path,
        outcome=_outcome(
            kind=STAGE_FAILURE,
            stages=("implement",),
            cause="the merge gate timed out waiting on required checks",
            category="transient_infra",
        ),
    )

    assert "implement" in body
    assert "the merge gate timed out waiting on required checks" in body
    assert "transport fault" not in body
    assert "backgrounded command" not in body


def test_a_provider_ceiling_survives_onto_the_record(tmp_path: Path) -> None:
    """The vendor that refused is named, because the next dispatch acts on it."""
    _assert_field_exists()

    body = _recorded(
        tmp_path=tmp_path,
        outcome=_outcome(
            kind=STAGE_FAILURE,
            stages=("implement",),
            cause="Claude usage limit reached",
            category="transient_infra",
            provider="anthropic",
        ),
    )

    assert "anthropic" in body
    assert "provider" in body


def test_an_engine_cause_cannot_poison_the_item_it_is_written_to(tmp_path: Path) -> None:
    """No MiniJinja opener survives into the body, by the preflight's own detector."""
    _assert_field_exists()
    hostile = (
        "ACP tool call call_1 (echo {{ env.TOKEN }} {% raw %} {# c #}) continued in background"
    )

    body = _recorded(
        tmp_path=tmp_path,
        outcome=_outcome(kind=STAGE_FAILURE, stages=("pr",), cause=hostile),
    )

    assert minijinja_openers_in_text(source="record", text=body) == ()
    # And the reader is told the rewrite happened, so a bracket form is not
    # mistaken for what the agent actually ran.
    assert "rewritten" in body


def test_a_credential_shaped_cause_is_redacted_wholesale(tmp_path: Path) -> None:
    """A tokenized push URL never reaches the append-only record."""
    _assert_field_exists()
    secret = "ghs_livesecrettokenvalue"
    cause = (
        f"ACP tool call call_1 (git push https://x-access-token:{secret}@github.com/o/r) "
        "continued in background as task task_9"
    )

    body = _recorded(
        tmp_path=tmp_path,
        outcome=_outcome(kind=STAGE_FAILURE, stages=("pr",), cause=cause),
    )

    assert secret not in body
    assert REDACTION_MARKER in body


def test_a_non_needs_human_outcome_writes_nothing(tmp_path: Path) -> None:
    """Only a needs-human ending leaves this record.

    Asserted because the writer runs inside the shared post-run disposition
    sequence, which every outcome passes through. A record on a green or failed
    outcome would be an attribution about an ending that never happened.
    """
    _write_config(tmp_path)
    append_work_item(path=_config(), item=_item())

    record_needs_human_cause(
        repo=tmp_path,
        item=_item(),
        outcome=DispatchOutcome(
            work_item_id=_ITEM,
            status="green",
            stage="done",
            pr_number=7,
            merge_sha="deadbeef",
            detail="merged",
        ),
        journal=_RecordingJournal(),
    )

    assert read_work_item_comments(path=_config(), work_item_id=_ITEM) == ()

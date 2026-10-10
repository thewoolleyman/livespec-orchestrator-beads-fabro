"""The typed `next_action` pointer, and the resume directive it decides.

Per contracts.md's "Typed next_action and last_session", an open plan epic's
`next_action` metadata is the single authority on what happens next: an
object carrying exactly `kind`, `ref` and `text`, beside a `last_session`
string naming who wrote it and when. Both are updated IN PLACE, because they
point at the NEXT step rather than recording the steps taken, and both are
written only through the plan primitives — `append_handoff`,
`append_supervisor_handoff`, and `set_next_action` here.

The resume directive reads that object and nothing else. It used to derive an
unattended session's next action by scanning the newest handoff comment for a
line beginning `next action:`; ordinary line wrapping truncated that
instruction twice on a live tenant, deleting a constraint in one case and the
factory route in the other, while the directive reported one confident action
either way. A typed object has no wrap to truncate. A prose marker line MAY
still appear in a handoff body for a human reader, but it carries no authority
here: when the two disagree, the metadata wins.

Refusing to ask stays a tracked case. It requires one of the executable kinds,
a non-empty `ref`, an observable unsatisfied required result, and an unexpired
budget. An unattended resume may take that action directly. An attended resume
also requires a current recorded continuation ruling; without one, it offers
the recorded action as the picker default. `human`, `none`, an empty ref, an
unknown kind, or an absent pointer always falls back to the picker.

ONE MORE WAY TO ASK, AND IT PRE-EMPTS THE POINTER. A plan epic carrying no
Definition of Done section is reported by EVERY resume, and an unattended one
sets `next_action` to `kind: human` naming the gap rather than authoring the
maintainer's assertions for them — UNLESS the pointer is already `kind: impl`,
which it still takes. That carve-out is the whole reason the gap check runs
BEFORE the dispatch decision rather than instead of it: an `impl` pointer names
work already filed and admitted, and overwriting it would strand a live dispatch
behind a question no unattended session can answer. A `spec-op` pointer is
replaced, because a plan that has not said what done means has nothing for a
spec operation to ratify toward.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import ResultObservation

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "ARCHIVE_KIND",
    "AWAIT_KIND",
    "HUMAN_KIND",
    "IMPL_KIND",
    "LAST_SESSION_METADATA_KEY",
    "LEGACY_TRACKING",
    "NEXT_ACTION_KINDS",
    "NEXT_ACTION_METADATA_KEY",
    "NONE_KIND",
    "PLAN_RESUME_ACTOR",
    "PROOF_KIND",
    "REVIEW_KIND",
    "SPEC_OP_KIND",
    "NextAction",
    "ResumeDirective",
    "dispatchable_action_id",
    "next_action_metadata",
    "parse_next_action",
    "plan_record_metadata",
    "read_next_action",
    "resume_directive",
    "set_next_action",
]

NEXT_ACTION_METADATA_KEY = "next_action"
LAST_SESSION_METADATA_KEY = "last_session"

IMPL_KIND = "impl"
SPEC_OP_KIND = "spec-op"
PROOF_KIND = "proof"
REVIEW_KIND = "review"
ARCHIVE_KIND = "archive"
AWAIT_KIND = "await"
HUMAN_KIND = "human"
NONE_KIND = "none"

NEXT_ACTION_KINDS: tuple[str, ...] = (IMPL_KIND, SPEC_OP_KIND, HUMAN_KIND, NONE_KIND)

_DISPATCHABLE_KINDS: tuple[str, ...] = (
    IMPL_KIND,
    SPEC_OP_KIND,
    PROOF_KIND,
    REVIEW_KIND,
    ARCHIVE_KIND,
    AWAIT_KIND,
)
_KIND_FIELD = "kind"
_REF_FIELD = "ref"
_TEXT_FIELD = "text"
_REQUIRED_RESULT_FIELD = "required_result"
_BUDGET_FIELD = "budget"
_METADATA_FIELD = "metadata"
# The reserved author literal the resume signs its own gap pointer with,
# computed here rather than accepted from a caller — the same reservation
# `archive_thread` makes for `plan-archive` and `append_supervisor_handoff`
# for `<slug>-supervisor`. The resume writes this pointer on its OWN behalf,
# so no session identity is the honest author of it.
PLAN_RESUME_ACTOR = "plan-resume"


class _LegacyTracking:
    """Sentinel distinguishing a legacy three-key pointer from explicit null."""


LEGACY_TRACKING = _LegacyTracking()


@dataclass(frozen=True, kw_only=True)
class NextAction:
    """The typed pointer to a plan's next step.

    `kind` is one of `NEXT_ACTION_KINDS`. For `impl` the `ref` is one
    work-item id, so the action executes as the `drive` operation's
    `impl:<ref>` action-id; for `spec-op` the `ref` is already an
    `<operation>:<topic>` action-id. `human` MAY carry a ref naming the
    question, and `none` MUST carry none. `text` is one imperative sentence a
    person can read without any other context.
    """

    kind: str
    ref: str
    text: str
    required_result: object = LEGACY_TRACKING
    budget: object = LEGACY_TRACKING


@dataclass(frozen=True, kw_only=True)
class ResumeDirective:
    """Whether a resume asks which action to take, and what it takes instead.

    `findings` carries what this resume must REPORT regardless of which action
    it takes — today, a missing plan Definition of Done section. It is separate
    from `reason` because the two answer different questions: `reason` explains
    the picker decision, and a finding is owed even when no picker is raised.
    Defaulted to empty so every existing construction stays valid.
    """

    ask: bool
    next_action: str | None
    reason: str
    findings: tuple[str, ...] = ()
    # Added after the original three-field directive shipped.  Equality omits
    # the presentation-only default so legacy callers comparing directives keep
    # their meaning; callers that render the picker read this field directly.
    picker_default: str | None = field(default=None, compare=False)
    observation: ResultObservation | None = None


def next_action_metadata(
    *,
    existing_metadata: dict[str, Any],
    action: NextAction,
    session: str,
    now: str,
) -> dict[str, Any]:
    """Overlay the typed pointer and its authorship onto an epic's metadata.

    The whole `next_action` object is rewritten on every call. `bd update
    --metadata` merges at the TOP level but replaces a nested object WHOLESALE,
    so a partial nested write silently destroys the sub-keys it omits; carrying
    all three keys every time is what makes that merge harmless here.
    """
    metadata = dict(existing_metadata)
    pointer: dict[str, object] = {
        _KIND_FIELD: action.kind,
        _REF_FIELD: action.ref,
        _TEXT_FIELD: action.text,
    }
    metadata[NEXT_ACTION_METADATA_KEY] = pointer
    metadata[LAST_SESSION_METADATA_KEY] = f"{session} at {now}"
    return metadata


def parse_next_action(*, value: object) -> NextAction | None:
    """Read one `next_action` metadata value, or None when absent or ill-typed.

    An absent pointer and an ill-typed one are deliberately the same answer to
    this reader: both mean there is nothing a resume may act on. Naming the
    typing violation is the conformance checks' job, not the resume path's.
    """
    if not isinstance(value, dict):
        return None
    fields = cast("dict[str, Any]", value)
    kind = fields.get(_KIND_FIELD)
    ref = fields.get(_REF_FIELD)
    text = fields.get(_TEXT_FIELD)
    if not isinstance(kind, str) or not isinstance(ref, str) or not isinstance(text, str):
        return None
    if _REQUIRED_RESULT_FIELD in fields and _BUDGET_FIELD in fields:
        return NextAction(
            kind=kind,
            ref=ref,
            text=text,
            required_result=fields[_REQUIRED_RESULT_FIELD],
            budget=fields[_BUDGET_FIELD],
        )
    return NextAction(kind=kind, ref=ref, text=text)


def dispatchable_action_id(*, action: NextAction) -> str | None:
    """Return the action id an unattended resume executes, or None for the picker."""
    ref = action.ref.strip()
    if action.kind not in _DISPATCHABLE_KINDS or ref == "":
        return None
    if action.kind == IMPL_KIND:
        return f"{IMPL_KIND}:{ref}"
    if action.kind == SPEC_OP_KIND:
        return ref
    return f"{action.kind}:{ref}"


def read_next_action(*, config: StoreConfig, epic_id: str) -> NextAction | None:
    """Read one epic's typed `next_action`, or None when it carries none."""
    client = make_beads_client(config=config)
    record = client.show_issue(issue_id=epic_id)
    return parse_next_action(
        value=plan_record_metadata(record=record).get(NEXT_ACTION_METADATA_KEY)
    )


def set_next_action(
    *,
    config: StoreConfig,
    epic_id: str,
    action: NextAction,
    session: str,
    now: str,
) -> None:
    """Update one epic's `next_action` and `last_session` metadata in place."""
    client = make_beads_client(config=config)
    record = client.show_issue(issue_id=epic_id)
    client.update_issue(
        issue_id=epic_id,
        metadata=next_action_metadata(
            existing_metadata=plan_record_metadata(record=record),
            action=action,
            session=session,
            now=now,
        ),
    )


def resume_directive(*, config: StoreConfig, epic_id: str, unattended: bool) -> ResumeDirective:
    """Delegate the resume decision to its cohesive reconciliation module."""
    from livespec_orchestrator_beads_fabro.commands._plan_resume import decide_plan_resume

    return decide_plan_resume(config=config, epic_id=epic_id, unattended=unattended)


def plan_record_metadata(*, record: BeadsRecord) -> dict[str, Any]:
    """Return a record's metadata, tolerating the key's absence.

    Beads records are `omitempty`-sparse: a record holding no metadata omits
    the key entirely rather than carrying an empty object, so indexing it
    raises on exactly the epic that has never been written to.
    """
    metadata = record.get(_METADATA_FIELD)
    if not isinstance(metadata, dict):
        return {}
    return dict(cast("dict[str, Any]", metadata))

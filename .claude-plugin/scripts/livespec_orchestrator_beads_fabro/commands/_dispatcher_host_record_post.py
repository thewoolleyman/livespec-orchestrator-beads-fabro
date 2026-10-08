"""The posting primitive: the one route by which a host-leg proof record is published.

The host-leg clause of `SPECIFICATION/contracts.md` (v115) requires "one posting
primitive that renders these records, so that no session hand-formats one"; that the
primitive "MUST compute the publishing identity itself — the invoking agent session's
id, or the forge login for a human — and MUST NOT accept it as a caller-supplied
string"; that it "MUST refuse a `host_verified` or `host_not_reproduced` post whose
computed identity equals that of the `host_recorded` record it replays"; and that "on
publishing `host_verified` or `host_not_reproduced`, it MUST drive `reconcile-merged
--item <id>` ... which re-runs the acceptance pass".

WHAT THE CALLER SUPPLIES, AND WHAT IT CANNOT. The caller hands in only the evidence it
alone holds: the build it exercised, and per assertion the steps it ran, the proof they
produced, and whether they reproduced. Everything the clause makes a REQUIREMENT of the
record is computed here — the header shape, the publishing identity, the UTC timestamp,
the target pull request, and each assertion's declared proof MODE. Two of those matter
beyond tidiness: a caller that could supply the MODE could publish a
`factory_captured` assertion as a host one and have the acceptance pass grade it on the
host leg, and a caller that could supply the IDENTITY could defeat the independence
refusal with a flag, which would reduce the whole "independent party" guarantee to a
naming convention.

WHY THE TARGET IS RESOLVED RATHER THAN NAMED. Host records "MUST be published on the
pull request of the latest merged run for the item; a host record on an earlier pull
request ... is not evidence". A `--pull-request` flag would make publishing onto the
wrong one a typo away, and the resulting record would be refused by the acceptance pass
for a reason the publisher could not see from the post's own success. So the merge is
resolved through the same `resolve_merged_pr` the reconcile valve uses — one resolution
authority, rather than two that could name two different pull requests.

WHY EVERY REFUSAL FIRES BEFORE THE POST, which is the ordering this module exists to
guarantee. A record comment "MUST NOT be edited after posting; a correction is a new
record", so a refusal that fired AFTER the forge call would leave the very record the
clause calls not-evidence permanently on the pull request, where the acceptance pass
would read it, refuse it, and report a refusal the publisher then cannot retract. The
refusal ladder therefore completes — identity, host leg, payload, capture — before any
`gh pr comment` runs, and the primitive's tests assert the ABSENCE of that call for
each one.

WHY A CAPTURE DOES NOT DRIVE THE RECONCILE. The clause names only `host_verified` and
`host_not_reproduced`, and the asymmetry is real rather than an omission: a capture
changes no verdict — the assertion stays pending until an independent replay lands — so
re-running the pass for one would spend an acceptance cycle to reach the identical
answer. Only a replay can move the item.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_leg import REPLAY_VERDICTS
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_payload import (
    Evidence,
    read_evidence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    NO_GOVERNING_SCENARIO,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_target import (
    host_record_target,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import load_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_budget import (
    record_budget_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_identity import (
    computed_publishing_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_HOST_RECORDED,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "HOST_RECORD_STAGE",
    "HOST_RECORD_SURFACE",
    "NO_CAPTURE_REFUSAL",
    "NO_IDENTITY_REFUSAL",
    "SELF_REPLAY_REFUSAL",
    "HostRecordPost",
    "host_record_argv",
    "run_post_host_record_command",
]

HOST_RECORD_STAGE = "host-record-post"
# The command name every refusal below names, and the one the shared payload read
# renders into its own. PUBLIC so the plan surface's sibling constant sits beside a
# named peer rather than beside a literal nobody can find from the other module.
HOST_RECORD_SURFACE = "post-host-record"
NO_IDENTITY_REFUSAL = "no publishing identity could be computed for this invocation"
SELF_REPLAY_REFUSAL = "the computed identity equals the identity that recorded the capture"
NO_CAPTURE_REFUSAL = "no host_recorded record on the pull request for this replay to replay"

# Every refusal this primitive can emit, as a template formatted at its site. Module
# level for the reason the reconcile valve's refusals are: a refusal is operator-facing
# prose that wants reading as a whole, and interleaving it with the control flow makes
# both harder to follow. Each one names what would clear it.
_NO_ITEM_REFUSAL = "ERROR: post-host-record refused: no work-item {item_id}\n"
_NO_HOST_LEG_REFUSAL = (
    "ERROR: post-host-record refused: work-item {item_id} declares no host_captured"
    " assertion, so it owes no host record.\n"
)
_NO_TARGET_REFUSAL = (
    "ERROR: post-host-record refused: no single merged pull request resolves for"
    " work-item {item_id}, so there is no target for its host record.\n"
)
_IDENTITY_REFUSAL_TEXT = "ERROR: post-host-record refused: {reason}.\n"
_POST_FAILED_TEXT = (
    "ERROR: post-host-record failed: the forge refused the comment on pull request"
    " #{pr_number}; nothing was published and no acceptance pass was re-run.\n"
)
_UNREADABLE_PULL_REQUEST_REFUSAL = (
    "ERROR: post-host-record refused: pull request #{pr_number} comments could not be"
    " read, so the capturing identity this replay must differ from is unknown. A replay"
    " is not published against an unread pull request.\n"
)
_NO_CAPTURE_REFUSAL_TEXT = (
    "ERROR: post-host-record refused: {reason} (pull request #{pr_number}). Publish the"
    " {capture} capture first.\n"
)
_SELF_REPLAY_REFUSAL_TEXT = (
    "ERROR: post-host-record refused: {reason} ({identity}), so this post would not be"
    " evidence. The {capture} record it replays is {url}. A DIFFERENT session identity"
    " must replay those steps.\n"
)

_POST_TIMEOUT_SECONDS = 60.0
_EXIT_REFUSED = 3
_EXIT_FAILED = 1


@dataclass(frozen=True, kw_only=True)
class HostRecordPost:
    """One invocation of the posting primitive: what to publish, and for which item."""

    repo: Path
    work_item_id: str
    verdict: str
    record_path: Path


@dataclass(frozen=True, kw_only=True)
class _Seams:
    """The four injected seams one invocation runs through.

    Bundled because the publish step needs all four and a function taking them loose
    exceeds this tree's argument ceiling. They travel together naturally: each is a
    boundary the primitive is exercised across, and no step needs a subset.
    """

    runner: CommandRunner
    env: Mapping[str, str]
    emit: Callable[[str], None]
    reconcile: Callable[..., int]


def host_record_argv(*, pr_number: int, body_file: Path) -> list[str]:
    """The forge call that posts one record as a NEW comment on the pull request.

    `--body-file` rather than `--body`: a record carries fenced proof output that
    routinely runs to thousands of characters, and an argv-borne body hits the
    platform's argument limit with an error that names the limit rather than the
    record. The file is also what the primitive echoes, so what was posted and what was
    reported are one artifact.
    """
    return ["gh", "pr", "comment", str(pr_number), "--body-file", str(body_file)]


def run_post_host_record_command(
    *,
    post: HostRecordPost,
    runner: CommandRunner,
    env: Mapping[str, str],
    emit: Callable[[str], None],
    reconcile: Callable[..., int],
) -> int:
    """Publish one host-leg record, refusing before the post whenever it must.

    `reconcile` is injected rather than imported so the primitive can be exercised
    without running a real acceptance pass, and so the ONE production wiring of it
    lives at the CLI boundary where every other subcommand's wiring lives.
    """
    item = _item(repo=post.repo, work_item_id=post.work_item_id)
    if item is None:
        emit(_NO_ITEM_REFUSAL.format(item_id=post.work_item_id))
        return _EXIT_REFUSED
    declared = _declared_modes(item=item)
    if not declared:
        emit(_NO_HOST_LEG_REFUSAL.format(item_id=item.id))
        return _EXIT_REFUSED
    evidence = read_evidence(
        record_path=post.record_path,
        work_item_id=f"work-item {post.work_item_id}",
        declared=declared,
        verdict_is_replay=post.verdict in REPLAY_VERDICTS,
        surface=HOST_RECORD_SURFACE,
        # The ITEM clause requires "the governing scenario ... or the statement that
        # no scenario governs it", so an absent field is a publisher who did not say
        # and renders the statement. The plan surface passes `None`.
        scenario_fallback=NO_GOVERNING_SCENARIO,
        emit=emit,
    )
    if evidence is None:
        return _EXIT_REFUSED
    return _publish(
        post=post,
        item=item,
        evidence=evidence,
        seams=_Seams(runner=runner, env=env, emit=emit, reconcile=reconcile),
    )


def _publish(*, post: HostRecordPost, item: WorkItem, evidence: Evidence, seams: _Seams) -> int:
    """Clear the RESOLUTION half of the ladder, then hand the record to the post.

    Split from `_render_and_post` along the seam between the refusals that are
    answerable BEFORE a record exists — who is publishing, onto which pull request,
    and against which capture — and the one that can only be answered AFTER it has
    been rendered, because it measures the rendered bytes. Keeping the two in one
    function put it over this tree's return-statement ceiling, and the ceiling was
    right: the resolution ladder reads as one sequence, and the size measurement is
    not part of it.
    """
    runner = seams.runner
    emit = seams.emit
    identity = computed_publishing_identity(repo=post.repo, env=seams.env, runner=runner)
    if identity is None:
        emit(_IDENTITY_REFUSAL_TEXT.format(reason=NO_IDENTITY_REFUSAL))
        return _EXIT_REFUSED
    pr_number = host_record_target(repo=post.repo, item=item, runner=runner)
    if pr_number is None:
        emit(_NO_TARGET_REFUSAL.format(item_id=item.id))
        return _EXIT_REFUSED
    refusal = _replay_refusal(
        post=post, pr_number=pr_number, identity=identity.identity, runner=runner
    )
    if refusal is not None:
        emit(refusal)
        return _EXIT_REFUSED
    return _render_and_post(
        post=post,
        item=item,
        evidence=evidence,
        seams=seams,
        header_field=identity.header_field,
        pr_number=pr_number,
    )


def _render_and_post(
    *,
    post: HostRecordPost,
    item: WorkItem,
    evidence: Evidence,
    seams: _Seams,
    header_field: str,
    pr_number: int,
) -> int:
    """Render the record, bound it against the budget, post it, drive the reconcile.

    `header_field` and `pr_number` arrive already RESOLVED rather than as the values
    they were resolved from, so this half cannot re-resolve either and reach a
    different answer than the refusals upstream were cleared against.
    """
    emit = seams.emit
    body = render_proof_record(
        title=PROOF_RECORD_TITLE,
        verdict=post.verdict,
        identity=header_field,
        timestamp=_utc_now_iso(),
        build=evidence.build,
        assertions=evidence.assertions,
    )
    # The LAST refusal before the post, and deliberately so: it measures the exact
    # bytes `_posted` would send, which only exist once everything above has been
    # resolved and rendered. It is also the only refusal here whose failure mode is
    # silent — every other one names a record or an identity a reader can go and
    # look at, while a rejected comment leaves nothing behind at all.
    over_budget = record_budget_refusal(
        body=body, surface=HOST_RECORD_SURFACE, assertions=evidence.assertions
    )
    if over_budget is not None:
        emit(over_budget)
        return _EXIT_REFUSED
    emit(body)
    if not _posted(post=post, pr_number=pr_number, body=body, runner=seams.runner):
        emit(_POST_FAILED_TEXT.format(pr_number=pr_number))
        return _EXIT_FAILED
    if post.verdict not in REPLAY_VERDICTS:
        return 0
    return seams.reconcile(work_item_id=item.id)


def _item(*, repo: Path, work_item_id: str) -> WorkItem | None:
    """The named item from the repository's ledger, or `None` when it was never filed.

    `load_items` is the Dispatcher's own ledger read, reused rather than re-rolled so
    the primitive sees the same tenant, through the same backend selection, as the
    acceptance pass whose verdict its post re-runs.
    """
    return next((one for one in load_items(repo=repo) if one.id == work_item_id), None)


def _declared_modes(*, item: WorkItem) -> dict[str, str]:
    """Each host-captured assertion the item declares, mapped to its proof mode.

    A MAPPING rather than a set because the mode is what the record publishes, and
    computing it here is what stops a caller declaring one: the record can only ever
    carry the mode the item's own Definition of Done assigned.
    """
    criteria = effective_criteria(item=item)
    host = set(criteria.host_captured_assertions)
    return {
        text: mode
        for text, mode in zip(criteria.assertions, criteria.proof_modes, strict=True)
        if text in host
    }


def _replay_refusal(
    *, post: HostRecordPost, pr_number: int, identity: str, runner: CommandRunner
) -> str | None:
    """The refusal a REPLAY earns from the records already on the pull request.

    A capture earns none: it is the first leg, there is nothing for it to collide with,
    and requiring one would make the first host record of every item unpublishable.
    """
    if post.verdict not in REPLAY_VERDICTS:
        return None
    records = read_pull_request_records(repo=post.repo, pr_number=pr_number, runner=runner)
    if records is None:
        return _UNREADABLE_PULL_REQUEST_REFUSAL.format(pr_number=pr_number)
    capture = latest_proof_record(records=records, verdict=VERDICT_HOST_RECORDED)
    if capture is None:
        return _NO_CAPTURE_REFUSAL_TEXT.format(
            reason=NO_CAPTURE_REFUSAL, pr_number=pr_number, capture=VERDICT_HOST_RECORDED
        )
    if capture.run_id != identity:
        return None
    return _SELF_REPLAY_REFUSAL_TEXT.format(
        reason=SELF_REPLAY_REFUSAL,
        identity=identity,
        capture=VERDICT_HOST_RECORDED,
        url=capture.url,
    )


def _posted(*, post: HostRecordPost, pr_number: int, body: str, runner: CommandRunner) -> bool:
    """Write the body to a file and post it as a new comment, reporting success."""
    target = post.repo / "tmp" / f"host-record-{post.work_item_id}-{post.verdict}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(body, encoding="utf-8")
    result = runner.run(
        argv=host_record_argv(pr_number=pr_number, body_file=target),
        cwd=post.repo,
        timeout_seconds=_POST_TIMEOUT_SECONDS,
    )
    return result.exit_code == 0


def _utc_now_iso() -> str:
    """The record header's UTC timestamp, computed rather than accepted."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

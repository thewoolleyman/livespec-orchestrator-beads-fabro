"""The ONE route by which a plan Proof of Done record reaches its epic.

The plan-record clause of `SPECIFICATION/contracts.md` (v115) requires that "the
implementation MUST provide one posting primitive that renders plan records, so
that no session hand-formats one"; that it "MUST compute the publishing identity
itself — the invoking agent session's id, or the forge login for a human — never
accept it as a caller-supplied string"; and that it "MUST refuse a `verified`
post whose computed identity equals that of the `captured` record it replays".

WHAT THE CALLER SUPPLIES, AND WHAT IT CANNOT. The caller hands in only the
evidence it alone holds: the build it exercised, and per assertion the steps it
ran, the proof they produced, and whether they reproduced. Everything the clause
makes a REQUIREMENT of the record is computed here — the header shape, the
publishing identity, the UTC timestamp, the target epic, and each assertion's
declared proof MODE. The last two matter beyond tidiness: a caller that could
supply the MODE could publish a `human_attested` plan assertion as a
host-captured one, and the archive gate would then grade it on the wrong leg;
and a caller that could supply the IDENTITY could defeat the independence
refusal with a flag, which reduces the whole "party with no role in the plan's
implementation" guarantee to a naming convention.

WHY A PLAN RECORD GOES ON THE EPIC AND AN ITEM RECORD ON A PULL REQUEST, which
is the reason this is a separate primitive rather than a flag on the host one. A
plan has no merged run and no pull request; its record is an append-only comment
on the plan epic. So there is no merge to resolve and no containment to check —
what the plan clause substitutes for that is the RELEASE identity, and the
ARCHIVE GATE checks that (`_plan_proof_leg`), not the post. The RENDER is shared
(`_dispatcher_host_record_render`) because the body structure is identical and a
second renderer would be a second place to get that module's two placement traps
wrong.

WHY EVERY REFUSAL FIRES BEFORE THE APPEND. A record comment must not be edited
after posting; a correction is a new record. A refusal that fired AFTER the
append would leave the very record the clause calls not-evidence permanently on
the epic, where the archive gate would read it, reject it, and report a rejection
the publisher could not see from the post's own success. The ladder therefore
completes — epic, section, payload, identity, capture — before anything is
appended, and this module's tests assert the comment count rather than the exit
code for each one.

WHY A CAPTURE OWES NO PRIOR RECORD. A `captured` record is the FIRST leg: there
is nothing for it to collide with, and requiring a predecessor would make the
first record of every plan unpublishable. A `verified` or `not_reproduced` post
is a replay and owes one, which is also what gives the independence refusal an
identity to compare against.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_payload import (
    Evidence,
    read_evidence,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_identity import (
    computed_publishing_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import VERDICT_CAPTURED
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    plan_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
    PLAN_REPLAY_VERDICTS,
    latest_plan_proof_entry,
    plan_proof_entries,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "PLAN_RECORD_SURFACE",
    "PlanRecordPost",
    "run_post_plan_record_command",
]

# The command name every refusal below names, and the one the shared payload read
# renders into its own messages.
PLAN_RECORD_SURFACE = "post-plan-record"

# Every refusal this primitive can emit, as a template formatted at its site.
# Module level for the reason the host primitive's are: a refusal is
# operator-facing prose that wants reading as a whole, and interleaving it with
# the control flow makes both harder to follow. Each one names what would clear it.
_NO_EPIC_REFUSAL = "ERROR: post-plan-record refused: no work-item {epic_id} in this tenant.\n"
_NO_SECTION_REFUSAL = (
    "ERROR: post-plan-record refused: epic {epic_id} carries no gradeable Definition"
    " of Done section, so a plan record has no assertions to publish. Author the"
    " section with the maintainer's own statement of what done means first.\n"
)
_NO_IDENTITY_REFUSAL = (
    "ERROR: post-plan-record refused: no publishing identity could be computed for"
    " this invocation. A record that cannot name its publisher is not publishable.\n"
)
_NO_CAPTURE_REFUSAL = (
    "ERROR: post-plan-record refused: epic {epic_id} carries no captured plan Proof"
    " of Done record for this {verdict} post to replay. Publish the capture first.\n"
)
_SELF_VERIFIED_REFUSAL = (
    "ERROR: post-plan-record refused: the computed identity ({identity}) equals the"
    " identity that captured the steps this {verdict} post replays, so the post"
    " would not be evidence. A DIFFERENT session identity must replay them.\n"
)

_EXIT_REFUSED = 3


@dataclass(frozen=True, kw_only=True)
class PlanRecordPost:
    """One invocation of the plan posting primitive: what to publish, for which plan.

    `repo` is carried for the identity computation alone — the forge-login arm
    runs `gh` in a repository — and never to resolve a target: a plan record's
    target is its epic, which `epic_id` names.
    """

    repo: Path
    epic_id: str
    verdict: str
    record_path: Path


def run_post_plan_record_command(
    *,
    post: PlanRecordPost,
    config: StoreConfig,
    runner: CommandRunner,
    env: Mapping[str, str],
    emit: Callable[[str], None],
) -> int:
    """Publish one plan record on its epic, refusing before the append whenever it must."""
    client = make_beads_client(config=config)
    if not client.exists(issue_id=post.epic_id):
        emit(_NO_EPIC_REFUSAL.format(epic_id=post.epic_id))
        return _EXIT_REFUSED
    declared = _declared_modes(client=client, epic_id=post.epic_id)
    if not declared:
        emit(_NO_SECTION_REFUSAL.format(epic_id=post.epic_id))
        return _EXIT_REFUSED
    evidence = read_evidence(
        record_path=post.record_path,
        work_item_id=f"plan epic {post.epic_id}",
        declared=declared,
        # Only a CAPTURE drops its reproduction verdict. A `human_attested` record
        # is its own independent leg rather than a replay, and the archive gate
        # reads its verdict line, so it carries one exactly as a replay does.
        verdict_is_replay=post.verdict != VERDICT_CAPTURED,
        surface=PLAN_RECORD_SURFACE,
        # The plan clause asks for no scenario field, so an absent one renders no
        # claim about scenarios rather than the item clause's own statement.
        scenario_fallback=None,
        emit=emit,
    )
    if evidence is None:
        return _EXIT_REFUSED
    return _publish(post=post, client=client, evidence=evidence, env=env, runner=runner, emit=emit)


def _publish(
    *,
    post: PlanRecordPost,
    client: BeadsClient,
    evidence: Evidence,
    env: Mapping[str, str],
    runner: CommandRunner,
    emit: Callable[[str], None],
) -> int:
    """Clear the identity and capture refusals, render, and append the record."""
    identity = computed_publishing_identity(repo=post.repo, env=env, runner=runner)
    if identity is None:
        emit(_NO_IDENTITY_REFUSAL)
        return _EXIT_REFUSED
    refusal = _replay_refusal(post=post, client=client, identity=identity.identity)
    if refusal is not None:
        emit(refusal)
        return _EXIT_REFUSED
    body = render_proof_record(
        title=PLAN_PROOF_RECORD_TITLE,
        verdict=post.verdict,
        identity=identity.header_field,
        timestamp=_utc_now_iso(),
        build=evidence.build,
        assertions=evidence.assertions,
    )
    emit(body)
    client.add_comment(issue_id=post.epic_id, body=body)
    return 0


def _declared_modes(*, client: BeadsClient, epic_id: str) -> dict[str, str]:
    """Each plan assertion mapped to the proof mode the section declared for it.

    A MAPPING rather than a set because the mode is what the record publishes, and
    computing it here is what stops a caller declaring one: the record can only
    ever carry the mode the plan's own Definition of Done assigned.

    An empty mapping means the epic carries no gradeable section — the same answer
    for a description with no heading, one whose first heading is something else,
    and one whose section holds no bullet, which is the distinction the ratified
    parse already collapses and the one every plan-side reader relies on.

    EVERY assertion is declared here, not only the host-captured ones, which is
    where this differs from the item surface. A plan's `human_attested` assertion
    is proved by a `human_attested` plan record on the SAME epic, so the primitive
    that publishes one needs its mode too; the item surface filters to the host
    leg because its factory assertions are proved by a different mechanism
    entirely.
    """
    description = client.show_issue(issue_id=epic_id).get("description")
    section = plan_definition_of_done(
        description=description if isinstance(description, str) else ""
    )
    return {one.text: one.proof_mode for one in section.assertions}


def _replay_refusal(*, post: PlanRecordPost, client: BeadsClient, identity: str) -> str | None:
    """The refusal a REPLAY earns from the records already on the epic.

    A capture earns none, and nor does a `human_attested` record: neither is a
    replay of anything, so neither has a capturing identity to collide with.

    The capture compared against is the LATEST one, which is the same record the
    archive gate measures a replay's recency against — so a replay this primitive
    admits is a replay of the capture the gate will hold it to.
    """
    if post.verdict not in PLAN_REPLAY_VERDICTS:
        return None
    capture = latest_plan_proof_entry(
        entries=plan_proof_entries(comments=client.list_comments(issue_id=post.epic_id)),
        verdicts=(VERDICT_CAPTURED,),
    )
    if capture is None:
        return _NO_CAPTURE_REFUSAL.format(epic_id=post.epic_id, verdict=post.verdict)
    if capture.record.run_id != identity:
        return None
    return _SELF_VERIFIED_REFUSAL.format(identity=identity, verdict=post.verdict)


def _utc_now_iso() -> str:
    """The record header's UTC timestamp, computed rather than accepted."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

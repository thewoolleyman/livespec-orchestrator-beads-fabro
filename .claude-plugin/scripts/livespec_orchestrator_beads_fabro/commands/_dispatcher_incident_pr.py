"""Which pull request an incident item's chain names, for the valves that resolve a merge.

`SPECIFICATION/contracts.md` ("Expedited incident lifecycle") requires that
merged-PR resolution and proof publication "select that explicit current
identity; the first merged branch match, latest title mention, or
marker-removal diff alone MUST NOT select it". For an item with incident
authority, the pull request is therefore read from the chain's current
`pr-bound` carrier through `carrier_selection`, which re-reads the chain
immediately before answering, and handed to the ordinary resolution as its
explicit selector. An item with no genesis record is left exactly to the
ordinary resolution: nothing here reads the forge or the chain for it.

One carrier is selected without being `pr-bound` (bd-ib-iwksr3). A repayment
attempt walks to `repayment-active` on its own `branch-reserved` carrier with no
PR, and under merge-hold its run ends before the pull request merges, so the
chain never names one, while `bind-repayment-acceptance` will not bind until the
item rests in acceptance. For that attempt alone an operator `--pr` is read from
the forge and selected only when it is MERGED and its head branch is the
carrier's reserved ref, the rule `bind-repayment-acceptance` applies, under its
refusal codes. Without `--pr`, or in any other phase, the carrier still refuses
`incident-carrier-unbound`.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._incident_authority_payload import GENESIS_MARKER
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_carrier import BranchReserved, is_object_id
from livespec_orchestrator_beads_fabro._incident_entry import GENERATION_STALE
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._incident_authority_binding import (
    CARRIER_MISMATCH,
    PR_UNMERGED,
    PR_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.incident_authority import (
    carrier_selection,
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._incident_authority_types import IncidentReading
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "INCIDENT_CARRIER_STALE",
    "IncidentCarrierTarget",
    "apply_incident_selection",
    "incident_carrier_target",
    "incident_selection",
]

INCIDENT_CARRIER_STALE = "incident-carrier-stale"
_CARRIER_UNBOUND = "incident-carrier-unbound"
_SLUG_UNRESOLVED = "incident-repository-unresolved"
_SLUG_TIMEOUT_SECONDS = 30.0
_REFS_HEADS = "refs/heads/"
_REPAYMENT_ACTIVE = REPAYMENT_PHASES[2]
_PR_FIELDS = "number,state,headRefName,headRefOid"
_MERGED = "MERGED"
_PR_TIMEOUT_SECONDS = 60.0
_LEDGER_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


@dataclass(frozen=True, kw_only=True)
class IncidentCarrierTarget:
    """The pull request, head branch and published head the chain's current carrier names."""

    pr_number: int
    branch: str
    remote_head: str


def _refusal(*, surface: str, item: WorkItem, code: str, detail: str) -> str:
    return (
        f"ERROR: {surface} refused: work-item {item.id} carries incident authority, so its "
        f"pull request is selected through the chain, which refused {code} ({detail}); no "
        "merge was ranked by branch or title.\n"
    )


def _has_genesis(*, client: BeadsClient, item_id: str) -> bool:
    return any(
        isinstance(text, str) and text.startswith(GENESIS_MARKER)
        for text in (comment.get("text") for comment in client.list_comments(issue_id=item_id))
    )


def _repository(*, repo: Path, runner: CommandRunner) -> str | None:
    read = runner.run(
        argv=["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        cwd=repo,
        timeout_seconds=_SLUG_TIMEOUT_SECONDS,
    )
    slug = read.stdout.strip()
    return slug if read.exit_code == 0 and slug else None


def incident_carrier_target(
    *,
    repo: Path,
    item: WorkItem,
    runner: CommandRunner,
    surface: str,
    explicit_pr: int | None = None,
) -> IncidentCarrierTarget | str | None:
    """The chain's pull request for an incident item, a refusal, or None for every other item.

    `None` means the item has no genesis record and the caller resolves as it
    always has. A refusal string names the surface, the item, and the chain's
    own refusal: a superseded reading is `incident-carrier-stale`, a carrier
    that is not yet `pr-bound` is `incident-carrier-unbound`, except that an
    `explicit_pr` can select a merge-held repayment's merged pull request.
    """
    client = make_beads_client(config=store_config(repo=repo))
    try:
        if not _has_genesis(client=client, item_id=item.id):
            return None
    except _LEDGER_ERRORS as exc:
        return _refusal(
            surface=surface, item=item, code="incident-authority-unavailable", detail=str(exc)
        )
    repository = _repository(repo=repo, runner=runner)
    if repository is None:
        return _refusal(surface=surface, item=item, code=_SLUG_UNRESOLVED, detail="gh repo view")
    explicit = _ExplicitPr(repo=repo, runner=runner, number=explicit_pr)
    return _selected(
        client=client, repository=repository, item=item, surface=surface, explicit=explicit
    )


@dataclass(frozen=True, kw_only=True)
class _ExplicitPr:
    """The operator's `--pr`, with what reading it from the forge needs."""

    repo: Path
    runner: CommandRunner
    number: int | None


def _selected(
    *,
    client: BeadsClient,
    repository: str,
    item: WorkItem,
    surface: str,
    explicit: _ExplicitPr,
) -> IncidentCarrierTarget | str:
    """The chain's current pr-bound carrier, or the refusal the chain gave."""
    head = read_incident_head(client=client, repository=repository, item_id=item.id)
    if isinstance(head, AuthorityRefusal):
        return _refusal(surface=surface, item=item, code=head.code, detail=head.detail)
    selection = carrier_selection(client=client, reading=head)
    if isinstance(selection, AuthorityRefusal):
        code = INCIDENT_CARRIER_STALE if selection.code == GENERATION_STALE else selection.code
        return _refusal(surface=surface, item=item, code=code, detail=selection.detail)
    if selection.pr_number is None or selection.remote_head is None:
        if explicit.number is not None and _merge_held_repayment(reading=head):
            return _explicit_repayment_pr(
                explicit=explicit,
                repository=repository,
                target_ref=selection.target_ref,
                item=item,
                surface=surface,
            )
        return _refusal(surface=surface, item=item, code=_CARRIER_UNBOUND, detail=selection.state)
    return IncidentCarrierTarget(
        pr_number=selection.pr_number,
        branch=selection.target_ref.removeprefix(_REFS_HEADS),
        remote_head=selection.remote_head,
    )


def _merge_held_repayment(*, reading: IncidentReading) -> bool:
    """Whether the current attempt is an active repayment still on its reserved branch."""
    attempt = reading.attempt
    return attempt.phase == _REPAYMENT_ACTIVE and isinstance(attempt.carrier, BranchReserved)


def _explicit_repayment_pr(
    *,
    explicit: _ExplicitPr,
    repository: str,
    target_ref: str,
    item: WorkItem,
    surface: str,
) -> IncidentCarrierTarget | str:
    """The operator's pull request when the forge reports it merged on the reserved branch."""
    number = explicit.number
    result = explicit.runner.run(
        argv=["gh", "pr", "view", str(number), "--repo", repository, "--json", _PR_FIELDS],
        cwd=explicit.repo,
        timeout_seconds=_PR_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    value = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    state, head_ref, head = value.get("state"), value.get("headRefName"), value.get("headRefOid")
    if (
        value.get("number") != number
        or not isinstance(state, str)
        or not isinstance(head_ref, str)
        or not is_object_id(value=head)
    ):
        reason = result.stderr.strip() or "no number, state and head in the reply"
        return _refusal(
            surface=surface, item=item, code=PR_UNOBSERVABLE, detail=f"PR #{number}: {reason}"
        )
    if state != _MERGED:
        return _refusal(
            surface=surface, item=item, code=PR_UNMERGED, detail=f"PR #{number}: {state}"
        )
    if _REFS_HEADS + head_ref != target_ref:
        return _refusal(
            surface=surface,
            item=item,
            code=CARRIER_MISMATCH,
            detail=f"PR #{number} head {head_ref} is not {target_ref}",
        )
    return IncidentCarrierTarget(
        pr_number=cast("int", number), branch=head_ref, remote_head=cast("str", head)
    )


def apply_incident_selection(
    *, plan: DispatchPlan, selected_pr: int | None, target: IncidentCarrierTarget, item: WorkItem
) -> tuple[DispatchPlan, int] | str:
    """The plan and selector the reconcile valve resolves an incident item's merge with.

    The chain's pull request becomes the explicit selector and the carrier's
    head branch the plan's branch, so the forge read that validates the
    selection identifies the merge by the incident carrier itself. An operator
    `--pr` that names another pull request is refused rather than outranking
    the chain.
    """
    if selected_pr is not None and selected_pr != target.pr_number:
        return (
            f"ERROR: reconcile-merged refused: --pr {selected_pr} names another pull request "
            f"than work-item {item.id}'s incident carrier (#{target.pr_number}); the chain "
            "selects the merge.\n"
        )
    return replace(plan, branch=target.branch), target.pr_number


def incident_selection(
    *,
    repo: Path,
    item: WorkItem,
    runner: CommandRunner,
    plan: DispatchPlan,
    selected_pr: int | None,
) -> tuple[DispatchPlan, int | None] | int:
    """The plan and selector the reconcile valve resolves with, or the exit code that refuses.

    Every item without incident authority keeps the plan and the operator's
    selector exactly as given. A refusal is written to stderr here, as the
    valve's other precondition refusals are, and its exit code returned.
    """
    target = incident_carrier_target(
        repo=repo, item=item, runner=runner, surface="reconcile-merged", explicit_pr=selected_pr
    )
    if target is None:
        return plan, selected_pr
    applied = (
        target
        if isinstance(target, str)
        else apply_incident_selection(plan=plan, selected_pr=selected_pr, target=target, item=item)
    )
    if isinstance(applied, str):
        _ = write_stderr(text=applied)
        return EXIT_PRECONDITION_ERROR
    return applied

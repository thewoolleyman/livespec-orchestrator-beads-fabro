"""The pre-dispatch wall: every refusal that lands after selection, before claim.

The ONE wall both dispatch paths run — the single `dispatch` and the queue-
draining `loop`. It was two byte-identical private functions, one per command
module, differing only in which item sequence each handed down; the duplicate is
what made "both paths refuse" a claim about two sequences that could drift, and
what required every new refusal to be wired twice. It moved out when the Codex
credential gate became the fourth refusal in each and pushed the single-dispatch
command module past its file LLOC ceiling — the seam was already there.

WHAT THE WALL IS. Four refusals plus one mutation, sharing one POSITION and one
guarantee: each runs after selection and BEFORE admission, so a refused item is
never claimed, no `active` row is left behind, and no factory run exists to reap.
Reading them as one decision is also what keeps each command entry point's return
count honest — the alternative was suppressing the too-many-returns rule, which
would have hidden the fact that the entry point had grown another exit.

The DRAIN reaches it after its `--dry-run` return, deliberately: a dry run creates
no run, so it stays a reporting surface that shows the operator exactly which
candidate needs criteria.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_credential_gate import (
    codex_credential_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
    EXIT_UNGRADEABLE_CRITERIA,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    credential_wrapper_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_gate import (
    proof_credentials_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    proof_assets_refusal_for_items,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publish_branch_reclaim import (
    reclaim_stale_publish_branches,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "pre_dispatch_wall_exit",
]


def pre_dispatch_wall_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
) -> int | None:
    """The whole wall, as ONE decision: an exit code, or None to proceed.

    `items` is the selection this pass would claim — exactly one target for the
    single dispatch, the whole admitted-candidate wave for the drain. Nothing
    below branches on which caller it is, which is the point: a refusal that
    fired for one path and not the other was a defect waiting to happen.

    The criteria wall is first and is variant-aware: it is handed this dispatch's
    explicit `--workflow-name`, resolves which graph the selection would run, and
    exempts a groom-kind dispatch, whose acceptance is the human approval of the
    draft.

    The proof-ASSETS gate follows (S5 / bd-ib-b4u6b7): an item carrying a
    `factory_captured` assertion needs this repository's standing proof-assets
    prerelease to exist before its capture stage can store an image, so the
    Dispatcher creates it here and refuses naming the tag when it still does not.
    Its exit code is the generic precondition one rather than a dedicated code:
    the fault is a missing repository-level resource, which is the same class
    every other pre-dispatch precondition reports.

    The proof-CREDENTIAL gate follows (S8 / bd-ib-77vny7), in the same position
    and for the same reason: an unusable `dispatcher.proof_credentials`
    declaration must refuse before a run exists, because the overlay each of
    these items is about to materialize would otherwise project it. It reads the
    environment here rather than resolving one of its own, so the values it
    grades are the ones the overlay will actually read. That declaration is
    repository-level, so one refusal covers the whole selection, while the
    journal records are written per item.

    The Codex credential gate closes the refusing sequence (bd-ib-tyqklx) and is
    the newest of the four for a reason worth recording: its decision was already
    being made, inside `materialize_overlay`, which `dispatch_one` reaches only
    AFTER `admit_and_select` has moved the item `ready -> active` and set its
    assignee — so a credential that could not be renewed above the floor left an
    `active` row nobody was working. It is also the only wall that spends a
    PROVIDER REQUEST, the one bounded in-place renewal, so its position is what
    decides whether that request's answer can still change what happens: before
    the claim it can refuse the selection, after it cannot. Like the
    proof-credential declaration it is a HOST-level fact, so one refusal covers
    the whole selection rather than reading as one fault per item.

    The publish-branch reclaim closes the wall and refuses NOTHING
    (bd-ib-yebrb7): a dead run's surviving publish branch is what makes a
    re-dispatch's `publish_draft` push non-fast-forward, and clearing it here --
    once its head is preserved by reference -- is what lets the recovery publish
    and reach proof capture. It is per ITEM, because a publish branch is per
    item, and it runs last because it MUTATES a remote ref: a selection this wall
    is about to refuse must leave the remote exactly as it found it.
    """
    ungradeable = pre_dispatch_criteria_refusal(
        items=items, cwd=repo, workflow_name=args.workflow_name
    )
    if ungradeable is not None:
        _ = write_stderr(text=ungradeable)
        return EXIT_UNGRADEABLE_CRITERIA
    proof_refusal = proof_assets_refusal_for_items(
        runner=ShellCommandRunner(), repo=repo, items=items, journal=journal
    )
    if proof_refusal is not None:
        _ = write_stderr(text=proof_refusal)
        return EXIT_PRECONDITION_ERROR
    work_item_ids = [item.id for item in items]
    credentials_refusal = proof_credentials_refusal_for_items(
        repo=repo,
        environ=os.environ,
        wrapper_text=credential_wrapper_text(repo=repo),
        work_item_ids=work_item_ids,
        journal=journal,
    )
    if credentials_refusal is not None:
        _ = write_stderr(text=credentials_refusal)
        return EXIT_PRECONDITION_ERROR
    codex_refusal = codex_credential_refusal_for_items(work_item_ids=work_item_ids, journal=journal)
    if codex_refusal is not None:
        _ = write_stderr(text=f"{codex_refusal}\n")
        return EXIT_PRECONDITION_ERROR
    reclaim_stale_publish_branches(args=args, repo=repo, items=items, journal=journal)
    return None

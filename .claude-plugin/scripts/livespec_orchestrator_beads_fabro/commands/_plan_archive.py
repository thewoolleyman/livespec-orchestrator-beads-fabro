"""The archive leg of the plan operation: the gates, the close, and the move.

Split out of `plan.py` by cohesion. That module holds the AUTHORING concern —
creating a plan, appending a handoff entry, recording a scope event — and this
one holds ARCHIVING, which is a different responsibility with a different
neighbourhood: `_plan_archive_gates` supplies the working-tree sweep and
`_plan_archive_review` supplies the completeness-review evidence rules, and
both were imported into `plan.py` for this leg alone.

The split cuts at the public entry point. `archive_thread` moves together with
the two private helpers only IT used, so nothing private crosses a module
boundary; `plan.py` imports the public name back and re-exports it, leaving
every existing caller of `plan.archive_thread` unaffected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
    outside_plan_path_references,
)
from livespec_orchestrator_beads_fabro.commands._plan_archive_review import (
    ArchiveCompletenessReviewRequest,
    CompletenessReviewLauncher,
    archive_completeness_review_request,
    undisposed_plan_child_ids,
    valid_completeness_review_evidence_id,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_HANDOFF_PREFIX,
    plan_comment_body,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "PLAN_ARCHIVE_ACTOR",
    "archive_thread",
]

_PLAN_DIR = "plan"
_ARCHIVE_DIR = "archive"
# The reserved author literal the archive leg signs its own handoff entry with,
# computed here rather than accepted from a caller — the same reservation
# `append_supervisor_handoff` makes for `<slug>-supervisor`. PUBLIC because the
# completeness-review evidence rules have to exclude the archive actor's own
# comment from counting as independent evidence.
PLAN_ARCHIVE_ACTOR = "plan-archive"


def archive_thread(
    *,
    project_root: Path,
    config: StoreConfig,
    slug: str,
    epic_id: str,
    completeness_review_comment_id: str | None,
    review_launcher: CompletenessReviewLauncher | None = None,
) -> dict[str, str]:
    """Archive a thread once the child, working-tree reference, and review gates pass.

    The working-tree gate sits between the two ledger gates deliberately.
    It is mechanical and cheap, like the child-disposition leg, so a plan
    the move would break refuses BEFORE a fresh independent reviewer is
    commissioned — and, decisively, before the epic is closed and stamped.
    """
    client = make_beads_client(config=config)
    undisposed = list(undisposed_plan_child_ids(client=client, epic_id=epic_id))
    if undisposed:
        raise PlanArchiveRefusedError.undisposed_children(child_ids=undisposed)
    referencing = outside_plan_path_references(project_root=project_root, slug=slug)
    if referencing:
        raise PlanArchiveRefusedError.outside_path_references(slug=slug, paths=referencing)
    source = project_root / _PLAN_DIR / slug
    evidence_id = _resolve_completeness_review_evidence(
        client=client,
        epic_id=epic_id,
        completeness_review_comment_id=completeness_review_comment_id,
        review_launcher=review_launcher,
        request=archive_completeness_review_request(
            client=client,
            project_root=project_root,
            source=source,
            slug=slug,
            epic_id=epic_id,
        ),
    )
    if evidence_id is None:
        raise PlanArchiveRefusedError.missing_completeness_review()
    archive = project_root / _PLAN_DIR / _ARCHIVE_DIR / slug
    archive.parent.mkdir(parents=True, exist_ok=True)
    _ = source.rename(archive)
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(
            prefix=PLAN_HANDOFF_PREFIX,
            author=PLAN_ARCHIVE_ACTOR,
            now=_utc_now_iso(),
            body=f"Archived after completeness review {evidence_id}.",
        ),
    )
    client.close_issue(issue_id=epic_id, reason="plan archived")
    return {"archive_path": archive.relative_to(project_root).as_posix(), "epic_id": epic_id}


def _resolve_completeness_review_evidence(
    *,
    client: BeadsClient,
    epic_id: str,
    completeness_review_comment_id: str | None,
    review_launcher: CompletenessReviewLauncher | None,
    request: ArchiveCompletenessReviewRequest,
) -> str | None:
    evidence_id = valid_completeness_review_evidence_id(
        client=client,
        epic_id=epic_id,
        evidence_id=completeness_review_comment_id,
        archive_actor=PLAN_ARCHIVE_ACTOR,
    )
    if evidence_id is not None or review_launcher is None:
        return evidence_id
    launched_id = review_launcher(request=request)
    return valid_completeness_review_evidence_id(
        client=client,
        epic_id=epic_id,
        evidence_id=launched_id,
        archive_actor=PLAN_ARCHIVE_ACTOR,
    )


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

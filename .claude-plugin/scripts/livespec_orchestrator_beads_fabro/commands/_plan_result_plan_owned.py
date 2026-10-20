"""The repository an obligation naming the PLAN EPIC ITSELF is read against.

A plan-level leg targets the plan epic — the proof and review legs through a
comment on it, the archive leg through its closed status — and the epic lives in
the plan's own tenant whatever repository the recorded obligation names. So a
recorded foreign repository makes that read fail, and the failure is terminal
rather than cosmetic: an unobservable obligation withholds dispatch while being
unreplaceable by design, so one stale `repo` field locks a plan for its whole
budget with no sanctioned write able to correct it. Measured 2026-10-20 on plan
epic `bd-ib-fyozyd`, whose satisfied `await` named a `livespec-dev-tooling` item
and whose derived proof leg inherited that repository.

`_plan_resume_advance` stops NEW pointers acquiring that field; this is what
unlocks the plans whose records already carry it.

WHY THIS MODULE OWNS THE READ ITSELF AND NOT MERELY THE REDIRECT. One plan-level
obligation is read THREE times from two stores on the way through a single
resume, and settling it at any subset of them leaves the locked plan stopped —
differently each time, which is what makes the count worth stating rather than
leaving to be rediscovered:

1. `evaluate_resume_progress` reads the CHAIN-held authority, and
   `decide_plan_resume` returns on its verdict before the pointer is ever
   consulted. So a redirect applied only at the pointer read is unreachable for
   every chain-tracked plan — which is every plan the progress gate can lock.
   Measured 2026-10-20 against the pointer-only build: a chain-tracked epic
   whose obligation named a sibling still reported
   `plan-progress-tracking: unobservable` and still answered with the diagnosis
   action, while its own-repository twin advanced.
2. `result_observation` reads the recorded POINTER, which is what decides that
   the satisfied step is stale and an advance is owed.
3. `_plan_tracked_write._prior_observation` reads the chain-held authority
   AGAIN, on behalf of the sanctioned write that persists the derived pointer.
   This reading does not report, it DECIDES: an unobservable prior obligation
   cannot be replaced, so the derived step is refused and the resume answers
   with no further step at all. Measured 2026-10-20 against the two-reader
   build on the item's own shape: a chain-tracked epic with a satisfied `proof`
   leg advanced to a derived review step and then had it refused — `the
   obligation stranger-repo item_comment <epic> marker 'Plan Proof of Done' is
   unobservable, so it cannot be replaced by repo item_comment <epic> marker
   'plan-completeness-review-evidence'` — leaving the plan SILENTLY stopped
   rather than diagnosably locked, which under an unattended resume is the
   worse of the two.

So `read_plan_owned_result` is the entry point all three take, and it performs
the whole read rather than handing back a corrected reference. The count is the
reason: each read was added for its own purpose, none of them announced that it
owed this redirect, and a fourth will not either — while a reader that reaches
`read_result` directly has to remember a three-step composition whose middle
step is the only one that fails silently.

WHY THE DISCRIMINATOR IS THE TARGET AND NOT THE POINTER'S KIND. The condition
that makes the redirect correct is that the obligation's own target IS the plan
epic, and that is checkable from the obligation alone — which is the only thing
the chain records. A kind test would ALSO have to be invented for the chain
read, where no kind exists. It would buy nothing in either case: an `impl` leg's
target is a CHILD, so it fails the target test already, and an id equal to the
epic's resolves in exactly one tenant — the plan's own — whichever leg recorded
it.

WHY THE REWRITE PERSISTS NOTHING. It is a READ-TIME redirect on every one of
those three paths, each of which is observing rather than recording: the
recorded pointer is replaced by the ordinary advance once this obligation is
satisfied, and the sanctioned write's own reading is of the PRIOR obligation,
which it grades rather than rewrites. Writing here would be an unsanctioned
ledger write, and `_plan_progress_resume`'s every arm is read-only by contract.

WHY THE RECORDED IDENTITY IS NOT COMPARED BEFORE SUBSTITUTING. An obligation
already naming the plan's own repository rewrites to the value it holds, so a
comparison would add an arm whose only difference is that it is harder to show
correct.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import REPO_FIELD
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    project_repository_identity,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ITEM_COMMENT_KIND,
    ITEM_STATUS_KIND,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "plan_owned_reference",
    "read_plan_owned_result",
]

# The two target kinds a plan-level leg's own obligation is ever written as: a
# comment on the epic for the proof and review legs, and the epic's closed
# status for the archive leg.
_ITEM_TARGET_KINDS: tuple[str, ...] = (ITEM_COMMENT_KIND, ITEM_STATUS_KIND)
_ITEM_ID_FIELD = "item_id"


def read_plan_owned_result(
    *,
    config: StoreConfig,
    epic_id: str,
    required_result: object,
    now: str | None = None,
) -> ResultObservation:
    """Observe one plan-level obligation, from this project, through the redirect.

    THE WHOLE READ AND NOT MERELY THE REDIRECT, because the redirect alone is a
    rule each caller has to remember to apply and three of them already had to.
    A caller reaching `read_result` directly composes the same three steps —
    resolve this project's root, redirect a plan-owned reference, read — and the
    only one of the three that announces its own absence is the root: a caller
    that forgets the redirect gets a well-formed `unobservable` reading of
    another repository's tenant, which every surface downstream reports as an
    obligation that cannot be measured.

    So this is the entry point every plan-level reader takes, and `read_result`
    is reached through it. The `now` default is the reader's own and is passed
    through rather than resolved here, so a caller pinning an instant and a
    caller taking the clock still read one obligation one way.
    """
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    return read_result(
        project_root=project_root,
        reference=plan_owned_reference(
            config=config, epic_id=epic_id, required_result=required_result
        ),
        runner=ShellCommandRunner(),
        now=now,
    )


def plan_owned_reference(*, config: StoreConfig, epic_id: str, required_result: object) -> object:
    """The reference to READ: the recorded one, or its plan-owned repository."""
    if not _names_epic(required_result=required_result, epic_id=epic_id):
        return required_result
    recorded = cast("dict[str, Any]", required_result)
    return {**recorded, REPO_FIELD: project_repository_identity(config=config)}


def _names_epic(*, required_result: object, epic_id: str) -> bool:
    """Whether a recorded obligation's own target is the plan epic itself.

    Read off the RAW value rather than through the typed parse, because a
    reference the parse refuses is one `read_result` must report its own refusal
    for — so a parse here would either duplicate that ladder or decide a
    redirect on a target the reader never admitted.
    """
    fields = cast("dict[str, Any]", required_result) if isinstance(required_result, dict) else {}
    return any(
        isinstance(target, dict) and cast("dict[str, Any]", target).get(_ITEM_ID_FIELD) == epic_id
        for target in (fields.get(kind) for kind in _ITEM_TARGET_KINDS)
    )

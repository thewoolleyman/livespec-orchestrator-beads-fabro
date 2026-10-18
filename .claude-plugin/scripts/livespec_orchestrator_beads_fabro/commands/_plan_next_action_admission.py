"""Admitting one typed plan pointer, the repository its result names included.

`_plan_next_action_validation` grades a pointer's SHAPE and is pure over the
value handed to it. This is the impure half of the same admission: whether the
repository the pointer's `required_result` names is one the shared authoritative
result reader can actually resolve for this project, which takes the project
root and, on the arm that reaches it, a local git read.

WHY THE WRITER ASKS THE READER'S OWN RESOLVER RATHER THAN A RULE OF ITS OWN.
`_plan_result_reference` admits any non-empty `repo` string, while
`_plan_result_repository` resolves only four identities — the project
directory's name, the basename of its `livespec.primaryPath`, the repository
name its origin remote carries, and a configured `cross_repo_targets` key. So a
value the writer accepted could be one the reader can never resolve, and every
later observation of it reads `unobservable` from repository resolution. That is
the most expensive way for this pair to disagree: `resume_directive` withholds
dispatch while a required result is unobservable, and replacing an unobservable
obligation is refused by design, so ONE malformed field locks the obligation for
its whole budget. Measured 2026-10-18 on plan epic `bd-ib-6tcjfx`, whose pointer
named this project's own repository in the full `owner/name` form and stayed
unobservable until its deadline.

The agreement is therefore STRUCTURAL rather than a second rule kept in step:
the admission calls `resolve_result_repository`, the same function the reader
calls, so there is no rule here that could drift from it. A widening of what the
reader resolves widens what the writer admits, in the same commit, by
construction.

WHY AN UNPARSEABLE REFERENCE IS NOT THIS MODULE'S REFUSAL. The shape grade runs
first, and it already refuses an executable pointer whose reference will not
parse — naming the parse fault, which is the remedy its author needs — while a
`human` or `none` pointer carries explicit null tracking and names no repository
at all. Either way there is no repository identity left to grade, so this arm
answers `None` rather than restating a refusal another module owns or inventing
one for a pointer that is correct.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_next_action import LEGACY_TRACKING
from livespec_orchestrator_beads_fabro.commands._plan_next_action_validation import (
    NextActionRefusal,
    NextActionShape,
    validate_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    resolve_result_repository,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ResultReferenceRefusal,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "admit_next_action",
]


def admit_next_action(
    *,
    action: NextActionShape,
    epic_id: str,
    config: StoreConfig,
) -> NextActionRefusal | None:
    """Admit one typed pointer: its shape first, then the repository it names."""
    refusal = validate_next_action(
        action=action,
        epic_id=epic_id,
        legacy_tracking=LEGACY_TRACKING,
    )
    if refusal is not None:
        return refusal
    return _unresolvable_repository(
        project_root=_project_root(config=config),
        required_result=action.required_result,
    )


def _unresolvable_repository(
    *,
    project_root: Path,
    required_result: object,
) -> NextActionRefusal | None:
    """Refuse a repository identity no observation of this result could resolve.

    The refusal NAMES that identity, because the `repo` field is the one thing
    its author has to change and a refused write echoes it nowhere else — so a
    refusal without it sends the author to read the resolver rather than fix the
    value.
    """
    parsed = parse_result_reference(value=required_result)
    if isinstance(parsed, ResultReferenceRefusal):
        return None
    if resolve_result_repository(project_root=project_root, name=parsed.repo) is not None:
        return None
    remedy = _bare_identity_remedy(project_root=project_root, name=parsed.repo)
    return NextActionRefusal(
        detail=(
            f"required_result names the repository {parsed.repo!r}, which the shared"
            " authoritative result reader cannot resolve for this project, so every"
            f" observation of this obligation would be unobservable{remedy}"
        )
    )


def _bare_identity_remedy(*, project_root: Path, name: str) -> str:
    """Name the bare identity a forge-path spelling was reaching for, when it resolves.

    The measured incident named this project's own repository as `<owner>/<repo>`,
    which is the right identity on every other surface this fleet has, so a
    refusal that only echoed the value back reads as a refusal of the correct
    answer. The segment after the last separator is RESOLVED before it is
    suggested, so a path whose tail is equally unresolvable gets no suggestion
    rather than a confident-looking wrong one.

    THE SUGGESTION IS NEVER APPLIED HERE, and that is deliberate rather than
    timid. Stripping the owner would make `<any-owner>/<this-repo-name>` resolve
    to THIS checkout — the one thing `_plan_result_repository`'s own origin-name
    resolution refuses to do, because it would read another repository's result
    as this project's and report it satisfied. A refusal costs its author one
    edit; a wrong normalization costs a false observation nobody can see.
    """
    bare = name.rsplit("/", 1)[-1]
    if bare == name or resolve_result_repository(project_root=project_root, name=bare) is None:
        return ""
    return f"; this project resolves as {bare!r}, so name that rather than a forge path"


def _project_root(*, config: StoreConfig) -> Path:
    root = config.repo_root
    return Path.cwd() if root is None else root

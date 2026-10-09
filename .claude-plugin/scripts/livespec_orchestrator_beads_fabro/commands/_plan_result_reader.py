"""The ONE shared authoritative result reader both tracking callers use.

The shared-authoritative-result-reader clause of `SPECIFICATION/contracts.md`
requires exactly one reader — "Both delivery and deadline callers MUST use it" —
so this module is deliberately the only public entry point into the parse, the
repository resolution and the five adapters. A caller that reached an adapter
directly would be choosing a source for itself, which is the shape the clause
retires.

THE ORDER OF THE THREE STEPS IS LOAD-BEARING, AND IT IS THE FAIL-CLOSED ORDER.
The reference is parsed before anything is read, because an unparseable reference
names no target to read; the repository is resolved before any adapter runs,
because every adapter needs the clone it executes from; and only then is one
source consulted. Reversing any pair would spend a read on a question that had
not been established — and, worse, would let a read failure be reported where a
reference or resolution fault was the real cause, which is a false attribution of
the failed source the clause requires naming.

THE DISPATCH IS A `match` OVER THE CLOSED TARGET UNION, ending in the
`assert_never` arm this tree requires. That is what makes a sixth ratified kind a
type error here rather than a silent fall-through: a ladder of `isinstance`
checks with a trailing default would accept the new kind and report it as
unobserved.

`now` IS INJECTED BY DEFAULT-NONE RATHER THAN REQUIRED. The clause requires a UTC
observation time, and a caller that had to supply one could supply a local one;
resolving it here through the repository's own canonical UTC helper makes the
default correct. It stays overridable because the deadline caller's own
boundaries must be deterministic against an injected current time.
"""

from __future__ import annotations

from pathlib import Path

from typing_extensions import assert_never

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_result_forge import (
    observe_file_on_branch,
    observe_pull_request_state,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_ledger import (
    observe_item_comment,
    observe_item_status,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    SOURCE_REFERENCE,
    SOURCE_REPOSITORY_RESOLUTION,
    ResultObservation,
    unobservable,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_proof import observe_verified_proof
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    ResultRepository,
    resolve_result_repository,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    FileOnBranchTarget,
    ItemCommentTarget,
    ItemStatusTarget,
    PullRequestStateTarget,
    ResultReference,
    ResultReferenceRefusal,
    ResultTarget,
    VerifiedProofTarget,
)

__all__: list[str] = [
    "UNPARSED_TARGET",
    "read_result",
]

# What a reference that will not parse names as its target. STATED rather than
# left empty, because the clause requires every observation to report a target
# identity and "" renders as a field the writer forgot; this says outright that
# no target was ever named.
UNPARSED_TARGET = "(no typed target: the reference did not parse)"


def read_result(
    *,
    project_root: Path,
    reference: object,
    runner: CommandRunner,
    now: str | None = None,
) -> ResultObservation:
    """Observe one required result through the source its typed reference names."""
    observed_at = utc_now_iso() if now is None else now
    parsed = parse_result_reference(value=reference)
    if isinstance(parsed, ResultReferenceRefusal):
        return unobservable(
            repo=parsed.repo,
            target=UNPARSED_TARGET,
            source=SOURCE_REFERENCE,
            now=observed_at,
            detail=parsed.detail,
        )
    repository = resolve_result_repository(project_root=project_root, name=parsed.repo)
    if repository is None:
        return unobservable(
            repo=parsed.repo,
            target=parsed.target.identity,
            source=SOURCE_REPOSITORY_RESOLUTION,
            now=observed_at,
            detail=(
                f"the repository {parsed.repo} is neither this project nor a configured"
                " cross-repo target resolving to a clone on this host, so the requested"
                " target was never queried"
            ),
        )
    return _observe(
        repository=repository,
        reference=parsed,
        runner=runner,
        now=observed_at,
    )


def _observe(
    *,
    repository: ResultRepository,
    reference: ResultReference,
    runner: CommandRunner,
    now: str,
) -> ResultObservation:
    """Route one resolved reference to the single adapter its kind names."""
    target: ResultTarget = reference.target
    match target:
        case ItemStatusTarget():
            return observe_item_status(repository=repository, target=target, now=now)
        case ItemCommentTarget():
            return observe_item_comment(repository=repository, target=target, now=now)
        case PullRequestStateTarget():
            return observe_pull_request_state(
                repository=repository, target=target, runner=runner, now=now
            )
        case VerifiedProofTarget():
            return observe_verified_proof(
                repository=repository, target=target, runner=runner, now=now
            )
        case FileOnBranchTarget():
            return observe_file_on_branch(
                repository=repository, target=target, runner=runner, now=now
            )
        case _:
            assert_never(target)

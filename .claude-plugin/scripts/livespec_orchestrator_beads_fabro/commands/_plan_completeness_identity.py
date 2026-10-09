"""The identity each party to the archive completeness leg is computed under.

The completeness leg of the plan archive gate (`SPECIFICATION/contracts.md`) is a
COMPARISON between two parties: the session archiving the plan, and the party that
performed and recorded the independent completeness review. The clause says
outright that "a self-review ... MUST NOT satisfy the completeness leg", so the
leg is worth exactly as much as the two identities it compares.

Both are computed here, through ONE resolver, by the same primitive the proof
record surfaces publish under (`_dispatcher_proof_identity`). One resolver rather
than one per side because the whole guarantee is that the two values are
COMPARABLE: two resolvers reading different inputs would each look correct on its
own while making the comparison between them meaningless.

WHY THE CONSTANT THIS REPLACES COULD NOT WORK, since the intent was never in
doubt and only the comparand was wrong. The leg used to compare a reviewer
identity against the literal `plan-archive` — the reserved handoff-author word the
archive leg signs its own timeline entry with, which no reviewer would ever adopt
as an identity. The predicate therefore reduced to "a reviewer identity is present
and is not literally `plan-archive`", every other string passed, and an archiving
session could author its own completeness evidence under any other name and be
accepted. The parameter was named `archive_actor` and the evidence field
`separate-reviewer`, so the author plainly meant "the reviewer must not be the one
archiving"; a fixed constant simply cannot realize that. Filed as `bd-ib-3xsz`.

WHY AN UNRESOLVED IDENTITY REFUSES rather than falling back to anything at all.
A leg that compares two identities has no check left when one of them is unknown,
and a gauge that passes while it cannot observe its own input converts a refusal
into a pass and leaves a record that reads healthy. Nor is there a safe fallback
value to reach for: `_dispatcher_invoker`'s `unattributed:<user>@<host>` mark is
right for a journal record, and wrong here in both directions at once — two
parties on one host compare EQUAL, which refuses a genuinely independent review,
while a genuine self-review across two hosts compares DIFFERENT and is admitted.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_identity import (
    computed_publishing_identity,
)
from livespec_orchestrator_beads_fabro.commands._plan_archive_gates import (
    PlanArchiveRefusedError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner

__all__: list[str] = [
    "ARCHIVING_PARTY",
    "REVIEWING_PARTY",
    "completeness_leg_identity",
]

# The side of the leg a party sits on, as the refusal names whichever one could
# not be computed. Naming it is what tells an operator which half of the
# comparison went unresolved, since both halves raise the same refusal type and
# their remedies sit in different sessions.
ARCHIVING_PARTY = "archiving party"
REVIEWING_PARTY = "reviewing party"


def completeness_leg_identity(
    *,
    role: str,
    project_root: Path | None = None,
    env: Mapping[str, str] | None = None,
    runner: CommandRunner | None = None,
) -> str:
    """The computed identity of one party to the completeness leg.

    The three defaults are the ordinary path: a session driving the plan operation
    reads its OWN environment, and a human at a terminal resolves a forge login by
    running `gh` in the repository being worked. They are parameters so a test can
    supply both without an agent session or a forge token, and so a caller holding
    the project root need not change directory to be read correctly.

    An environment is the SESSION's own property, which is exactly what
    `_dispatcher_proof_identity` asks the primitive to read, so passing one in is
    not a caller-supplied identity route. There is deliberately no parameter an
    identity itself can be put in: an identity a caller could NAME is one a caller
    could RENAME, and the self-review refusal would then be one flag away from
    passing.
    """
    identity = computed_publishing_identity(
        repo=Path.cwd() if project_root is None else project_root,
        env=os.environ if env is None else env,
        runner=ShellCommandRunner() if runner is None else runner,
    )
    if identity is None:
        raise PlanArchiveRefusedError.unresolved_publishing_identity(role=role)
    return identity.identity

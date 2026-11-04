"""The SPEC IDENTITY as a judgement record carries it, and the node digest built on it.

A host taking records the identity it folded into its subject digest beside the
digests themselves, so the run can be supplied exactly that identity and the
`dod_gate` node can compare on the digest the taking used. The identity is read
off the NEWEST taken record, for the reason the governing-heading verdict is: a
dispatch is briefed from the most recent reading.

A record naming no identity, such as one written before the identity was
recorded, supplies none, and a run supplied none falls back on the whole-tree
digest at the resolved commit.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
    comment_marker,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    SpecIdentity,
    whole_tree_identity,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "node_subject_digest",
    "recorded_spec_identity",
    "spec_identity_lines",
]

_FORM_PREFIX = "spec-identity-form: "
_VALUE_PREFIX = "spec-identity: "


def spec_identity_lines(*, identity: SpecIdentity) -> list[str]:
    """The two record lines naming one identity's form and its labelled value."""
    return [f"{_FORM_PREFIX}{identity.form}", f"{_VALUE_PREFIX}{identity.value}"]


def recorded_spec_identity(*, comments: Sequence[str]) -> SpecIdentity | None:
    """The identity the NEWEST taken verdict recorded, or `None` when it names none."""
    for body in reversed(tuple(comments)):
        if comment_marker(body=body) != JUDGEMENT_COMMENT_MARKER:
            continue
        lines = [raw.strip() for raw in body.splitlines()]
        forms = [line[len(_FORM_PREFIX) :] for line in lines if line.startswith(_FORM_PREFIX)]
        values = [line[len(_VALUE_PREFIX) :] for line in lines if line.startswith(_VALUE_PREFIX)]
        if not forms or not values:
            return None
        return SpecIdentity(form=forms[-1], value=values[-1])
    return None


def node_subject_digest(*, item: WorkItem, cwd: Path, comments: Sequence[str]) -> str:
    """The subject digest the run's `dod_gate` node compares on.

    Computed from the identity the pre-dispatch taking recorded and the run was
    supplied, never from governing-heading verdicts of its own, so the node's
    outcome and the matching host record compare on one digest. A run supplied no
    identity, because the pre-dispatch judgement did not run, takes the
    whole-tree digest at the resolved commit.
    """
    supplied = recorded_spec_identity(comments=comments)
    identity = whole_tree_identity(cwd=cwd) if supplied is None else supplied
    return judgement_subject_digest(
        item=item, cwd=cwd, comments=comments, spec_identity=identity.value
    )

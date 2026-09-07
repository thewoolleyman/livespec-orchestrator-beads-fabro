"""Each attention item's effective answer disposition, ridden on its summary.

An item resting at `blocked` / `blocked_reason: needs-human` is an ATTENTION
ITEM: it is parked on a question, and the fifth dispatcher policy setting of the
dispatcher-policy-settings contract in `SPECIFICATION/contracts.md` (ratified in
v104) governs WHO may answer it. The snapshot that reports the parked item had
no way to say which actor class the answer is open to, so an operator reading it
could not tell an item they may answer from one only a human may.

WHY IT RIDES THE SUMMARY. The attention envelope is owned by `livespec-runtime`
through the machine-envelope contract in the same file, and this repository does
not own that wire type. The ratified clause anticipates exactly that: until a
first-class field ratifies there, the effective disposition MAY ride the
existing per-item `summary` string. So this is a deliberate carrier, not a
shortcut — and when the field lands, the sentence composed here is what moves.

WHAT IT DOES NOT DO. It reports the disposition; it never advertises a press.
The advertiser-and-enforcer binding in the same clause forbids the
`resolve-blocked` lane from offering an answer handoff the effective disposition
would refuse, and the way to satisfy that is to offer none: the lane's handoff
stays the plain `resolve-blocked:<work-item-id>:ready` action it has always been,
and the refusal itself lives in `drive`. A sentence that named an answer press
would be an advertisement, which is why the wording below deliberately does not
spell one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_answer_disposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ANSWER_DISPOSITION,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "answer_disposition_summary",
]

_HUMAN = (
    "Effective answer disposition human: only a human operator may answer this "
    "item, so an automated disposition's press is refused."
)
_CONSENSUS = (
    "Effective answer disposition consensus: the ratified consensus tier may "
    "also answer this item, and behaves as a human until livespec core "
    "ratifies the tier."
)


def answer_disposition_summary(
    *,
    project_root: Path,
    item: WorkItem,
    raw_labels: Sequence[str],
    default_summary: str,
) -> str:
    """The lane summary with this item's effective answer disposition appended.

    Fail-SOFT like every other enrichment on this lane: an unreadable
    `.livespec.jsonc` costs the READ, never the row, and falls through to the
    setting's safe default. That fallback is safe in one direction only, and it
    is the safe one — `human` is the most restrictive disposition, so a
    disposition nobody could read is never reported as more permissive than it
    is.

    `unsafe_perform_io` is required rather than decorative: `IOResult.value_or`
    returns `IO[value]`, not the value, and an `IO` wrapper compares equal to
    no disposition at all — so omitting it reports every item as `consensus`,
    which is the one direction this fallback must never fail in.
    """
    disposition = unsafe_perform_io(
        effective_answer_disposition(item=item, cwd=project_root, raw_labels=raw_labels).value_or(
            DEFAULT_ANSWER_DISPOSITION
        )
    )
    return f"{default_summary} {_sentence(disposition=disposition)}"


def _sentence(*, disposition: str) -> str:
    if disposition == DEFAULT_ANSWER_DISPOSITION:
        return _HUMAN
    return _CONSENSUS

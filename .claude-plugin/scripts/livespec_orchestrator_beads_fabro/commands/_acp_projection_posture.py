"""What an unresolved projection-failure fact does to the dispatch loop.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "While any projection-failure fact remains unresolved, an
unattended loop MUST stop further picking for that repository. A
human-attended `--item` dispatch MAY proceed only after the high-urgency
warning is surfaced before claim and does not clear the fact."

THE TWO POSTURES ARE ASYMMETRIC ON PURPOSE, and the asymmetry is the
whole clause. Unattended picking is stopped because nobody is watching:
the repository's fallback evidence is unread, so every hold that would
have skipped a dead candidate may be missing, and the drain would keep
launching work at it. An attended `--item` dispatch has a person behind
it, so the remedy is to TELL them -- before the claim, while the choice
is still theirs -- and then get out of the way.

SURFACING IS NOT CLEARING, and this module writes nothing that could be
mistaken for a resolution. The attended path emits operator text and a
journal line recording that the warning was surfaced; neither is a
`acp-projection-succeeded` nor a clearance, so the fact stands into the
next pass exactly as the clause requires.

STOPPING IS NOT REFUSING. The loop returns cleanly having picked
nothing, the same shape an empty ready set produces, because the
repository is not broken and no individual item is at fault. A refusal
exit code here would read as "this dispatch failed" on every surface
that greps for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    AcpProjectionFailure,
    unresolved_projection_failures,
)

__all__: list[str] = [
    "PROJECTION_ATTENDED_STAGE",
    "PROJECTION_STOP_STAGE",
    "AcpProjectionPosture",
    "acp_projection_posture",
]

PROJECTION_STOP_STAGE = "acp-projection-picking-stopped"
PROJECTION_ATTENDED_STAGE = "acp-projection-warning-surfaced"


@dataclass(frozen=True, kw_only=True)
class AcpProjectionPosture:
    """Whether this pass may pick, and what it must tell the operator first."""

    failures: tuple[AcpProjectionFailure, ...]
    attended: bool

    @property
    def stop_picking(self) -> bool:
        """Whether an UNATTENDED pass must stop picking for this repository."""
        return bool(self.failures) and not self.attended

    @property
    def warning(self) -> str | None:
        """The high-urgency text to surface BEFORE claim, or `None`.

        Rendered for both postures rather than only the attended one: the
        unattended pass that stops has to say why it picked nothing, or
        the stop is indistinguishable from an empty ready set on every
        surface an operator reads.
        """
        if not self.failures:
            return None
        lines = "".join(f"  {failure.fact_id}: {failure.summary}\n" for failure in self.failures)
        posture = (
            "This attended --item dispatch may proceed; it does not clear the fact.\n"
            if self.attended
            else "Unattended picking is stopped for this repository until projection replays.\n"
        )
        return (
            f"WARNING: {len(self.failures)} unresolved ACP fallback projection "
            f"failure(s):\n{lines}{posture}"
        )

    def journal_record(self) -> dict[str, object]:
        """The append-only line recording which posture this pass took."""
        return {
            "stage": PROJECTION_ATTENDED_STAGE if self.attended else PROJECTION_STOP_STAGE,
            "fact_ids": [failure.fact_id for failure in self.failures],
            "attended": self.attended,
        }


def acp_projection_posture(*, journal_path: Path | None, attended: bool) -> AcpProjectionPosture:
    """Read the unresolved projection failures and decide this pass's posture."""
    return AcpProjectionPosture(
        failures=unresolved_projection_failures(journal_path=journal_path), attended=attended
    )

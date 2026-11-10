"""What the filing display says about the `dod_gate` judgement it took.

`filing_display` consults the spec-stated judgement for the item's governing
heading, through the `dod_gate` candidate chain. Each candidate's outcome went
only to standard error, so a judgement whose sole reply did not parse left the
display printing `definition-of-done findings: none` — a clean answer from a
judgement that never happened (`bd-ib-4foa5q`). The front-ends show the returned
string line by line, so what the filer must learn has to be IN that string.

WHY AN UNAVAILABLE JUDGEMENT IS REPORTED ON THE FINDINGS LINE. `none` and
`judgement unavailable` are different answers to the question the line exists to
answer, and a filer who reads the first for the second may repair a record or
relaunch a dispatch on a measurement nobody took.

WHY ONLY A STARTED CANDIDATE COUNTS. A chain that resolved no candidate at all
started nothing to report, and the item with no Definition of Done section never
reaches the judge. Both keep the display they always had.

WHY THE REPLY GOES TO A FILE RATHER THAN INTO THE DISPLAY. A reply that did not
parse can be a whole page of prose, and the display is read line by line by a
filer who cannot act on it. The file is under the repository's own `tmp/`, which
is gitignored, so diagnosing the parse failure needs the text and costs the
repository nothing.

WHY A FAILED SAVE IS A LINE, NOT AN EXCEPTION. The display stays an advisory
surface that never refuses; an unwritable `tmp/` is reported beside the
candidate it concerns.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
    OUTCOME_UNPARSEABLE_VERDICT,
    CandidateAttempt,
    candidate_report,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
        CandidateChainResult,
    )

__all__: list[str] = [
    "JUDGEMENT_UNAVAILABLE_REPORT",
    "JudgementObserver",
]

# The findings line of a judgement no candidate answered, in the same leader as
# `definition-of-done findings: none` so the two read as alternatives on one line.
JUDGEMENT_UNAVAILABLE_REPORT = "definition-of-done findings: judgement unavailable"
# Where an unparseable reply is kept, relative to the repository the display ran in.
_SCRATCH_DIRNAME = "tmp"
_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(kw_only=True)
class JudgementObserver:
    """Collects the candidate chains one display's judgement ran."""

    chains: list[CandidateChainResult] = field(default_factory=list)

    def observe(self, *, chain: CandidateChainResult) -> None:
        """Take one finished chain, as `drift_judge`'s `on_chain` hands it over."""
        self.chains.append(chain)

    @property
    def unavailable(self) -> bool:
        """Whether candidates were started and none returned a parseable verdict."""
        return any(chain.attempts for chain in self.chains) and all(
            chain.reply is None for chain in self.chains
        )

    def report_lines(self, *, item_id: str, cwd: Path) -> list[str]:
        """One line per candidate started, then one per unparseable reply kept."""
        attempts = [ran for chain in self.chains for ran in chain.attempts]
        lines = [candidate_report(attempt=ran) for ran in attempts]
        lines.extend(
            _saved_reply_line(item_id=item_id, cwd=cwd, ran=ran)
            for ran in attempts
            if ran.outcome == OUTCOME_UNPARSEABLE_VERDICT
        )
        return lines


def _saved_reply_line(*, item_id: str, cwd: Path, ran: CandidateAttempt) -> str:
    """Write one unparseable reply under `tmp/` and say where, or why it was not."""
    leader = f"dod-gate: unparseable reply of agent={ran.agent} model={ran.model}"
    written = attempt(
        action=lambda: _write_reply(item_id=item_id, cwd=cwd, text=ran.reply_text),
        exceptions=(OSError,),
    )
    if isinstance(written, AttemptFailure):
        return f"{leader} could not be saved: {written.error}"
    return f"{leader} saved to {written}"


def _write_reply(*, item_id: str, cwd: Path, text: str) -> Path:
    """The reply in a new file of its own, so a second display never overwrites it."""
    scratch = cwd / _SCRATCH_DIRNAME
    scratch.mkdir(parents=True, exist_ok=True)
    safe_id = _UNSAFE_FILENAME_CHARACTERS.sub("-", item_id)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        errors="replace",
        dir=scratch,
        prefix=f"dod-gate-unparseable-{safe_id}-",
        suffix=".txt",
        delete=False,
    ) as handle:
        _ = handle.write(text)
    return Path(handle.name)

"""The display record for a governing-heading judgement it started itself."""

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

__all__: list[str] = ["JUDGEMENT_UNAVAILABLE_REPORT", "JudgementObserver"]

JUDGEMENT_UNAVAILABLE_REPORT = "definition-of-done findings: judgement unavailable"
_SCRATCH_DIRNAME = "tmp"
_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(kw_only=True)
class JudgementObserver:
    """Collect the chain that a single display's host reader ran."""

    chains: list[CandidateChainResult] = field(default_factory=list)

    def observe(self, *, chain: CandidateChainResult) -> None:
        """Remember one finished candidate chain."""
        self.chains.append(chain)

    @property
    def unavailable(self) -> bool:
        """Whether a started chain produced no parseable verdict."""
        return any(chain.attempts for chain in self.chains) and all(
            chain.reply is None for chain in self.chains
        )

    def report_lines(self, *, item_id: str, cwd: Path) -> list[str]:
        """Render candidates and preserve every unparseable reply for diagnosis."""
        attempts = [attempt for chain in self.chains for attempt in chain.attempts]
        lines = [candidate_report(attempt=attempt) for attempt in attempts]
        lines.extend(
            _saved_reply_line(item_id=item_id, cwd=cwd, ran=attempt)
            for attempt in attempts
            if attempt.outcome == OUTCOME_UNPARSEABLE_VERDICT
        )
        return lines


def _saved_reply_line(*, item_id: str, cwd: Path, ran: CandidateAttempt) -> str:
    """Save one unparseable reply, reporting a filesystem failure as display text."""
    leader = f"dod-gate: unparseable reply of agent={ran.agent} model={ran.model}"
    written = attempt(
        action=lambda: _write_reply(item_id=item_id, cwd=cwd, text=ran.reply_text),
        exceptions=(OSError,),
    )
    if isinstance(written, AttemptFailure):
        return f"{leader} could not be saved: {written.error}"
    return f"{leader} saved to {written}"


def _write_reply(*, item_id: str, cwd: Path, text: str) -> Path:
    """Write a reply into a fresh gitignored file in the governed repository."""
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

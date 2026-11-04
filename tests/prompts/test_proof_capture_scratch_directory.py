"""The proof-capture procedure must establish its replayable scratch root.

The proof verifier replays the published reproduction steps in the same
sandbox.  A record that names `${TMPDIR:-/tmp}/proof-capture` but does not
first create it cannot be executed on a clean sandbox, so the procedure must
publish the idempotent shell precondition rather than leave its creation to
inference.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROMPT = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "prompts"
    / "proof-capture.md"
)
_SCRATCH_PRECONDITION = 'mkdir -p "${TMPDIR:-/tmp}/proof-capture"'


def test_proof_capture_explicitly_creates_its_scratch_directory() -> None:
    """A replayer can run the prescribed scratch setup on a clean sandbox."""
    assert _SCRATCH_PRECONDITION in _PROMPT.read_text(encoding="utf-8")

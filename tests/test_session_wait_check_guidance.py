"""Host planning and drive guidance states what the shared `check` command covers.

Scenario 158 requires existing host guidance to use the shipped `check` command, to
derive monitoring claims from inventory, to claim automatic stop integration only
for a runtime whose hook surface is exercised, and to keep blocking host waits out of
factory execution. Each runtime ships its own copy of the drive guidance and the plan
prose carries the runtime-neutral statement, so every copy is graded on the same
common claims and the runtime-specific claims are graded on the copy they belong to.

Content assertions run against the WHITESPACE-FLATTENED text: a phrase wrapped across
a line would otherwise be absent as a literal while present as prose.
"""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN = _REPO_ROOT / ".claude-plugin"
_CLAUDE_DRIVE = _PLUGIN / "skills" / "drive" / "SKILL.md"
_CODEX_DRIVE = _PLUGIN / ".codex-plugin" / "skills" / "drive" / "SKILL.md"
_PI_DRIVE = (
    _PLUGIN / ".pi-plugin" / "skills" / "livespec-orchestrator-beads-fabro-drive" / "SKILL.md"
)
_PLAN_PROSE = _PLUGIN / "prose" / "plan.md"


def _flattened(*, path: Path) -> str:
    assert path.is_file(), f"{path} does not exist"
    return " ".join(path.read_text().split())


@pytest.mark.parametrize("path", [_CLAUDE_DRIVE, _CODEX_DRIVE, _PI_DRIVE])
def test_every_drive_copy_states_the_obligation_and_inventory_claims(path: Path) -> None:
    guidance = _flattened(path=path)

    assert "durable launch-obligation store" in guidance
    assert "even when no wait was ever armed" in guidance
    assert "unmonitored finding rather than as health" in guidance
    assert "explicit deadline and an explicit owner `ack`" in guidance
    assert "never from memory of what was armed" in guidance
    assert "A factory agent turn runs no blocking host wait" in guidance


def test_claude_guidance_claims_the_stop_hook_for_claude_only() -> None:
    guidance = _flattened(path=_CLAUDE_DRIVE)

    assert "Claude `Stop` hook runs `check` as a turn ends" in guidance
    assert "blocks the stop once on any finding" in guidance
    assert "claimed for Claude only" in guidance


@pytest.mark.parametrize("path", [_CODEX_DRIVE, _PI_DRIVE])
def test_codex_and_pi_guidance_disclose_the_missing_automatic_hook(path: Path) -> None:
    guidance = _flattened(path=path)

    assert "Automatic stop-hook coverage is NOT claimed" in guidance
    assert "has not been exercised" in guidance
    assert "Run `check` explicitly before finishing a turn or parking" in guidance
    assert "Claude `Stop` hook" not in guidance


def test_plan_prose_states_the_check_claims_and_which_runtime_has_a_hook() -> None:
    guidance = _flattened(path=_PLAN_PROSE)

    assert "durable launch-obligation store" in guidance
    assert "even when no wait was ever armed" in guidance
    assert "explicit deadline and an explicit owner `ack`" in guidance
    assert "never from memory of what was armed" in guidance
    assert "Only Claude's `Stop` hook runs `check` automatically" in guidance
    assert "Codex and pi invoke it explicitly" in guidance
    assert "A factory agent turn runs no blocking host wait" in guidance

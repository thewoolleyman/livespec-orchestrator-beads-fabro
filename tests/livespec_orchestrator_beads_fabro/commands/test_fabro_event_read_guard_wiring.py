"""The Dispatcher readers use the common Fabro event-read guard."""

from __future__ import annotations

from pathlib import Path

_COMMANDS = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_READERS = (
    "_dispatcher_fabro_second_reads.py",
    "_dispatcher_review_gate.py",
    "_dispatcher_preserved_tree_escalation.py",
)


def test_dispatcher_event_readers_use_the_common_failure_guard() -> None:
    for reader in _READERS:
        source = (_COMMANDS / reader).read_text(encoding="utf-8")
        assert "guarded_fabro_events_read" in source

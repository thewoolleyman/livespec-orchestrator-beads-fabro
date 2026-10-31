"""Fail-closed controls for Scenario 184's record-file resume classifier."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files import (
    record_file_resume_paths,
)


@pytest.mark.parametrize(
    ("config_text", "conflicted_paths"),
    [
        ("not json", ("record.json",)),
        ("[]", ("record.json",)),
        ("{}", ("record.json",)),
        ('{"livespec-orchestrator-beads-fabro": []}', ("record.json",)),
        ('{"livespec-orchestrator-beads-fabro": {}}', ("record.json",)),
        ('{"livespec-orchestrator-beads-fabro": {"dispatcher": []}}', ("record.json",)),
        ('{"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}', ("record.json",)),
        (
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": {}}}}',
            ("record.json",),
        ),
        (
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": []}}}',
            ("record.json",),
        ),
        (
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [null]}}}',
            ("record.json",),
        ),
        (
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [{}]}}}',
            ("record.json",),
        ),
        (
            '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"record_files": [{"path": "a"}, {"path": "a"}]}}}',
            ("a",),
        ),
    ],
)
def test_an_unreadable_or_ambiguous_declaration_never_admits_a_resume(
    *, config_text: str, conflicted_paths: tuple[str, ...]
) -> None:
    """Fail closed when the declared-path set cannot be established."""
    assert (
        record_file_resume_paths(config_text=config_text, conflicted_paths=conflicted_paths) is None
    )

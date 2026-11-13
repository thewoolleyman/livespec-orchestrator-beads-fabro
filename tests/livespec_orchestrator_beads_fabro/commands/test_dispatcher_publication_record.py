"""The pull-request publication binding used by recovery routing."""

from __future__ import annotations

import importlib
from pathlib import Path

_HEAD = "a" * 40
_RUN = "01M7PUBLICATIONRUN"


def test_a_record_by_the_configured_identity_binds_its_pushed_head_to_its_run() -> None:
    """A durable publication comment can attribute a head before proof exists."""
    module_path = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_publication_record.py"
    )
    assert module_path.is_file()

    records = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_publication_record"
    )
    comments = (
        {
            "author": {"login": "thewoolleyman-factory-bot[bot]"},
            "body": "\n".join(
                (
                    "livespec-publication-record",
                    f"run-id: {_RUN}",
                    f"head: {_HEAD}",
                    "pull-request: 42",
                    "stage: publish_draft",
                    "pushed-at: 2026-11-13T12:37:00Z",
                )
            ),
        },
    )

    assert records.publication_pairs(
        comments=comments, publication_identity="thewoolleyman-factory-bot[bot]"
    ) == ((_HEAD, _RUN),)

"""Tests for `_reflector_filing_store.file_new` lifecycle-status handling.

The reflector's `file_new` must land its newly-filed item in the `backlog`
lifecycle status, NOT beads' built-in default `open`. `bd create` cannot land
directly in a custom lifecycle status (the pinned bd v1.0.5 has no
`bd create --status`), so filing is a 2-step: create (lands `open`) then set
the lifecycle status. Without the follow-up the item is stuck at the
non-lifecycle `open`, which the dispatcher's status-conformance ledger-check
flags.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro.commands._reflector_filing_store import file_new
from livespec_orchestrator_beads_fabro.commands._reflector_findings_parse import ReflectorFinding


def _finding() -> ReflectorFinding:
    return ReflectorFinding(
        category="stage-timeout",
        stage="fabro-run",
        severity="critical",
        subject="repeated stage timeouts on dispatch",
        detail="a recurring observation",
        occurrences=3,
        work_item_id=None,
        score=0.4,
        label="fail",
    )


def test_file_new_sets_backlog_lifecycle_status_after_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reflector-filed item lands the `backlog` lifecycle status, not `open`."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = FakeBeadsClient()

    issue_id = file_new(
        finding=_finding(),
        fingerprint_hex="deadbeefcafe",
        client=client,
        repo=tmp_path,
    )

    record = client.show_issue(issue_id=issue_id)
    assert record["status"] == "backlog"

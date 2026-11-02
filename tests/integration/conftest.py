"""Shared isolation for integration cases that exercise fake repository storage."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_groom_fake_repository(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the groom scenario's fake journal beneath pytest's temporary directory."""
    module = request.module
    if module is None or module.__name__ != "tests.integration.test_groom_scenario7":
        return
    monkeypatch.setattr(
        module,
        "_LOCAL_REPO_ROOT",
        tmp_path / "livespec-orchestrator-beads-fabro",
    )

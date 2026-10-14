"""Wrapper resolution replaces only credential slots and fails closed."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_refresh import (
    refresh_claude_credentials,
)


@pytest.mark.parametrize(
    "wrapper",
    [
        ["/nonexistent-credential-wrapper"],
        ["invalid\0executable"],
        ["/bin/sh", "-c", "exit 4"],
        ["/bin/sh", "-c", "printf 'not-json'"],
        ["/bin/sh", "-c", "printf '[]'"],
        ["/bin/sh", "-c", 'printf \'{"UNRELATED":"value"}\''],
        ["/bin/sh", "-c", "printf '{\"CLAUDE_CODE_OAUTH_TOKEN\":7}'"],
        ["/bin/sh", "-c", "printf '{}'"],
    ],
)
def test_failed_resolution_discards_stale_slots(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrapper: list[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "stale")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__OLD", "stale-pool")
    monkeypatch.setenv("UNRELATED", "unchanged")
    (tmp_path / ".livespec.jsonc").write_text(json.dumps({"credential_wrapper": wrapper}))
    refresh_claude_credentials(repo=tmp_path)
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ
    assert "CLAUDE_CODE_OAUTH_TOKEN__OLD" not in os.environ
    assert os.environ["UNRELATED"] == "unchanged"


def test_no_wrapper_preserves_environment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "inherited")
    refresh_claude_credentials(repo=tmp_path)
    assert os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "inherited"

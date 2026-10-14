"""A parked loop reads a rotated wrapper credential without a restart."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
    ClaudeProbeObservation,
    classify_claude_probe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_env import (
    assess_credential_status,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe import (
    await_usable_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    selected_account_record_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile


@pytest.mark.parametrize("slot", ["CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN__ROTATED"])
def test_wrapper_rotation_reaches_next_probe_and_admission(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, slot: str
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    selection = selected_account_record_path(home=tmp_path)
    selection.parent.mkdir(parents=True)
    selection.write_text('{"profile": "rotated"}', encoding="utf-8")
    monkeypatch.setenv(slot, "launch-value")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "launch-value")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__REMOVED", "obsolete-slot")
    token_file = tmp_path / "current-token"
    token_file.write_text("limited-value", encoding="utf-8")
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(
        f'#!/bin/sh\nexport {slot}="$(cat current-token)"\nexec "$@"\n', encoding="utf-8"
    )
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"credential_wrapper": ["/bin/sh", str(wrapper)]}), encoding="utf-8"
    )
    probed: list[str] = []
    slept: list[float] = []

    def probe(*, token: str) -> ClaudeCredentialStatus:
        probed.append(token)
        return classify_claude_probe(
            observation=ClaudeProbeObservation(
                http_status=200 if token == "rotated-value" else 429,
                error_type=None,
                input_tokens=None,
                output_tokens=None,
            )
        )

    def rotate(seconds: float) -> None:
        slept.append(seconds)
        assert len(slept) == 1, "the next probe still used the launch-time credential"
        token_file.write_text("rotated-value", encoding="utf-8")

    await_usable_credential(
        repo=tmp_path,
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        budget=1,
        probe=probe,
        sleep=rotate,
    )

    assert probed == ["limited-value", "rotated-value"]
    assert slept == [300]
    assert assess_credential_status(repo=tmp_path, probe=probe).usable
    assert probed[-1] == "rotated-value"
    assert "CLAUDE_CODE_OAUTH_TOKEN__REMOVED" not in os.environ

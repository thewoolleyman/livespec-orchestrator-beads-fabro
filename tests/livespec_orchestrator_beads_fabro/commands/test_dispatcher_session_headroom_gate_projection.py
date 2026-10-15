"""The headroom reading assesses the credential the dispatch would PROJECT.

Binds "It MUST read the provider's five-hour session utilization using the
exact credential snapshot that the dispatch would project" in
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance".

The projection does not read the unnumbered `CLAUDE_CODE_OAUTH_TOKEN`: it
prefers the pool slot the caam-published selection names
(`_dispatcher_factory_account_selector.select_factory_credential`), and so does
the credential-usability probe. Measured 2026-10-15 (`bd-ib-nzp5ln`): with the
selection naming anthropic-3, the gate assessed the unnumbered token, whose
fingerprint equals the anthropic-1 slot, while the run would have billed
anthropic-3. A gate reading a different account from the one projected admits
or skips on someone else's window.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    SELECTED_ACCOUNT_RECORD_REL,
)

_NOW = "2026-10-15T02:00:00Z"


def _publish_selection(*, home: Path, profile: str) -> None:
    record = home / SELECTED_ACCOUNT_RECORD_REL
    record.parent.mkdir(parents=True)
    _ = record.write_text(
        json.dumps({"profile": profile, "account_uuid": "uuid", "written_at": _NOW}),
        encoding="utf-8",
    )


def test_the_reading_assesses_the_caam_selected_slot_not_the_unnumbered_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _publish_selection(home=tmp_path, profile="anthropic-3")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "unnumbered-token")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_3", "selected-token")
    tokens: list[str | None] = []

    def _read(*, token: str | None, observed_at: str) -> Any:
        tokens.append(token)
        return headroom.session_headroom_reading(
            credential_identity="cred", observed_at=observed_at, utilization=10
        )

    policy = headroom_gate.session_headroom_policy(repo=tmp_path, now_iso=_NOW, read=_read)
    _ = policy.read()

    assert tokens == ["selected-token"]

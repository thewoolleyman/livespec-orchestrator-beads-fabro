"""Shared hermetic-backend fixtures for the beads store + command tests.

Every test under `tests/livespec_orchestrator_beads_fabro/` drives the store through the
in-memory `FakeBeadsClient` rather than a live `dolt-server`. Two things
make that hermetic and isolated:

1. `LIVESPEC_BEADS_FAKE=1` is set in the environment so
   `commands._config.resolve_store_config` resolves `StoreConfig.fake=True`
   and `store.make_beads_client` returns the fake. The command modules
   (list-work-items / next) call the resolver internally, so
   this is the only seam that flips them onto the fake.
2. `reset_fake_singleton()` runs before AND after each test so the
   process-singleton fake tenant starts empty for every test — the
   accumulation-within-one-invocation behaviour the runtime relies on does
   not leak across test cases.

The fixture is autouse so individual tests do not have to opt in; a test
that never touches the store simply observes an empty fake.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterator

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton


def _fresh_codex_auth_json() -> str:
    """A host Codex `auth.json` whose access-token JWT `exp` is a century out.

    The dual-credential projection (Scenario 18 / 19) reads a host Codex
    credential and freshness-gates it against the run budget. A far-future
    `exp` keeps every dispatch test past the gate against the real clock the
    dispatch path reads. The refresh token is a placeholder —
    `project_codex_auth_snapshot` replaces it with the inert sentinel before
    the snapshot reaches the overlay.
    """
    exp = int(time.time()) + 100 * 365 * 24 * 3600
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    # No test may make a real ntfy POST. The dispatcher's fail-open
    # terminal-failure alarm (work-item livespec-impl-beads-h1p) resolves
    # its topic from these env vars and POSTs via urllib; the host carries
    # a live CLAUDE_NTFY_TOPIC, so an unscrubbed env would let a failed /
    # blocked / non-green-loop dispatch test fire a real network request.
    # Scrubbing them makes the notifier a silent no-op by default; tests
    # that exercise a delivered POST set the env back explicitly and inject
    # a recording poster.
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    # No test may read the real host `~/.codex/auth.json`. The dispatch
    # path projects a freshness-gated snapshot of the host Codex credential
    # into the sandbox (Scenario 18); point CODEX_HOME at a scratch dir
    # carrying a fresh fake credential so every dispatch test is hermetic
    # and the gate passes. Tests asserting the missing/stale paths override
    # this explicitly (delenv / point at an empty dir / monkeypatch the read).
    codex_home = tmp_path_factory.mktemp("codex-home")
    _ = (codex_home / "auth.json").write_text(_fresh_codex_auth_json(), encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    reset_fake_singleton()
    yield
    reset_fake_singleton()

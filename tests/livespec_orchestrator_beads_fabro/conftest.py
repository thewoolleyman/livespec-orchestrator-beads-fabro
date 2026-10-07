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

from collections.abc import Iterator

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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
    reset_fake_singleton()
    yield
    reset_fake_singleton()

"""Shared hermetic-backend fixtures for the beads store + command tests.

Every test under `tests/livespec_impl_beads/` drives the store through the
in-memory `FakeBeadsClient` rather than a live `dolt-server`. Two things
make that hermetic and isolated:

1. `LIVESPEC_BEADS_FAKE=1` is set in the environment so
   `commands._config.resolve_store_config` resolves `StoreConfig.fake=True`
   and `store.make_beads_client` returns the fake. The command modules
   (list-work-items / list-memos / next) call the resolver internally, so
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
from livespec_impl_beads._beads_client import reset_fake_singleton


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()

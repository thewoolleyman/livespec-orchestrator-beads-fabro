"""One dispatch pass reads the ready-dwell instants once, however many orderings it builds.

Each `ready_aging_order` call returned a lookup that read the whole ledger on its first
use (`bd list --status all --limit 0` and a parse of every record). A dispatch builds
several: the ready queue, the rework projection admission takes, and the idle-slot
holds, so the same dump was taken again for each. The instants are an ordering
tiebreak that no write inside the pass changes for a row still ready, so the pass
shares one reading, as it already shares the journal and `fabro inspect`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro import _beads_client_fake
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import pass_snapshot
from livespec_orchestrator_beads_fabro.commands._ready_aging_order import ready_aging_order


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_a_pass_reads_the_ready_dwell_instants_once_and_a_bare_call_reads_each_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    listings: list[None] = []
    original = _beads_client_fake.FakeBeadsClient.list_issues

    def counting(self: _beads_client_fake.FakeBeadsClient) -> list[dict[str, object]]:
        listings.append(None)
        return original(self)

    monkeypatch.setattr(_beads_client_fake.FakeBeadsClient, "list_issues", counting)

    with pass_snapshot():
        first = ready_aging_order(project_root=repo).ready_since_lookup
        second = ready_aging_order(project_root=repo).ready_since_lookup
        _ = first("bd-ib-one")
        _ = second("bd-ib-two")
    in_a_pass = len(listings)
    _ = ready_aging_order(project_root=repo).ready_since_lookup("bd-ib-three")
    _ = ready_aging_order(project_root=repo).ready_since_lookup("bd-ib-four")

    assert (in_a_pass, len(listings)) == (1, 3)

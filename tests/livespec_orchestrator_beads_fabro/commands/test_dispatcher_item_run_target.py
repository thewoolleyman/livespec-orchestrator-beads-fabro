"""Which factory one item's run is looked for on, and what cannot be read.

`SPECIFICATION/contracts.md` — cited at FILE level, because a heading-level
citation rots the moment the heading is reworded — requires Fabro capability to
be "read from the dispatch's resolved factory server, never a local binary".
`AGENTS.md` records the cost of getting it wrong: a bare `fabro` invocation
answers for `127.0.0.1` and reports `No running processes found` while the
dispatch is perfectly healthy on `hp` — a clean, plausible, entirely wrong
answer with no error.

BOTH ARMS ARE ASSERTED, and the pairing is the point. A resolution that answered
`None` for everything would satisfy the unresolvable case exactly as well as a
correct one, and one that answered the configured default for everything would
satisfy the resolved case; only the two together say the reading discriminates.

THE UNREADABLE-TENANT ARM IS THE ORDINARY ONE, not an edge. The item's recorded
`dispatch_factory` stamp lives in the beads tenant, and every caller of this
resolution runs AFTER the work it follows has finished — so a tenant this host
cannot reach must degrade to the repository default rather than raise through a
caller that has nothing left to do. Both fixtures below declare no connection
block, which is exactly that degradation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_run_target import (
    ACP_EVENTS_TIMEOUT_SECONDS,
    resolve_item_run_factory,
)

_ITEM = "bd-ib-qm6r1"


def _repo(*, tmp_path: Path, dispatcher: dict[str, object]) -> Path:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return tmp_path


def test_the_configured_default_factory_resolves_when_the_stamp_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repository declaring a default resolves it, stamp or no stamp."""
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher={
            "default_factory": "hp",
            "factories": {"hp": {"server": "https://hp.example.test:32276"}},
        },
    )

    target = resolve_item_run_factory(repo=repo, work_item_id=_ITEM)

    assert target is not None
    assert (target.name, target.server) == ("hp", "https://hp.example.test:32276")


def test_a_factory_declaring_no_server_resolves_to_no_target_at_all(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`None` rather than a target whose server is the ambient local engine's.

    A `FactoryTarget` carrying `server=None` is what an unconfigured repository
    holds, and every consumer reads that as the LOCAL engine — so answering
    with one would survey whichever Fabro the dispatching host happens to run
    and report a clean answer taken on the wrong machine.
    """
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    repo = _repo(tmp_path=tmp_path, dispatcher={"default_factory": "missing"})

    assert resolve_item_run_factory(repo=repo, work_item_id=_ITEM) is None


def test_the_events_read_is_bounded_well_below_the_run_survey() -> None:
    """The bound the retired projection declared, which the cost read still needs."""
    assert ACP_EVENTS_TIMEOUT_SECONDS == 30.0

"""A repository declaring NO fallback chain is still assessed for headroom.

Binds the sentence of the "Admission filters candidates by projected Claude
session headroom" paragraph of `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance" that the implementation skipped
outright: the Dispatcher MUST "assess every otherwise-selectable covered
candidate on an admission-required ACP node, including covered fallbacks and
built-in single-candidate nodes without fallback metadata".

WHY THIS FILE EXISTS, recorded because the gap it closes was invisible from
every repository that happened to declare chains. `resolve_acp_preflight`
returned the viable no-op verdict as soon as `repository_acp_chains` found no
ENABLED chain, which is strictly earlier than the policy the admission pass
hands it -- so the assessment was gated on a repository declaring fallback
metadata rather than on the clause's own coverage rule. Measured 2026-10-17 on
plugin build 87cab2ae2047: this repository, which declares eight enabled
chains, journaled an `acp-session-headroom` record on each of two admission
evaluations, while a fresh dispatch in `livespec-dev-tooling`, which declares
none, journaled ZERO and named a built-in candidate on every node. The
one-account five-hour window relies on this gate as its brake, so every
repository without fallback chains was dispatching with no brake at all.

THE FIXTURE IS A REPOSITORY THAT DECLARES NOTHING, which is the population
under test rather than a stand-in for it. An empty `.livespec.jsonc` leaves
`dispatcher.acp_nodes` absent, so every node resolves through the bundled
default workflow to exactly one built-in Claude adapter carrying a built-in
identity -- the same shape the measurement above found in `livespec-dev-tooling`
(`builtin-anthropic-ff4ec159a0288eb8` on `implement`). Nothing about the
assessment is injected except the provider read itself.

THE POLICY IS BUILT BY THE PRODUCTION BUILDER with only that read injected, and
the read is COUNTED. The clause's "One assessment per distinct projected
credential per admission evaluation MUST be reused across nodes and candidates
sharing that credential" is the builder's memo, so a hand-constructed policy
here would assert this test's own stand-in and say nothing about the pair that
runs in production -- and the record count alone cannot tell one assessment
reused across eight nodes from eight assessments that happened to agree.
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
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_acp_preflight,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_NOW = "2026-10-17T16:46:00Z"
_FLOOR = 20
_TOKEN = "projected-token"


def _no_fallback_repo(*, tmp_path: Path) -> Path:
    """A repository declaring no ACP configuration of any kind."""
    repo = tmp_path / "governed"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{}\n", encoding="utf-8")
    return repo


def _records(*, journal_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_a_repository_with_no_fallback_chain_journals_one_headroom_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One record per distinct projected credential, on the no-fallback path.

    The eight nodes of the default workflow share ONE projected credential, so
    the clause's reuse rule makes this exactly one provider read and exactly
    one journaled assessment -- not eight of either.
    """
    reads: list[str | None] = []
    reading = headroom.session_headroom_reading(
        credential_identity="cred-no-fallback", observed_at=_NOW, utilization=95
    )

    def counting_read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        _ = observed_at
        reads.append(token)
        return reading

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    repo = _no_fallback_repo(tmp_path=tmp_path)
    journal_path = tmp_path / "journal.jsonl"
    # The fixture declares no floor, so the builder resolves the RATIFIED
    # default -- the governing floor for every repository that has not set the
    # dial, and therefore the one this case must measure against.
    assert headroom.DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT == _FLOOR

    verdict = resolve_acp_preflight(
        repo=repo,
        journal_path=journal_path,
        now_iso=_NOW,
        headroom=headroom_gate.session_headroom_policy(
            repo=repo, now_iso=_NOW, journal_path=journal_path, read=counting_read
        ),
    )
    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-vim5gc",
        verdict=verdict,
        journal=JournalFile(path=journal_path),
    )

    # The repository under test declares no fallback-enabled chain: that is the
    # population, established rather than assumed, so a fixture that acquired
    # one fails HERE instead of making the rest of the case vacuous.
    assert verdict.fallback_enabled is False
    assert reads == [_TOKEN]
    assert [reading.credential_identity for reading in verdict.headroom_assessments] == [
        "cred-no-fallback"
    ]

    assessments = [
        record
        for record in _records(journal_path=journal_path)
        if record["stage"] == SESSION_HEADROOM_STAGE
    ]
    assert len(assessments) == 1
    assert assessments[0]["work_item_id"] == "bd-ib-vim5gc"
    assert assessments[0]["session_headroom_floor_percent"] == _FLOOR
    assert [entry["credential_identity"] for entry in assessments[0]["assessments"]] == [
        "cred-no-fallback"
    ]

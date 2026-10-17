"""The two negatives that keep the no-fallback assessment from being a blanket.

Controls for `test_acp_session_headroom_no_fallback_repository.py` and
`test_acp_session_headroom_no_fallback_refusal.py`, and they are what give those
two meaning: without them, a build that took a reading for EVERY no-fallback
repository and journaled a row on EVERY call would satisfy both while issuing a
usage request on surfaces the clause forbids one on.

THE FIRST NEGATIVE IS COVERAGE. The headroom clause of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance" assesses a COVERED candidate -- resolved `claude-acp`
provenance, or a built-in Claude identity -- and says "Arbitrary manual adapters
and other agents are outside this clause's coverage". A repository that
overrides every node with an arbitrary adapter is therefore inside the new
no-fallback path and still owes no reading, so both the request and the journal
row must be absent. Its fixture differs from the covered one by exactly the
per-node `command` overrides, which carry no fallback metadata -- the entry
stays legacy, so this is the same no-fallback path and not a second one.

THE SECOND NEGATIVE IS THE SURFACE. "Snapshot composition MUST NOT issue a live
usage request", and the two consumers that compose one -- the availability wait
and the needs-attention idle-factory read -- supply no policy at all. So the
absent policy must keep the short-circuit intact, which is asserted by counting
the CHAIN-SOURCE RESOLUTIONS rather than by reading the verdict alone: a verdict
can be the no-op while the resolution that would have reached a provider has
already been spent, and only the count tells those two apart. The call shape of
the needs-attention caller is bound here too, because the guarantee rests on
that caller continuing to pass no policy and nothing else in the suite says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _dispatcher_acp_preflight as preflight
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands import _needs_attention_waits as waits
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import no_fallback_verdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

_NOW = "2026-10-17T16:46:00Z"
_TOKEN = "projected-token"

# The value the instrument control feeds its own recorder, kept apart from the
# projected one so a reading that leaked from the control into a measurement
# would be visible rather than indistinguishable from the real thing.
_CONTROL_TOKEN = "instrument-control"

# Every ACP node of the default workflow, overridden to an adapter that is not a
# built-in and resolves through no agent entry. A `command`-only entry carries no
# fallback metadata, so the node stays on the legacy path.
_UNCOVERED_NODES = (
    "disposition",
    "dod_gate",
    "fix",
    "implement",
    "proof_capture",
    "proof_verify",
    "review",
    "review_fix",
)


def _repo(*, tmp_path: Path, config: dict[str, Any]) -> Path:
    repo = tmp_path / "governed"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


def _uncovered_config() -> dict[str, Any]:
    return {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {
                "acp_nodes": {node: {"command": "uncovered-adapter"} for node in _UNCOVERED_NODES}
            }
        }
    }


def test_a_no_fallback_repository_with_no_covered_candidate_reads_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No covered candidate: no usage request, and no assessment row."""
    reads: list[str | None] = []

    def counting_read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        reads.append(token)
        return headroom.session_headroom_reading(
            credential_identity="cred-unused", observed_at=observed_at, utilization=95
        )

    # THE INSTRUMENT CONTROL, taken before the measurement: the recorder DOES
    # record, so the empty list below is the filter declining to read and not a
    # counter that could never have reported one.
    _ = counting_read(token=_CONTROL_TOKEN, observed_at=_NOW)
    assert reads == [_CONTROL_TOKEN]
    reads.clear()

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    repo = _repo(tmp_path=tmp_path, config=_uncovered_config())
    journal_path = tmp_path / "journal.jsonl"

    verdict = preflight.resolve_acp_preflight(
        repo=repo,
        journal_path=journal_path,
        now_iso=_NOW,
        headroom=headroom_gate.session_headroom_policy(
            repo=repo, now_iso=_NOW, journal_path=journal_path, read=counting_read
        ),
    )
    headroom_gate.journal_session_headroom(
        work_item_id="bd-ib-uncovered",
        verdict=verdict,
        journal=JournalFile(path=journal_path),
    )

    # The population: still the no-fallback path, and still graded -- its nodes
    # were filtered, they just carry nothing this clause covers. Without this
    # the case would pass for a repository the path never reached at all.
    assert verdict.fallback_enabled is False
    assert verdict.nodes != ()
    assert verdict.viable is True

    assert reads == []
    assert verdict.headroom_assessments == ()
    assert not journal_path.exists() or not [
        line
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if SESSION_HEADROOM_STAGE in line
    ]


def test_a_no_fallback_repository_with_no_policy_resolves_no_chain_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The policy-free surfaces keep the whole short-circuit, reads included.

    THE POSITIVE CONTROL RUNS FIRST, through the SAME recorder and the SAME
    fixture: with a policy supplied the resolution IS taken and the provider IS
    read, so the two empty lists afterwards are the short-circuit holding rather
    than a fixture that could never have done any work or a recorder that could
    never have reported it.
    """
    resolutions: list[Path] = []
    reads: list[str | None] = []
    real_sources = preflight.repository_acp_chain_sources

    def counting_sources(**kwargs: Any) -> Any:
        resolutions.append(kwargs["repo"])
        return real_sources(**kwargs)

    def counting_read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        reads.append(token)
        return headroom.session_headroom_reading(
            credential_identity="cred-control", observed_at=observed_at, utilization=0
        )

    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _TOKEN)
    monkeypatch.setattr(preflight, "repository_acp_chain_sources", counting_sources)
    repo = _repo(tmp_path=tmp_path, config={})
    journal_path = tmp_path / "journal.jsonl"

    _ = preflight.resolve_acp_preflight(
        repo=repo,
        journal_path=journal_path,
        now_iso=_NOW,
        headroom=headroom_gate.session_headroom_policy(
            repo=repo, now_iso=_NOW, journal_path=journal_path, read=counting_read
        ),
    )
    assert (resolutions, reads) == ([repo], [_TOKEN])
    resolutions.clear()
    reads.clear()

    verdict = preflight.resolve_acp_preflight(repo=repo, journal_path=journal_path, now_iso=_NOW)

    assert verdict == no_fallback_verdict()
    assert verdict.session_headroom_floor_percent is None
    assert (resolutions, reads) == ([], [])


def test_the_needs_attention_wait_read_supplies_no_headroom_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller half of the guarantee above, bound at its own call site."""
    calls: list[dict[str, Any]] = []

    def recording_preflight(**kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return no_fallback_verdict()

    monkeypatch.setattr(waits, "resolve_acp_preflight", recording_preflight)

    assert waits.acp_chain_wait_active(project_root=tmp_path) is False
    assert [call.get("headroom") for call in calls] == [None]

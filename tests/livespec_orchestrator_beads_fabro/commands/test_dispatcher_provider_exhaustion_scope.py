"""The legacy provider gate's SCOPE: which providers, and which candidates.

Binds the two halves of defect D6 of
`plan/factory-configurable-model-fallback-priority/research/dispatcher-fallback-downsides-2026-10-12.md`
against `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" and the Scenario 60 scenario "A hold on one provider does not refuse
an item wholly on another":

- The set of providers a dispatch can be refused on is DERIVED -- from the
  journal's own live records, and from the adapters this dispatch's nodes
  resolved to -- rather than read off a hard-coded `("anthropic", "codex")`
  tuple. A record naming a vendor outside that retired pair was previously
  unreadable, which is the failure mode an absence-shaped instrument cannot
  announce: it returned a clean, plausible "no record held".
- A record only refuses when it COVERS one of the candidates those adapters
  render.

THE DISCRIMINATING CASE IS THE NEGATIVE ONE, and it is why the controls are
paired. Before this scoping, a codex record refused an all-Anthropic dispatch
with a journal line that looked exactly like a genuine vendor ceiling; after
it, the same journal must admit. So each negative below sits beside a positive
on the SAME journal, proving the gate can still return a hit rather than that
it has been blinded.

Everything is HERMETIC: the journal is a file in `tmp_path`, candidates are
built in memory, no adapter is launched and no provider is reached.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-12T12:00:00Z"
_LIVE_EXPIRY = "2026-10-12T12:10:00Z"
_PAST_EXPIRY = "2026-10-12T11:50:00Z"

_BUILTIN_ANTHROPIC = ("anthropic", "builtin-anthropic-0000000000000000")
_BUILTIN_CODEX = ("codex", "builtin-codex-0000000000000000")
# A vendor the retired tuple never named. A record for it was previously
# unreachable by any read in this module.
_THIRD_VENDOR = "zeta-router"


def _module() -> Any:
    return importlib.import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")


def _observation(*, provider: str, expires_at: str) -> dict[str, object]:
    return {
        "at": _NOW,
        "stage": "provider-exhaustion-observed",
        "work_item_id": f"bd-{provider}",
        "provider": provider,
        "governing_condition": "provider_usage_limit",
        "record_expires_at": expires_at,
    }


def _journal(*, tmp_path: Path, records: tuple[dict[str, object], ...]) -> Path:
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")
    return path


def _rendered(*, pair: tuple[str, str] | None, builtin: bool) -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    dispatch_coverage = importlib.import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    identity = (
        None
        if pair is None
        else schema.AcpCandidateIdentity(
            display_name="candidate", candidate_key=pair[1], availability_key=pair[0]
        )
    )
    return dispatch_coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="adapter", env={}, args=()),
            identity=identity,
        ),
        builtin=builtin,
    )


def test_the_retired_vendor_tuple_no_longer_bounds_which_records_are_read(
    tmp_path: Path,
) -> None:
    """D6: a record outside `("anthropic", "codex")` was silently unreadable."""
    exhaustion = _module()
    assert "DISPATCH_PROVIDERS" not in exhaustion.__all__
    assert not hasattr(exhaustion, "DISPATCH_PROVIDERS")
    journal = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(provider="anthropic", expires_at=_LIVE_EXPIRY),
            _observation(provider="codex", expires_at=_LIVE_EXPIRY),
            _observation(provider="expired-vendor", expires_at=_PAST_EXPIRY),
            _observation(provider=_THIRD_VENDOR, expires_at=_LIVE_EXPIRY),
        ),
    )

    live = exhaustion.live_provider_exhaustions(journal_path=journal, now_iso=_NOW)

    # Newest observation first, every provider the JOURNAL names, and the
    # expired one absent -- enumeration is a fact about the records rather
    # than about a vendor list this build happens to carry.
    assert [record.provider for record in live] == [_THIRD_VENDOR, "codex", "anthropic"]
    assert (
        exhaustion.active_provider_exhaustion(
            provider=_THIRD_VENDOR, journal_path=journal, now_iso=_NOW
        )
        is not None
    )
    assert exhaustion.live_provider_exhaustions(journal_path=None, now_iso=_NOW) == ()
    assert (
        exhaustion.live_provider_exhaustions(journal_path=tmp_path / "absent", now_iso=_NOW) == ()
    )


def test_a_providers_newest_live_observation_wins_and_a_clearance_retires_it(
    tmp_path: Path,
) -> None:
    """One record per provider: the newest decides, and a clearance retires it."""
    exhaustion = _module()
    journal = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(provider="codex", expires_at=_LIVE_EXPIRY),
            {
                "stage": "provider-exhaustion-cleared",
                "provider": "anthropic",
                "governing_condition": "provider_usage_limit",
                "reason": "operator cleared",
            },
            _observation(provider="codex", expires_at=_LIVE_EXPIRY),
        ),
    )

    live = exhaustion.live_provider_exhaustions(journal_path=journal, now_iso=_NOW)

    assert [record.provider for record in live] == ["codex"]
    # The factory-wide read the awareness surface consumes answers with that
    # newest live record whatever vendor it names.
    held = exhaustion.dispatch_provider_exhaustion(journal_path=journal, now_iso=_NOW)
    assert held is not None
    assert held.provider == "codex"


def test_the_providers_a_dispatch_can_be_refused_on_come_from_its_own_adapters(
    tmp_path: Path,
) -> None:
    """Scenario 60: a hold on one provider cannot refuse a dispatch outside it."""
    exhaustion = _module()
    journal = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(provider="anthropic", expires_at=_LIVE_EXPIRY),
            _observation(provider="codex", expires_at=_LIVE_EXPIRY),
        ),
    )

    def covering(*, candidates: tuple[Any, ...] | None) -> Any:
        # Every record on this journal is provider-only, so the ACCOUNT axis
        # (`test_dispatcher_exhaustion_identity_scoped_coverage`) is vacuous
        # here and the projected set it is compared against is empty.
        return exhaustion.covering_provider_exhaustion(
            journal_path=journal,
            now_iso=_NOW,
            candidates=candidates,
            projected_identities=frozenset(),
        )

    anthropic_only = (_rendered(pair=_BUILTIN_ANTHROPIC, builtin=True),)
    codex_only = (_rendered(pair=_BUILTIN_CODEX, builtin=True),)
    elsewhere = (_rendered(pair=("zeta-account", "zeta/model"), builtin=False),)

    # Each dispatch is refused on its OWN domain's record and on no other,
    # from one journal holding both.
    assert covering(candidates=anthropic_only).provider == "anthropic"
    assert covering(candidates=codex_only).provider == "codex"
    assert covering(candidates=elsewhere) is None
    # An UNREADABLE resolution is not an empty candidate set: it fails
    # CLOSED onto the pre-scoping behaviour, where any live record refuses.
    assert covering(candidates=None) is not None


class _RecordingJournal:
    """The journal seam, recording what the refusal wrote rather than writing."""

    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_the_refusal_fires_only_on_a_record_covering_a_rendered_candidate(
    tmp_path: Path,
) -> None:
    """D6: the first refusal in the ladder refused whatever the item's nodes use."""
    exhaustion = _module()
    assert (
        "candidates" in inspect.signature(exhaustion.provider_exhaustion_refusal).parameters
    ), "the refusal is not scoped to the candidates the dispatch renders yet"
    journal_path = _journal(
        tmp_path=tmp_path, records=(_observation(provider="codex", expires_at=_LIVE_EXPIRY),)
    )

    def refusal(*, candidates: tuple[Any, ...] | None) -> tuple[Any, list[dict[str, object]]]:
        journal = _RecordingJournal()
        outcome = exhaustion.provider_exhaustion_refusal(
            work_item_id="bd-item",
            journal=journal,
            journal_path=journal_path,
            now_iso=_NOW,
            candidates=candidates,
            projected_identities=frozenset(),
        )
        return outcome, journal.records

    admitted, quiet = refusal(candidates=(_rendered(pair=_BUILTIN_ANTHROPIC, builtin=True),))
    refused, written = refusal(candidates=(_rendered(pair=_BUILTIN_CODEX, builtin=True),))
    blinded, _ = refusal(candidates=None)

    # An all-Anthropic dispatch is admitted by the valve, and nothing is
    # journaled for it: a refusal record naming the codex hold is exactly
    # what Scenario 60 forbids.
    assert admitted is None
    assert quiet == []
    # The control: the SAME journal still refuses a dispatch that renders a
    # covered candidate, and still names the vendor from the record.
    assert refused is not None
    assert refused.status == "provider-exhaustion"
    assert "provider=codex" in refused.detail
    assert [record["stage"] for record in written] == ["outcome", "provider-exhaustion-refusal"]
    assert blinded is not None

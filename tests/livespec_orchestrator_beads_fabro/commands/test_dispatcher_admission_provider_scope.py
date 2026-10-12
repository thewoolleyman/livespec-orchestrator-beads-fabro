"""The ADMISSION VALVE's own answer: a hold elsewhere does not refuse this item.

Binds the Scenario 60 scenario "A hold on one provider does not refuse an item
wholly on another" at the surface that decides it -- `filter_eligible_candidates`,
whose first per-row refusal is the legacy provider gate -- rather than at the
gate's own seam, which `test_dispatcher_provider_exhaustion_scope` already
covers. The two tiers answer different questions: that one asks whether the
gate scopes correctly when handed a candidate set, and this one asks whether
the valve RESOLVES that set at all. A valve that threaded nothing down would
satisfy every assertion in the other file and still refuse every dispatch,
because the unreadable arm deliberately fails closed.

THE CONTROL IS ON THE SAME JOURNAL, and it is what separates scoping from
blinding. A codex record must admit this repository-shaped dispatch, whose
nodes resolve to the build's own Anthropic adapters; an anthropic record
appended to that same journal must then refuse it. Without the second half,
a gate that had simply stopped reading the journal would pass.

The second case asserts the resolution is spent ONCE PER PASS. The module's
own docstring makes that a cost claim about the least item-specific
conditions, and a per-row resolution re-reads one repository's committed
configuration, workflow manifest and overlays once per candidate to reach the
same answer -- which is invisible from any outcome, since every row is
refused or admitted identically either way.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_EXHAUSTION_REFUSAL_STAGE = "provider-exhaustion"
_ELIGIBILITY = "livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility"


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="Ready candidate",
        description="## Definition of Done\n\n- The product satisfies one assertion.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-12T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _fixture(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ids: tuple[str, ...]
) -> tuple[Path, list[WorkItem], JournalFile]:
    """A `ready` wave in a repository whose nodes resolve to built-in adapters."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "livespec-impl-beads",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"adopted_assertion_count_ceiling": None},
                }
            }
        ),
        encoding="utf-8",
    )
    config = _config(repo_root=repo)
    items = [_item(item_id=item_id) for item_id in ids]
    for item in items:
        append_work_item(path=config, item=item)
    return repo, items, JournalFile(path=repo / "journal.jsonl")


def _seed(*, journal: JournalFile, provider: str) -> None:
    journal.append(
        record={
            "stage": "provider-exhaustion-observed",
            "work_item_id": "bd-other",
            "provider": provider,
            "governing_condition": "provider_usage_limit",
            "record_expires_at": "2099-01-01T00:00:00Z",
        }
    )


def _viable() -> AcpPreflightVerdict:
    return AcpPreflightVerdict(fallback_enabled=True, success_critical=("implement",))


def test_a_ready_item_whose_candidates_are_all_elsewhere_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario 60: the codex hold names no candidate this dispatch renders."""
    repo, items, journal = _fixture(tmp_path=tmp_path, monkeypatch=monkeypatch, ids=("bd-one",))
    _seed(journal=journal, provider="codex")

    admittable, refused = filter_eligible_candidates(
        repo=repo, preflight=_viable(), candidates=list(items), journal=journal
    )

    assert refused == []
    assert [item.id for item in admittable] == ["bd-one"]

    # The control, on the SAME journal: a record on the domain this
    # dispatch's own adapters DO render still refuses it, which is what
    # tells scoping apart from a gate that stopped reading the journal.
    _seed(journal=journal, provider="anthropic")
    held, held_refusals = filter_eligible_candidates(
        repo=repo, preflight=_viable(), candidates=list(items), journal=journal
    )

    assert held == []
    assert [outcome.stage for outcome in held_refusals] == [_EXHAUSTION_REFUSAL_STAGE]
    assert "provider=anthropic" in held_refusals[0].detail


def test_the_rendered_candidates_are_resolved_once_per_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Committed configuration is the least item-specific condition of all."""
    repo, items, journal = _fixture(
        tmp_path=tmp_path, monkeypatch=monkeypatch, ids=("bd-one", "bd-two")
    )
    eligibility = import_module(_ELIGIBILITY)
    resolutions: list[Path] = []
    resolve = eligibility.resolve_dispatch_candidates

    def _counted_resolve(*, repo: Path) -> object:
        resolutions.append(repo)
        return resolve(repo=repo)

    monkeypatch.setattr(eligibility, "resolve_dispatch_candidates", _counted_resolve)

    admittable, refused = filter_eligible_candidates(
        repo=repo, preflight=_viable(), candidates=list(items), journal=journal
    )

    assert refused == []
    assert [item.id for item in admittable] == ["bd-one", "bd-two"]
    assert resolutions == [repo]

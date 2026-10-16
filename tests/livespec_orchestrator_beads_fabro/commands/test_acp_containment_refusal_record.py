"""The containment refusal an emptied admission-required chain writes.

Binds `SPECIFICATION/contracts.md` section "Provider spend containment" ->
"No silent containment": "A containment refusal MUST carry at minimum the
work-item id, governing condition, admission-required node lacking an eligible
candidate, and scheduled reevaluation instant. It MUST name applicable hold
observations and their expiries when present." And the rest state the same
refusal leaves behind, from section "Factory-configurable ACP fallback
priority": "the item MUST remain ready without a claim or blocked reason".

THE REST STATE IS ASSERTED THROUGH THE STORE AND THE LOCK, NOT THROUGH THE
RETURNED OUTCOME. A refused row looks identical from its outcome whichever
condition refused it, and "without a claim" is a claim about writes that did
NOT happen -- so the status is re-read from the ledger, `blocked_reason` is
read off that same re-read row, and the dispatch-lock path is asserted absent.
An implementation that refused correctly while parking the row would satisfy
every assertion about the record and none of these.

THE VIABLE CONTROL IS WHAT MAKES THE RECORD ASSERTIONS MEAN ANYTHING. A
journal writer that appended these fields unconditionally would satisfy every
positive case here; the viable verdict asserts no refusal record is written at
all, and the configuration-refusal case asserts the pre-existing record stays
free of wait fields -- because an unsupported graph is not an availability wait
and naming an instant for it would report a committed configuration fault as a
provider outage that expires on its own.

THE INTERVAL IS READ FROM COMMITTED CONFIGURATION, and the fixture commits a
NON-DEFAULT one. The default is 300 seconds, so a resolver that ignored the
repository's key would still produce a well-formed instant -- and the only
fixture that can tell the two apart is one whose configured value differs.

THE TWO NEW SURFACES ARE REACHED THROUGH THEIR MODULES rather than imported at
the top, and each case asserts the surface EXISTS before using it. A top-level
import of a name that does not exist yet would make this module's Red a
collection error -- zero assertions run -- which proves only unimportability
and not that the behaviour is unimplemented.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    HEADROOM_SKIP,
    TYPED_HOLD_SKIP,
    NodePreflight,
    SkippedCandidate,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import AcpAvailabilityHold
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    ACP_PREFLIGHT_REFUSAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility import (
    filter_eligible_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_COMMANDS = "livespec_orchestrator_beads_fabro.commands"


def _verdict_type() -> Any:
    """`AcpPreflightVerdict`, asserted to carry the one-evaluation hold set."""
    verdict_type = import_module(f"{_COMMANDS}._acp_preflight_verdict").AcpPreflightVerdict
    assert (
        "holds" in verdict_type.__dataclass_fields__
    ), "AcpPreflightVerdict does not carry the evaluation's holds yet"
    return verdict_type


def _resolve_availability_wait() -> Any:
    module = import_module(f"{_COMMANDS}._dispatcher_acp_preflight")
    assert hasattr(
        module, "resolve_availability_wait"
    ), "resolve_availability_wait is not implemented yet"
    return module.resolve_availability_wait


_ITEM_ID = "bd-waiting"
_NOW = "2026-10-15T12:00:00Z"

# Deliberately NOT the 300-second default: a resolver ignoring the committed
# key would still produce a well-formed instant, just the wrong one.
_INTERVAL = 900
_NOW_PLUS_INTERVAL = "2026-10-15T12:15:00Z"
_NOW_PLUS_DEFAULT = "2026-10-15T12:05:00Z"

_HOLD_EXPIRY = "2026-10-15T12:40:00Z"
_DOMAIN = "availability-domain"


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


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Waiting on an emptied conditional chain",
        description="## Definition of Done\n\n- The product waits.\n",
        origin="freeform",
        gap_id=None,
        rank="a4",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def _repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, StoreConfig]:
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
                    "dispatcher": {"credential_reprobe_interval_seconds": _INTERVAL},
                }
            }
        ),
        encoding="utf-8",
    )
    config = _config(repo_root=repo)
    append_work_item(path=config, item=_item())
    return repo, config


def _hold() -> AcpAvailabilityHold:
    return AcpAvailabilityHold(
        schema_version=1,
        observation_id="obs-fix",
        scope=_DOMAIN,
        hold_key="codex",
        candidate_key=None,
        cause="quota",
        occurred_at=_NOW,
        expires_at=_HOLD_EXPIRY,
    )


def _skip(*, reason: str) -> SkippedCandidate:
    if reason == TYPED_HOLD_SKIP:
        return SkippedCandidate(
            availability_key="codex",
            candidate_key="only",
            reason=reason,
            cause="quota",
            scope=_DOMAIN,
            hold_key="codex",
        )
    return SkippedCandidate(availability_key="anthropic", candidate_key="only", reason=reason)


def _emptied_verdict(*, reason: str, holds: tuple[AcpAvailabilityHold, ...]) -> Any:
    """A verdict whose conditional `fix` node has no eligible candidate left."""
    return _verdict_type()(
        fallback_enabled=True,
        nodes=(
            NodePreflight(node="fix", enabled=True, candidates=(), skipped=(_skip(reason=reason),)),
        ),
        success_critical=("implement",),
        admission_required=("implement", "fix"),
        exhausted=("fix",),
        holds=holds,
    )


def _viable_verdict() -> Any:
    return _verdict_type()(
        fallback_enabled=True,
        success_critical=("implement",),
        admission_required=("implement", "fix"),
    )


def _configuration_refusal_verdict() -> Any:
    return _verdict_type()(
        fallback_enabled=True, refusal="workflow graph is unsupported for fallback"
    )


def _refusal_records(*, journal: JournalFile) -> list[dict[str, Any]]:
    if not journal.path.is_file():
        return []
    records = [
        json.loads(line) for line in journal.path.read_text(encoding="utf-8").splitlines() if line
    ]
    return [record for record in records if record.get("stage") == ACP_PREFLIGHT_REFUSAL_STAGE]


def _run_filter(
    *, repo: Path, verdict: Any, journal: JournalFile
) -> tuple[list[WorkItem], list[Any]]:
    return filter_eligible_candidates(
        repo=repo, preflight=verdict, candidates=[_item()], journal=journal
    )


def _reread(*, config: StoreConfig) -> WorkItem:
    return materialize_work_items(records=read_work_items(path=config))[_ITEM_ID]


def test_the_refusal_record_names_the_condition_node_and_scheduled_instant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The four minimum fields, plus the hold observation and its expiry."""
    repo, _config_unused = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")

    _admittable, refused = _run_filter(
        repo=repo,
        verdict=_emptied_verdict(reason=TYPED_HOLD_SKIP, holds=(_hold(),)),
        journal=journal,
    )

    assert [outcome.work_item_id for outcome in refused] == [_ITEM_ID]
    records = _refusal_records(journal=journal)
    assert len(records) == 1
    record = records[0]
    assert record["work_item_id"] == _ITEM_ID
    assert record["governing_condition"] == TYPED_HOLD_SKIP
    assert record["admission_required_node"] == "fix"
    assert record["scheduled_reevaluation_at"] == _HOLD_EXPIRY
    assert record["governing_hold_observations"] == [
        {
            "observation_id": "obs-fix",
            "scope": _DOMAIN,
            "hold_key": "codex",
            "candidate_key": None,
            "cause": "quota",
            "expires_at": _HOLD_EXPIRY,
        }
    ]


def test_the_refused_item_stays_ready_with_no_claim_and_no_blocked_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "The item MUST remain ready without a claim or blocked reason."

    Read back off the ledger rather than off the outcome, because the forbidden
    writes are writes that must NOT have happened.
    """
    repo, config = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")

    admittable, refused = _run_filter(
        repo=repo,
        verdict=_emptied_verdict(reason=TYPED_HOLD_SKIP, holds=(_hold(),)),
        journal=journal,
    )

    assert admittable == []
    assert len(refused) == 1
    row = _reread(config=config)
    assert row.status == "ready"
    assert row.blocked_reason is None
    assert row.assignee is None
    assert dispatch_lock_path(repo=repo, work_item_id=_ITEM_ID).exists() is False


def test_an_ephemeral_skip_schedules_the_committed_reprobe_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "And otherwise after `dispatcher.credential_reprobe_interval_seconds`."

    Asserted against the DEFAULT interval's own answer, so a resolver that
    never read the repository's key fails here rather than passing on a
    well-formed instant that is fifteen minutes wrong.
    """
    repo, _config_unused = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")
    # The pass's own clock, patched where the eligibility filter reads it: one
    # fixed evaluation time is this filter's property, not the seam's.
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_admission_eligibility.utc_now_iso",
        lambda: _NOW,
    )

    _admittable, _refused = _run_filter(
        repo=repo, verdict=_emptied_verdict(reason=HEADROOM_SKIP, holds=()), journal=journal
    )

    record = _refusal_records(journal=journal)[0]
    assert record["governing_condition"] == HEADROOM_SKIP
    assert record["scheduled_reevaluation_at"] == _NOW_PLUS_INTERVAL
    assert record["scheduled_reevaluation_at"] != _NOW_PLUS_DEFAULT
    # "It MUST NOT invent a hold identity or expiry."
    assert record["governing_hold_observations"] == []


def test_a_viable_verdict_writes_no_containment_refusal_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the record's fields mean nothing if they are unconditional."""
    repo, config = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")

    admittable, _refused = _run_filter(repo=repo, verdict=_viable_verdict(), journal=journal)

    assert [item.id for item in admittable] == [_ITEM_ID]
    assert _refusal_records(journal=journal) == []
    assert _reread(config=config).status == "ready"


def test_a_configuration_refusal_record_carries_no_wait_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unsupported graph still refuses, and still names no instant.

    Waiting repairs nothing here, so the pre-existing refusal record must stay
    exactly as it was -- additive to every repository whose chains resolve.
    """
    repo, _config_unused = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    journal = JournalFile(path=repo / "journal.jsonl")

    _admittable, refused = _run_filter(
        repo=repo, verdict=_configuration_refusal_verdict(), journal=journal
    )

    assert len(refused) == 1
    record = _refusal_records(journal=journal)[0]
    assert "scheduled_reevaluation_at" not in record
    assert "governing_condition" not in record
    assert "admission_required_node" not in record


def test_the_wait_resolution_is_none_for_a_viable_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam itself: nothing to schedule means nothing resolved."""
    repo, _config_unused = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    resolve = _resolve_availability_wait()

    assert resolve(repo=repo, verdict=_viable_verdict(), now_iso=_NOW) is None


def test_the_wait_resolution_reads_the_holds_the_verdict_carried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ONE evaluation's evidence, carried on the verdict rather than re-read.

    The seam performs no second ledger walk: the holds it grades are the ones
    the verdict was built from, so a record retiring between two reads cannot
    be surfaced by one half and acted on by the other.
    """
    repo, _config_unused = _repo(tmp_path=tmp_path, monkeypatch=monkeypatch)

    resolve = _resolve_availability_wait()

    wait = resolve(
        repo=repo,
        verdict=_emptied_verdict(reason=TYPED_HOLD_SKIP, holds=(_hold(),)),
        now_iso=_NOW,
    )

    assert wait is not None
    assert wait.node == "fix"
    assert wait.reevaluate_at == _HOLD_EXPIRY
    assert [hold.observation_id for hold in wait.holds] == ["obs-fix"]

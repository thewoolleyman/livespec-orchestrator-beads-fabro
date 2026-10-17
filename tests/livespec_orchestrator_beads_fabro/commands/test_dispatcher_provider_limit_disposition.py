"""Performing a provider-limit release: the hold, the record, and the claim.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Provider-limit release and re-dispatch" (`bd-ib-6itdjz`,
Scenario 127) orders four steps "in this order and without a human": record
the hold, journal one `provider-limit-release` record, "release the item's
dispatch claim and return it to `ready`, NOT to `blocked` and with no
`blocked_reason`", and "leave the item to the ordinary admission valve".

THE ADMISSION POLICY IS ASSERTED UNCHANGED, and that is step four made
checkable. "Leave the item to the ordinary admission valve" is a claim about
what the release did NOT do: the needs-human park beside it writes
`admission_policy="manual"` precisely so no further dispatch happens without a
human, so a release that copied that write would return the item to `ready`
and then make it undispatchable -- a state that reads healthy on the status
alone. The item below starts `auto` and must still be `auto` afterwards.

REPLAY IS KEYED ON THE FACTORY, RUN AND FAILING NODE ATTEMPT, which is the
clause's own key, and the three replay cases are not one case repeated. An
interrupted release must COMPLETE -- exactly one record, no second hold, and
no refreshed expiry -- while a replay arriving after a NEWER dispatch has
claimed the item must leave that claim alone. The second is the destructive
direction: the resulting row is byte-identical to a correct first release, so
nothing downstream could tell a live run's stolen claim from a healthy one.

THE THIRD CASE IS THE ONE THE RELEASE ROW ALONE CANNOT ANSWER: a pass whose
ledger transition never landed. The clause requires reconciliation to complete
"any interrupted hold, release, cost-observation, and LEDGER-TRANSITION
writes", and the transition is deliberately fail-soft, so a release row can sit
in the journal beside an item that is still `active` with `fabro` assigned. A
replay reading only its own release row calls that state already-released and
leaves the item holding a WIP slot with no run -- invisible to admission and to
`next`, which is the strand this whole clause exists to retire. So the replay
is settled against the ITEM's own status and assignee, not against the row
alone.

AND THE JOURNAL READING MUST NOT BE BLINDABLE. The newer-dispatch-claim guard
reads the journal for a `dispatch-id` row, and the journal is shared with every
other dispatcher stage, so one truncated line from a crash mid-append is an
ordinary event. A reader that discarded the whole file on one unparseable line
would see no claim row, conclude nothing is owed either way, and hand a running
run's claim back to the queue -- a gauge that passes when blinded, which this
repository treats as worse than the honest violation.

WHY THE LEGACY ARM IS EXERCISED HERE TOO. It writes no typed hold but is still
a release, so the ledger transition and the journal record must happen on both
arms. A disposition that performed only the typed arm would leave every
identity-less adapter's ceiling resting `active` with `fabro` assigned -- the
invisible state the stall disposition's own docstring calls worse than the
wrong bounce it replaced.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_provider_limit_disposition as disposition,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    AcpAvailabilityFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_disposition import (
    dispose_provider_limit_release,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-plrelease"
_RUN = "01M52R2WND7Y"
_NOW = "2026-10-16T19:20:00Z"
_IDENTITY = AcpCandidateIdentity(
    display_name="Claude ACP primary",
    candidate_key="claude-primary",
    availability_key="anthropic-team",
)


@pytest.fixture(autouse=True)
def _fresh_tenant(monkeypatch: pytest.MonkeyPatch) -> object:
    """The hermetic in-memory tenant, flipped on through its one env seam."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="A dispatched slice whose provider ceiling ended the run",
        description="Implement the slice.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green by the check suite.",
    )
    return replace(base, **overrides)


def _release(*, typed: bool = True) -> ProviderLimitRelease:
    matched = (
        AcpAvailabilityFailure(
            cause="quota",
            scope="availability-domain",
            hold_key="anthropic-team",
            availability_key="anthropic-team",
            candidate_key=None,
            source="protocol.message",
        )
        if typed
        else None
    )
    return ProviderLimitRelease(
        factory="hp",
        run_id=_RUN,
        node_attempt="implement",
        matched=matched,
        executed=_IDENTITY,
        legacy_provider=None if typed else "anthropic",
        recovery_source=f"the tree was preserved on refs/heads/needs-human/{_RUN}",
    )


def _outcome(*, release: ProviderLimitRelease | None, status: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=_ITEM_ID,
        status=status,
        stage="provider-limit-release",
        pr_number=None,
        merge_sha=None,
        detail="",
        fabro_run_id=_RUN,
        provider_limit_release=release,
    )


def _journal(*, tmp_path: Path, lines: tuple[str, ...] = ()) -> JournalFile:
    path = tmp_path / "journal.jsonl"
    _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return JournalFile(path=path)


def _records(*, journal: JournalFile) -> list[dict[str, object]]:
    """Every PARSEABLE journal record, skipping a truncated line.

    One case below writes a half-written line on purpose, so a reader that
    raised on it would fail that case for the wrong reason -- in the product's
    name rather than its own.
    """
    records: list[dict[str, object]] = []
    for line in journal.path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def _of_stage(*, journal: JournalFile, stage: str) -> list[dict[str, object]]:
    return [record for record in _records(journal=journal) if record.get("stage") == stage]


def _dispose(*, tmp_path: Path, journal: JournalFile, outcome: DispatchOutcome) -> None:
    dispose_provider_limit_release(
        repo=_repo(tmp_path=tmp_path), item=_item(), outcome=outcome, journal=journal, now_iso=_NOW
    )


def _released_item() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))[_ITEM_ID]


def _release_line() -> str:
    """This release's OWN journal row, as an interrupted pass left it.

    Spelled once, because three replay cases key on it and a second spelling of
    the release key is how two of them would come to describe different
    releases while reading as one case repeated.
    """
    return json.dumps(
        {
            "stage": "provider-limit-release",
            "work_item_id": _ITEM_ID,
            "release_key": f"hp:{_RUN}:implement",
        }
    )


def test_the_release_holds_journals_and_returns_the_item_to_ready(tmp_path: Path) -> None:
    """All four ordered steps of the clause, on the typed arm."""
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    holds = _of_stage(journal=journal, stage="acp-availability-observed")
    assert len(holds) == 1
    assert holds[0]["scope"] == "availability-domain"
    assert holds[0]["hold_key"] == "anthropic-team"
    assert holds[0]["expires_at"] == "2026-10-16T19:35:00Z"
    releases = _of_stage(journal=journal, stage="provider-limit-release")
    assert len(releases) == 1
    assert releases[0]["release_key"] == f"hp:{_RUN}:implement"
    assert releases[0]["failed_candidate_key"] == "claude-primary"
    assert releases[0]["recovery_source"].startswith("the tree was preserved on")
    released = _released_item()
    assert released.status == "ready"
    assert released.assignee is None
    assert released.blocked_reason is None
    # Step four, made checkable: the item is left to the ORDINARY admission
    # valve, so the policy the needs-human park would have set to `manual` is
    # untouched and the drain can re-dispatch with no human valve.
    assert released.admission_policy == "auto"


def test_the_legacy_arm_releases_the_claim_without_a_typed_hold(tmp_path: Path) -> None:
    """No entitlement was measured, so no hold -- but still a release."""
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(typed=False), status="provider-limit-release"),
    )

    assert _of_stage(journal=journal, stage="acp-availability-observed") == []
    releases = _of_stage(journal=journal, stage="provider-limit-release")
    assert len(releases) == 1
    assert releases[0]["legacy_provider"] == "anthropic"
    released = _released_item()
    assert released.status == "ready"
    assert released.assignee is None
    assert released.admission_policy == "auto"


def test_every_other_outcome_is_left_entirely_alone(tmp_path: Path) -> None:
    """The control: a no-op for every terminal that is not this release.

    Without it, a disposition that fired on every outcome would satisfy every
    assertion above while releasing green runs and ordinary failures too.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)

    _dispose(tmp_path=tmp_path, journal=journal, outcome=_outcome(release=None, status="blocked"))

    assert _records(journal=journal) == []
    assert _released_item().status == "active"
    assert _released_item().assignee == "fabro"


def test_a_replay_of_an_interrupted_release_completes_it_exactly_once(
    tmp_path: Path,
) -> None:
    """Keyed on factory, run and failing node attempt: one record, one hold.

    The second call is the reconciliation replay. It must leave exactly one
    `provider-limit-release` record and must not refresh the hold's expiry --
    which is asserted by re-disposing under a LATER clock, the one reading that
    could push the bound forward if the observation id were not stable.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)
    outcome = _outcome(release=_release(), status="provider-limit-release")

    _dispose(tmp_path=tmp_path, journal=journal, outcome=outcome)
    dispose_provider_limit_release(
        repo=_repo(tmp_path=tmp_path, name="replay"),
        # As reconciliation finds it: already released by the interrupted pass.
        item=_item(status="ready", assignee=None),
        outcome=outcome,
        now_iso="2026-10-16T19:29:00Z",
        journal=journal,
    )

    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    holds = _of_stage(journal=journal, stage="acp-availability-observed")
    assert len(holds) == 1
    assert holds[0]["expires_at"] == "2026-10-16T19:35:00Z"
    # The replay SAYS it declined, rather than doing nothing silently: a replay
    # that did nothing and said nothing is indistinguishable from one that
    # never ran.
    held = _of_stage(journal=journal, stage="provider-limit-release-held")
    assert len(held) == 1
    assert held[0]["reason"] == "already-released"
    assert held[0]["release_key"] == f"hp:{_RUN}:implement"


def test_a_replay_after_a_newer_dispatch_claimed_the_item_leaves_that_claim(
    tmp_path: Path,
) -> None:
    """The destructive direction: a live run's claim is never handed back.

    A `dispatch-id` row AFTER this release's own record says a later dispatch
    has since claimed the item, so the claim now standing is not the one this
    release dropped. Performing the release again would return a live run's
    claim to the queue, and the row it wrote would be byte-identical to a
    correct first release.
    """
    append_work_item(path=_config(), item=_item(status="active", assignee="fabro"))
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            _release_line(),
            json.dumps({"stage": "dispatch-id", "work_item_id": _ITEM_ID}),
        ),
    )

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _of_stage(journal=journal, stage="acp-availability-observed") == []
    held = _of_stage(journal=journal, stage="provider-limit-release-held")
    assert len(held) == 1
    assert held[0]["reason"] == "newer-dispatch-claim"
    # The newer dispatch's claim is intact.
    claimed = _released_item()
    assert claimed.status == "active"
    assert claimed.assignee == "fabro"


def test_a_replay_completes_a_release_whose_ledger_transition_never_landed(
    tmp_path: Path,
) -> None:
    """A release row beside a still-claimed item is an UNFINISHED step three.

    The write order is hold, then release record, then ledger transition, and
    that transition is fail-soft by design: `_release_claim` journals
    `provider-limit-release-error` and leaves the item `active` with `fabro`
    assigned. The journal fixture below is exactly that state. A replay reading
    only its own release row would report `already-released`, say nothing is
    owed, and leave the item stranded -- so the reading is settled against the
    item, and the replay finishes the transition.

    It also finishes the interrupted HOLD, which is idempotent through the
    shared ledger's first-write-wins dedupe, while journaling NO second release
    record: that append is the one write a replay cannot repeat.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            _release_line(),
            json.dumps(
                {
                    "stage": "provider-limit-release-error",
                    "work_item_id": _ITEM_ID,
                    "release_key": f"hp:{_RUN}:implement",
                    "reason": "BeadsCommandError",
                }
            ),
        ),
    )

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _of_stage(journal=journal, stage="provider-limit-release-held") == []
    assert len(_of_stage(journal=journal, stage="acp-availability-observed")) == 1
    released = _released_item()
    assert released.status == "ready"
    assert released.assignee is None
    assert released.admission_policy == "auto"


def test_one_malformed_line_does_not_blind_the_newer_dispatch_claim_guard(
    tmp_path: Path,
) -> None:
    """A truncated line must not make the guard hand back a live claim.

    The newer-claim guard is a journal reading, and a reader that discarded the
    WHOLE journal on one unparseable line would find neither this release's own
    row nor the `dispatch-id` row after it, conclude nothing is owed, and
    perform the release again -- returning a running run's claim to the queue
    under a row byte-identical to a correct first release. The malformed line
    here belongs to an unrelated stage, which is what a crash mid-append
    actually leaves: only that line may be dropped.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(
        tmp_path=tmp_path,
        lines=(
            _release_line(),
            '{"stage": "janitor", "work_it',
            json.dumps({"stage": "dispatch-id", "work_item_id": _ITEM_ID}),
        ),
    )

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    held = _of_stage(journal=journal, stage="provider-limit-release-held")
    assert len(held) == 1
    assert held[0]["reason"] == "newer-dispatch-claim"
    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _of_stage(journal=journal, stage="acp-availability-observed") == []
    claimed = _released_item()
    assert claimed.status == "active"
    assert claimed.assignee == "fabro"


def test_an_unreadable_hold_occurrence_is_journaled_rather_than_silently_dropped(
    tmp_path: Path,
) -> None:
    """A hold the writer refuses still releases the item, and says why.

    The release is what unblocks the queue, so it must not be held hostage to
    the audit copy. But the refusal is journaled rather than swallowed,
    because a hold that was never minted is exactly what an operator needs to
    know when the next dispatch spends the same exhausted allowance.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)

    dispose_provider_limit_release(
        repo=_repo(tmp_path=tmp_path),
        item=_item(),
        outcome=_outcome(release=_release(), status="provider-limit-release"),
        journal=journal,
        now_iso="last Tuesday",
    )

    assert _of_stage(journal=journal, stage="acp-availability-observed") == []
    refusals = _of_stage(journal=journal, stage="acp-availability-observed-refused")
    assert len(refusals) == 1
    assert "last Tuesday" in str(refusals[0]["reason"])
    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _released_item().status == "ready"


def test_a_failed_ledger_write_is_journaled_rather_than_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A release whose ledger transition fails leaves an account behind.

    FAIL-SOFT, and the direction matters. The terminal is already final, so a
    disposition that raised would strand the item AND lose the record of why.
    The item stays `active` -- which an operator can see and move by hand --
    and the journal carries the error row naming the release that could not
    complete, so the stranding is attributable instead of silent.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)

    def _refuse(**_: object) -> None:
        raise BeadsCommandError(command="bd update", exit_code=1, stderr="refused")

    monkeypatch.setattr(disposition, "update_work_item_status", _refuse)

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    errors = _of_stage(journal=journal, stage="provider-limit-release-error")
    assert len(errors) == 1
    assert errors[0]["reason"] == "BeadsCommandError"
    assert errors[0]["release_key"] == f"hp:{_RUN}:implement"
    # The hold and the release record were taken BEFORE the ledger write, so
    # they survive the failure: the evidence outlives the transition.
    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _released_item().status == "active"


def test_an_unreadable_journal_still_performs_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal that cannot be READ holds nothing, so the release proceeds.

    Without an "after" to read, the newer-claim question has not been answered
    either way -- and the dispatch most likely to have left the item stranded
    is exactly the one whose record went missing. So the fail-soft direction
    here is to release rather than to decline.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path)
    original = Path.read_text

    def _unreadable(self: Path, *args: object, **kwargs: object) -> str:
        if self == journal.path:
            raise OSError("journal unreadable")
        return original(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _unreadable)

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    monkeypatch.undo()
    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _of_stage(journal=journal, stage="provider-limit-release-held") == []
    assert _released_item().status == "ready"


def test_one_malformed_journal_line_does_not_stop_the_release(tmp_path: Path) -> None:
    """A crash mid-append leaves a truncated line; the release still completes.

    The journal is shared with every other dispatcher stage, so one
    unparseable line must not make this reading raise -- which would strand the
    item over a record belonging to something else entirely.
    """
    append_work_item(path=_config(), item=_item())
    journal = _journal(tmp_path=tmp_path, lines=('{"stage": "dispatch-id", "work_it',))

    _dispose(
        tmp_path=tmp_path,
        journal=journal,
        outcome=_outcome(release=_release(), status="provider-limit-release"),
    )

    assert len(_of_stage(journal=journal, stage="provider-limit-release")) == 1
    assert _released_item().status == "ready"

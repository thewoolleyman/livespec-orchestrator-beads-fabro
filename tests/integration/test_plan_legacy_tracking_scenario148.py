"""Scenario 148 — legacy pointers stay readable and diagnosis never mutates.

`contracts.md` section "Required result, budget and progress epoch": "Legacy
three-key pointers MUST remain readable, report `plan-progress-tracking:
missing`, and acquire the new shape on their next sanctioned write; legacy reads
alone MUST NOT invent budgets or mutate the ledger."

READABLE AND MUTATING ARE SEPARATE CLAIMS, so each is asserted on its own
instrument. "Readable" is read off the parse and the resume directive; "does not
mutate" is read off a FULL BEFORE/AFTER SNAPSHOT of the epic's record and
comments, not off a return value — a reader that invented a budget and stored it
would return a perfectly correct finding either way, and the only place that
shows up is the ledger.

THE DIAGNOSIS DEFECT THIS MODULE CLOSES, recorded on `bd-ib-zi5ygh` from an
executed probe of the terminal run's handler: with no `next_action` at all it
raised `AttributeError: NoneType has no attribute required_result`, and with a
legacy three-key pointer it raised `AttributeError: ResultReferenceRefusal has
no attribute identity`. Both are states a real plan sits in — one before its
first pointer, one before its migration — so the public diagnosis crashed on the
two inputs it most needed to answer for. It must instead return a STRUCTURED
read-only finding, and the cases below assert the payload rather than merely
that no exception escaped: a handler that swallowed the error and returned a
plausible shell would pass an exception-free assertion while reporting nothing.

A `verified_proof` reference is used for the "unmet prior obligation" case
rather than an `item_status` one, because it is unobservable in a hermetic
tenant without a forge — which is the state that must PRESERVE the obligation
rather than discharge it.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain import (
    ChainHead,
    read_chain_head,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    LEGACY_TRACKING,
    NEXT_ACTION_METADATA_KEY,
    NextAction,
    parse_next_action,
    plan_record_metadata,
    read_next_action,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_PROJECT_NAME = "repo"
_EPIC_ID = "bd-ib-relaylegacy"
_TARGET_ID = "bd-ib-legacytarget"
_TRACKING_MISSING = "plan-progress-tracking: missing"
_DIAGNOSIS = f"diagnose-plan-progress:{_EPIC_ID}"
_DEADLINE = "2099-01-01T00:00:00Z"
_MODULE = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_drive_plan_progress_diagnosis.py"
)


@pytest.fixture(autouse=True)
def _hermetic_backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _fake(*, config: StoreConfig) -> FakeBeadsClient:
    client = make_beads_client(config=config)
    assert isinstance(client, FakeBeadsClient)
    return client


def _legacy_pointer() -> dict[str, object]:
    """The three-key shape that predates the tracking fields entirely."""
    return {"kind": "impl", "ref": _TARGET_ID, "text": "Keep going."}


def _seed(*, tmp_path: Path, pointer: dict[str, object] | None) -> StoreConfig:
    repo = tmp_path / _PROJECT_NAME
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    config = store_config(repo=repo)
    fake = _fake(config=config)
    metadata: dict[str, object] = {"rank": "a0"}
    if pointer is not None:
        metadata[NEXT_ACTION_METADATA_KEY] = pointer
    for issue_id, status in ((_EPIC_ID, "active"), (_TARGET_ID, "ready")):
        _ = fake.create_issue(
            draft=IssueDraft(
                issue_id=issue_id,
                issue_type="epic" if issue_id == _EPIC_ID else "feature",
                title=issue_id,
                description="Definition of Done\n\n- A thing holds.",
                assignee=None,
                created_at="2026-10-13T08:00:00Z",
                metadata=metadata if issue_id == _EPIC_ID else {"rank": "a0"},
            )
        )
        fake.update_issue(issue_id=issue_id, status=status)
    return config


def _snapshot(*, config: StoreConfig) -> tuple[Any, Any]:
    """The whole observable ledger state of the epic, record and comments."""
    fake = _fake(config=config)
    return (
        fake.show_issue(issue_id=_EPIC_ID),
        fake.list_comments(issue_id=_EPIC_ID),
    )


def _diagnose(*, config: StoreConfig, repo: Path) -> dict[str, Any]:
    """Run the public diagnosis action through the real `drive` router."""
    _ = config
    assert _MODULE.is_file(), f"{_MODULE} does not exist"
    drive = importlib.import_module("livespec_orchestrator_beads_fabro.commands.drive")
    return drive.run_action(repo=repo, action_id=_DIAGNOSIS)


def _findings_text(*, findings: tuple[str, ...]) -> str:
    return "\n".join(findings)


def test_a_legacy_three_key_pointer_still_parses_as_a_readable_pointer() -> None:
    """Readability is the FIRST requirement and it is structural.

    Both tracking fields read as the legacy sentinel rather than as `None`,
    because explicit null is what a `human` pointer carries and the two must
    stay distinguishable: one has no obligation, the other never had the fields.
    """
    action = parse_next_action(value=_legacy_pointer())

    assert action is not None
    assert (action.kind, action.ref) == ("impl", _TARGET_ID)
    assert action.required_result is LEGACY_TRACKING
    assert action.budget is LEGACY_TRACKING


def test_a_legacy_pointer_is_readable_through_the_store(tmp_path: Path) -> None:
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    action = read_next_action(config=config, epic_id=_EPIC_ID)

    assert action is not None
    assert action.required_result is LEGACY_TRACKING


def test_a_legacy_resume_reports_missing_tracking(tmp_path: Path) -> None:
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert _TRACKING_MISSING in _findings_text(findings=directive.findings)


def test_a_legacy_read_invents_no_budget_and_mutates_no_ledger(
    tmp_path: Path,
) -> None:
    """ "legacy reads alone MUST NOT invent budgets or mutate the ledger".

    The whole record and every comment are compared before and after, because a
    reader that stored an invented budget would return the correct finding
    regardless and the ledger is the only place it shows.
    """
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())
    before = _snapshot(config=config)

    _ = read_next_action(config=config, epic_id=_EPIC_ID)
    _ = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert _snapshot(config=config) == before
    assert isinstance(read_chain_head(config=config, epic_id=_EPIC_ID), ChainFinding)


def test_the_missing_tracking_finding_names_the_sanctioned_migration(
    tmp_path: Path,
) -> None:
    """A finding with no remedy leaves the operator nowhere to go.

    The clause says the pointer acquires the new shape on its "next sanctioned
    write", and the migration is the sanctioned write that supplies the fields
    for an existing plan, so the finding has to name it.
    """
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    assert "migrate-plan-records" in _findings_text(findings=directive.findings)


def test_an_absent_chain_keeps_the_migration_remedy_rather_than_the_pointer_write(
    tmp_path: Path,
) -> None:
    """The half of the distinction that must NOT move (`bd-ib-paevjd`).

    A chain that reads cleanly while tracking no obligation now names an
    executable-kind pointer write as its remedy. This epic has no chain at all,
    so the migration that creates its genesis token is still the write it
    needs, and naming the pointer write here would point an unmigrated plan at
    a writer that refuses it — `set_next_action` has nowhere to commit a
    transition. Asserted here, with both halves in one place, because the
    expensive failure is a repair that collapses the two arms onto whichever
    remedy was written last.
    """
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    directive = resume_directive(config=config, epic_id=_EPIC_ID, unattended=True)

    text = _findings_text(findings=directive.findings)
    assert _TRACKING_MISSING in text
    assert "migrate-plan-records" in text
    assert "next_action write carrying required_result and budget" not in text


def test_the_next_sanctioned_write_requires_both_tracking_fields(
    tmp_path: Path,
) -> None:
    """ "an impl or spec-op pointer requires valid required_result and budget".

    The legacy shape is REFUSED on a write, which is what makes the migration
    necessary rather than optional — a write that silently kept three keys
    would leave the pointer legacy forever.
    """
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    refusal = set_next_action(
        config=config,
        epic_id=_EPIC_ID,
        action=NextAction(kind="impl", ref=_TARGET_ID, text="Keep going."),
        session="relay-session",
        now="2026-10-13T09:00:00Z",
    )

    assert refusal is not None
    assert "required_result and budget" in refusal.detail


def test_a_sanctioned_write_supplying_both_fields_lands_the_new_shape(
    tmp_path: Path,
) -> None:
    """The POSITIVE half: without it, "the legacy shape is refused" is equally
    consistent with a writer that refuses every write."""
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    refusal = set_next_action(
        config=config,
        epic_id=_EPIC_ID,
        action=NextAction(
            kind="impl",
            ref=_TARGET_ID,
            text="Keep going.",
            required_result={
                "repo": _PROJECT_NAME,
                "item_status": {"item_id": _TARGET_ID, "status": "done"},
            },
            budget={"deadline": _DEADLINE, "max_handoffs": 5},
        ),
        session="relay-session",
        now="2026-10-13T09:00:00Z",
    )

    assert refusal is None, refusal
    pointer = plan_record_metadata(record=_fake(config=config).show_issue(issue_id=_EPIC_ID))[
        NEXT_ACTION_METADATA_KEY
    ]
    assert isinstance(pointer, dict)
    assert pointer["budget"] == {"deadline": _DEADLINE, "max_handoffs": 5}


def test_a_human_pointer_requires_explicit_null_tracking_fields(
    tmp_path: Path,
) -> None:
    """ "human or none pointers require explicit null tracking fields"."""
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    refusal = set_next_action(
        config=config,
        epic_id=_EPIC_ID,
        action=NextAction(
            kind="human",
            ref="Decide the routing.",
            text="Decide the routing.",
            required_result={
                "repo": _PROJECT_NAME,
                "item_status": {"item_id": "x", "status": "done"},
            },
            budget={"deadline": _DEADLINE, "max_handoffs": 5},
        ),
        session="relay-session",
        now="2026-10-13T09:00:00Z",
    )

    assert refusal is not None
    assert "null required_result and budget" in refusal.detail


def test_the_diagnosis_reports_a_structured_finding_for_a_missing_pointer(
    tmp_path: Path,
) -> None:
    """The first measured crash: `NoneType has no attribute required_result`.

    An epic before its first pointer is an ordinary state, and the payload is
    asserted rather than merely the absence of an exception — a handler that
    caught the error and returned a shell would pass an exception-free check
    while reporting nothing.
    """
    config = _seed(tmp_path=tmp_path, pointer=None)

    payload = _diagnose(config=config, repo=tmp_path / _PROJECT_NAME)

    assert payload["status"] == "green"
    assert payload["action_id"] == _DIAGNOSIS
    diagnosis = payload["diagnosis"]
    assert diagnosis["ledger_mutation"] is False
    assert diagnosis["target_fulfillment"] == "not-asserted"
    assert any(_TRACKING_MISSING in one for one in diagnosis["findings"])


def test_the_diagnosis_reports_a_structured_finding_for_a_legacy_pointer(
    tmp_path: Path,
) -> None:
    """The second measured crash: `ResultReferenceRefusal has no attribute
    identity`.

    A legacy pointer's `required_result` is the sentinel, not a reference, so a
    handler that parsed it and reached for an identity dereferenced the refusal
    value the parse returns.
    """
    config = _seed(tmp_path=tmp_path, pointer=_legacy_pointer())

    payload = _diagnose(config=config, repo=tmp_path / _PROJECT_NAME)

    assert payload["status"] == "green"
    diagnosis = payload["diagnosis"]
    assert any(_TRACKING_MISSING in one for one in diagnosis["findings"])
    assert diagnosis["ledger_mutation"] is False


@pytest.mark.parametrize("pointer_kind", ["missing", "legacy"])
def test_the_diagnosis_writes_nothing_to_the_ledger(
    tmp_path: Path,
    pointer_kind: str,
) -> None:
    """ "a structured read-only finding, with zero writes".

    Both crash inputs are run, because the repair must not trade a crash for a
    write — and a diagnosis that repaired what it found would look identical at
    the payload.
    """
    config = _seed(
        tmp_path=tmp_path,
        pointer=_legacy_pointer() if pointer_kind == "legacy" else None,
    )
    before = _snapshot(config=config)

    _ = _diagnose(config=config, repo=tmp_path / _PROJECT_NAME)

    assert _snapshot(config=config) == before


def test_an_unmet_prior_obligation_survives_a_change_to_a_human_pointer(
    tmp_path: Path,
) -> None:
    """ "any unmet prior obligation remains in history".

    The obligation is established, then the pointer is changed to `human` with
    explicit null tracking. The POINTER goes null and the AUTHORITY keeps the
    obligation — reading the authority back is the only way to tell that from
    an obligation discharged by pointing elsewhere.
    """
    config = _seed(tmp_path=tmp_path, pointer=None)
    fake = _fake(config=config)
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import (
        create_genesis_token,
    )

    assert isinstance(create_genesis_token(config=config, epic_id=_EPIC_ID), str)
    unobservable_result: dict[str, object] = {
        "repo": _PROJECT_NAME,
        "verified_proof": {
            "subject_id": _TARGET_ID,
            "build": "v0.0.0",
            "assertions": ["A thing holds."],
        },
    }
    assert (
        set_next_action(
            config=config,
            epic_id=_EPIC_ID,
            action=NextAction(
                kind="impl",
                ref=_TARGET_ID,
                text="Keep going.",
                required_result=unobservable_result,
                budget={"deadline": _DEADLINE, "max_handoffs": 5},
            ),
            session="relay-session",
            now="2026-10-13T09:00:00Z",
        )
        is None
    )
    established = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(established, ChainHead)
    assert established.authority.original_deadline == _DEADLINE

    assert (
        set_next_action(
            config=config,
            epic_id=_EPIC_ID,
            action=NextAction(
                kind="human",
                ref="Decide the routing.",
                text="Decide the routing.",
                required_result=None,
                budget=None,
            ),
            session="relay-session",
            now="2026-10-13T10:00:00Z",
        )
        is None
    )

    after = read_chain_head(config=config, epic_id=_EPIC_ID)
    assert isinstance(after, ChainHead)
    assert after.authority.original_deadline == _DEADLINE
    assert after.authority.required_result == unobservable_result
    pointer = plan_record_metadata(record=fake.show_issue(issue_id=_EPIC_ID))[
        NEXT_ACTION_METADATA_KEY
    ]
    assert isinstance(pointer, dict)
    assert pointer["required_result"] is None
    assert pointer["budget"] is None

"""Scenario 301 — a verified delegated press satisfies a human valve, recorded as delegated.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 301 — A verified delegated press satisfies a human valve and is
recorded as delegated`. The clause it realizes is the delegated-valve-authority
paragraph of the journal invoker attribution contract in
`SPECIFICATION/contracts.md`, cited at the FILE level so a heading rename cannot
rot it.

EVERY PRESS GOES THROUGH `drive.run_action`, the router the CLI calls, so each
case shows that `drive` consults the verifier rather than that the verifier
computes a verdict in isolation.

WHY EVERY REFUSAL READS THE TENANT AND THE JOURNAL. A refusal is a claim about
what did NOT happen, and a build that refused AFTER writing returns the same
payload. So each refused press asserts the item still rests where it was, the
ledger carries no comment and the journal holds no line.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import fake_singleton, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
_ITEM = "bd-ib-parked"
_ANSWER = "Release it; the merge wait only ran out of poll budget."
_REF = "R493"
_GRANTOR = "human:thewoolleyman"
_RECORD = "livespec-dev-tooling-6tgd2z plan-scope-event 2026-11-01T22:36:24Z"
_DELEGATE_NAME = "legacy-coordinator-agent"
_DELEGATE = InvokerIdentity(invoker=f"delegate:{_DELEGATE_NAME}", invoker_source="flag")
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
# The labels seeding `_parked()` writes. A refused press must leave exactly
# these, so a merge hold or a policy label written before a refusal shows here.
_SEEDED_LABELS = ("origin:freeform", "blocked-reason:needs-human")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fresh in-memory tenant per case, with the fake backend selected."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario301_a_delegate_invoker_without_a_delegation_is_refused_before_any_write(
    tmp_path: Path,
) -> None:
    """A `delegate:` invoker that names no delegation is refused, writing nothing."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked())

    refused = run_action(
        repo=repo,
        action_id=f"resolve-blocked:{_ITEM}:ready",
        answer=_ANSWER,
        identity=_DELEGATE,
    )

    assert refused["status"] == "failed"
    assert refused["domain_error"] == "delegation-incomplete"
    assert _DELEGATE.invoker in str(refused["summary"])
    assert _wrote_nothing(repo=repo)


def test_scenario301_a_verified_delegated_answer_is_admitted_and_recorded_as_delegated(
    tmp_path: Path,
) -> None:
    """Given a committed delegation R493 for the delegate, and an item parked at human,
    When the delegate presses resolve-blocked with an answer under --delegation R493,
    Then the answer lands naming the delegation and its grantor,
    And every journal record carries the delegate invoker and a delegation object,
    And the item gains a livespec-delegated-valve-press comment, with no human: identity.
    """
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked())
    action = f"resolve-blocked:{_ITEM}:ready"

    admitted = run_action(
        repo=repo, action_id=action, answer=_ANSWER, identity=_DELEGATE, delegation=_REF
    )

    assert admitted["status"] == "green"
    assert admitted["target_status"] == "ready"
    assert admitted["delegation"] == {"ref": _REF, "grantor": _GRANTOR, "record": _RECORD}
    texts = [str(record["text"]) for record in _comments()]
    assert len(texts) == 2
    answer_head = texts[0].split("\n", 1)[0]
    assert answer_head.startswith(
        f"livespec-human-answer ({_DELEGATE.invoker} via flag under maintainer delegation "
        f"{_REF} granted by {_GRANTOR}, "
    )
    assert answer_head.endswith(f", {action}):")
    assert texts[1].startswith("livespec-delegated-valve-press")
    for needle in (action, _DELEGATE.invoker, _REF, _GRANTOR, _RECORD):
        assert needle in texts[1]
    lines = _journal_lines(repo=repo)
    assert lines
    for line in lines:
        assert line["invoker"] == _DELEGATE.invoker
        assert line["delegation"] == {"ref": _REF, "grantor": _GRANTOR, "record": _RECORD}
    assert all(not text.startswith("human:") and "(human:" not in text for text in texts)


@pytest.mark.parametrize(
    ("identity", "delegation", "error"),
    [
        (_DELEGATE, "R999", "delegation-unverified"),
        (
            InvokerIdentity(invoker="delegate:some-other-seat", invoker_source="flag"),
            _REF,
            "delegation-unverified",
        ),
        (
            InvokerIdentity(invoker="session:seat", invoker_source="flag"),
            _REF,
            "delegation-incomplete",
        ),
    ],
)
def test_scenario301_a_delegation_that_cannot_be_verified_is_refused_before_any_write(
    tmp_path: Path, identity: InvokerIdentity, delegation: str, error: str
) -> None:
    """An unknown ref, a ref granted to another delegate, or a ref without the role: refused."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked())

    refused = run_action(
        repo=repo,
        action_id=f"resolve-blocked:{_ITEM}:ready",
        answer=_ANSWER,
        identity=identity,
        delegation=delegation,
    )

    assert refused["status"] == "failed"
    assert refused["domain_error"] == error
    assert identity.invoker in str(refused["summary"])
    assert delegation in str(refused["summary"])
    assert _wrote_nothing(repo=repo)


def test_scenario301_an_unreadable_delegation_setting_verifies_no_press(tmp_path: Path) -> None:
    """An entry whose grantor is not a named human makes the setting verify nothing."""
    repo = _repo(tmp_path=tmp_path, grantor="session:coordinator")
    append_work_item(path=_config(), item=_parked())

    refused = run_action(
        repo=repo,
        action_id=f"resolve-blocked:{_ITEM}:ready",
        answer=_ANSWER,
        identity=_DELEGATE,
        delegation=_REF,
    )

    assert refused["status"] == "failed"
    assert refused["domain_error"] == "delegation-unverified"
    assert _wrote_nothing(repo=repo)


@pytest.mark.parametrize(
    "action",
    [
        f"set-merge-hold:{_ITEM}:on",
        f"set-factory-safety:{_ITEM}:needs-host-secrets",
        f"set-admission:{_ITEM}:auto",
        f"impl:{_ITEM}",
    ],
)
def test_scenario301_a_delegated_press_of_a_non_delegable_valve_is_refused(
    tmp_path: Path, action: str
) -> None:
    """A verified delegation never reaches a verb off the delegable valve allowlist."""
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked())

    refused = run_action(repo=repo, action_id=action, identity=_DELEGATE, delegation=_REF)

    assert refused["status"] == "failed"
    assert refused["domain_error"] == "delegation-not-permitted"
    assert action in str(refused["summary"])
    assert _wrote_nothing(repo=repo)


def _wrote_nothing(*, repo: Path) -> bool:
    record = fake_singleton().show_issue(issue_id=_ITEM)
    labels = sorted(record.get("labels") or [])
    return (
        record["status"] == "blocked"
        and _comments() == []
        and labels == sorted(_SEEDED_LABELS)
        and not (repo / _JOURNAL).exists()
    )


def _comments() -> list[dict[str, object]]:
    return list(fake_singleton().list_comments(issue_id=_ITEM))


def _journal_lines(*, repo: Path) -> list[dict[str, object]]:
    text = (repo / _JOURNAL).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _parked() -> WorkItem:
    """A work-item resting at `blocked` with `blocked_reason: needs-human`."""
    return WorkItem(
        id=_ITEM,
        type="task",
        status="blocked",
        title="Parked on a question",
        description="It could not be finished without a decision.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-02T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


def _repo(*, tmp_path: Path, grantor: str = _GRANTOR) -> Path:
    """A governed clone carrying one committed valve delegation."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    block: dict[str, object] = {
        "connection": {"prefix": _PREFIX},
        "dispatcher": {
            "valve_delegations": [
                {
                    "ref": _REF,
                    "delegate": _DELEGATE_NAME,
                    "grantor": grantor,
                    "record": _RECORD,
                }
            ]
        },
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps({_PLUGIN_BLOCK: block}), encoding="utf-8")
    return repo


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )

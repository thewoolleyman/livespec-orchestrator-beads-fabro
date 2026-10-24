"""Integration-tier acceptance for Scenario 124's marked answer comment.

Binds `SPECIFICATION/scenarios.md` "Scenario 124 — The human answer lands as a
marked ledger comment before the transition, and a poisoned answer is refused"
and the v093-native answer route of `SPECIFICATION/contracts.md` it realizes.

Both cases drive `drive.run_action` — the operator's own entry point — over the
REAL store/client seam against the in-memory `FakeBeadsClient`, and read the
comment back through `read_work_item_comments`, which is the `bd comments <id>
--json` seam. Reading it back through `bd show` would report every successful
append as lost, because that surface carries only `comment_count`.

THE ORDERING IS OBSERVED RATHER THAN INFERRED. "The comment is written before
the item's status transition" is a claim about what was already true at a moment
INSIDE the valve, and the end state is identical whichever order the two writes
took — so the status write is wrapped and asked what the ledger held when it was
entered, then delegated to the production writer. Asserting the end state alone
would pass for a build that transitioned first, which is the exact miss the
route exists to close: a `ready` item is selectable by `next` the instant the
status write returns, so a re-dispatch could pick it up against a brief that
still lacked the answer.

THE MARKER LINE IS ASSERTED FIELD BY FIELD, not by containment of the marker.
A body that merely MENTIONED the marker would satisfy an `in` check while
naming none of the four things the clause requires of it — the invoker, how that
invoker was resolved, the instant the answer was written, and the valve action
id under which it was given — and the action id is the only place the
disposition an answer carried survives into the ledger at all.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _drive_policy_valves
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_answer import (
    ANSWER_COMMENT_MARKER,
    answering_action_id,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_INVOKER = "human:cwoolley"
_INVOKER_SOURCE = "flag"
# Two lines, because "the answer follows the marker line verbatim" is a claim
# about the WHOLE answer: a reader that kept only the first line would satisfy a
# single-line fixture.
_ANSWER = "Take option B: the guard stays fail-closed.\nRe-dispatch when it lands."
# The MiniJinja expression opener, built rather than written literally: this
# repository keeps the literal pair out of prose that discusses it, because a
# ledger comment carrying one can never be edited or deleted.
_EXPRESSION_OPENER = "{" + "{"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
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


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_BLOCK: {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd-ib",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _parked(*, item_id: str) -> None:
    append_work_item(
        path=_config(),
        item=replace(
            WorkItem(
                id=item_id,
                type="task",
                status="blocked",
                title=f"{item_id} parked on a question",
                description="d",
                origin="freeform",
                gap_id=None,
                rank="a1",
                assignee=None,
                depends_on=(),
                captured_at="2026-10-22T00:00:00Z",
                resolution=None,
                reason=None,
                audit=None,
                superseded_by=None,
            ),
            blocked_reason="needs-human",
        ),
    )


def _press(*, repo: Path, item_id: str, answer: str) -> dict[str, object]:
    return run_action(
        repo=repo,
        action_id=f"resolve-blocked:{item_id}:ready",
        identity=InvokerIdentity(invoker=_INVOKER, invoker_source=_INVOKER_SOURCE),
        answer=answer,
    )


def _utc_second() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _clean_answer(*, tmp_path: Path, item_id: str) -> tuple[dict[str, object], str]:
    """Apply one clean answer and return its result plus the persisted comment text."""
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id=item_id)
    result = _press(repo=repo, item_id=item_id, answer=_ANSWER)
    [comment] = read_work_item_comments(path=_config(), work_item_id=item_id)
    return result, comment.text


def test_scenario124_a_clean_answer_transitions_the_item_to_ready(tmp_path: Path) -> None:
    result, _ = _clean_answer(tmp_path=tmp_path, item_id="bd-ib-s124-ready")

    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    assert _fake().show_issue(issue_id="bd-ib-s124-ready")["status"] == "ready"


def test_scenario124_a_clean_answer_comment_opens_with_the_marker(tmp_path: Path) -> None:
    _, comment = _clean_answer(tmp_path=tmp_path, item_id="bd-ib-s124-marker")

    header = comment.split("\n", 1)[0]
    assert header.startswith(f"{ANSWER_COMMENT_MARKER} (")
    assert header.endswith("):")


def test_scenario124_the_marker_names_the_invoker_and_source(tmp_path: Path) -> None:
    _, comment = _clean_answer(tmp_path=tmp_path, item_id="bd-ib-s124-identity")

    header = comment.split("\n", 1)[0]
    assert f"{_INVOKER} via {_INVOKER_SOURCE}" in header


def test_scenario124_the_marker_names_the_answering_action(tmp_path: Path) -> None:
    _, comment = _clean_answer(tmp_path=tmp_path, item_id="bd-ib-s124-action")

    assert answering_action_id(text=comment) == "resolve-blocked:bd-ib-s124-action:ready"


def test_scenario124_the_marker_carries_the_write_instant(tmp_path: Path) -> None:
    before = _utc_second()
    _, comment = _clean_answer(tmp_path=tmp_path, item_id="bd-ib-s124-instant")
    after = _utc_second()

    header = comment.split("\n", 1)[0]
    instant = header.rstrip("):").rsplit(", ", 2)[-2]
    assert (
        before
        <= datetime.strptime(instant, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        <= after
    )


def test_scenario124_the_answer_follows_its_marker_verbatim(tmp_path: Path) -> None:
    _, comment = _clean_answer(tmp_path=tmp_path, item_id="bd-ib-s124-verbatim")

    _, _, body = comment.partition("\n")
    assert body == _ANSWER


def test_scenario124_the_marked_comment_lands_before_the_status_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One clean answer: the marker's four fields, the verbatim body, the order.

    `observed` is what the LEDGER held at the moment the production status
    writer was entered. The wrapper delegates, so the transition itself is
    production code and the end state is the real one.
    """
    item_id = "bd-ib-s124-clean"
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id=item_id)
    production_writer = _drive_policy_valves.write_blocked_state_and_reconcile
    observed: list[tuple[str, ...]] = []

    def _observing_writer(
        *, path: StoreConfig, item_id: str, status: str, blocked_reason: str | None
    ) -> None:
        observed.append(
            tuple(
                comment.text for comment in read_work_item_comments(path=path, work_item_id=item_id)
            )
        )
        production_writer(path=path, item_id=item_id, status=status, blocked_reason=blocked_reason)

    monkeypatch.setattr(
        _drive_policy_valves, "write_blocked_state_and_reconcile", _observing_writer
    )

    result = _press(repo=repo, item_id=item_id, answer=_ANSWER)

    assert result["status"] == "green"
    [comment] = read_work_item_comments(path=_config(), work_item_id=item_id)
    # The ledger already carried that same comment when the transition began.
    assert observed == [(comment.text,)]
    assert _fake().show_issue(issue_id=item_id)["status"] == "ready"


def test_scenario124_a_poisoned_answer_is_refused_with_nothing_written(
    tmp_path: Path,
) -> None:
    """A template opener would poison every FUTURE goal render for this item.

    Its control is the clean press in the sibling case above: a refusal
    asserted alone is equally consistent with a preflight that refuses every
    answer, which would make the route unreachable. Here the two facts that
    make a refusal FREE are what is asserted — the item is still parked and the
    ledger is still empty, so the operator rewords and re-runs the identical
    action.
    """
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id="bd-ib-s124-poisoned")

    result = _press(
        repo=repo,
        item_id="bd-ib-s124-poisoned",
        answer=f"Take option B, then run {_EXPRESSION_OPENER} justfile.recipe }}}}.",
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "answer-would-poison-goal"
    assert _EXPRESSION_OPENER in str(result["summary"])
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-s124-poisoned") == ()
    record = _fake().show_issue(issue_id="bd-ib-s124-poisoned")
    assert record["status"] == "blocked"
    assert "blocked-reason:needs-human" in record["labels"]

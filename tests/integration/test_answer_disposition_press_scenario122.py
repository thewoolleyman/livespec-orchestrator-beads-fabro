"""Scenario 122 — an attention item's answer disposition governs who may answer.

Integration-tier binding for the `SPECIFICATION/scenarios.md` heading
`## Scenario 122 — An attention item's answer disposition governs who may answer
it`, whose four gherkin scenarios are the four cases below. The clause it
realizes is the FIFTH dispatcher policy setting of
`SPECIFICATION/contracts.md`, read together with the dispatcher-admission
clause of the same file. Both are cited at the FILE level deliberately: a
heading-level citation in source rots on rename, and the repository's own
doctor check refuses one.

EVERY CASE DRIVES THE PUBLIC SURFACES, never the gate in isolation. The presses
go through `drive.run_action`, and the advertised lane and the reported
disposition come off the composed `build_attention` envelope rendered to JSON —
the two surfaces the ratified advertiser-and-enforcer binding names. A case that
called `answer_press_refusal` directly could show that the gate computes a
verdict and could not show that `drive` consults it, which is the whole claim.

WHY EVERY REFUSAL CASE ALSO READS THE TENANT. A refusal is a claim about what
did NOT happen, and the payload cannot carry it: a build that refused the press
AFTER writing the comment returns the identical dictionary. So each refused
press asserts the item is still `blocked` and the ledger still carries no
comment, which is the only place the two builds differ.

WHY THE CONSENSUS CASES RUN AGAINST A `consensus` GLOBAL AND A `human` LABEL.
The per-item label may only LOWER an item to `human`, so a case that asserted
`human` under a `human` global would pass on a build that ignored labels
entirely. Both items here are seeded into ONE tenant under ONE `consensus`
global, so the labelled row reading `human` and the unlabelled row reading
`consensus` are the same snapshot disagreeing with itself — which no
label-blind and no global-blind build can produce.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import fake_singleton, reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    read_answer_disposition_labels,
)
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_answer_disposition,
)
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.commands.needs_attention import (
    build_attention,
    render_json,
)
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput
from returns.unsafe import unsafe_perform_io

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_TENANT = "livespec-orchestrator-beads-fabro"
_PREFIX = "bd-ib"
_LABELLED = "bd-ib-labelled"
_PLAIN = "bd-ib-plain"
_ANSWER = "Take option B; the second provider is out of scope for this slice."
# The gate's own refusal code, spelled here rather than imported so this file
# keeps naming the record it means to read.
_REFUSED = "answer-disposition-refused"
_HUMAN = "human"
_CONSENSUS = "consensus"
# An automated disposition's identity, and a human operator's. Both assert a
# `<role>:<name>` identity through the SAME input, so the only difference
# between the two presses is the role — which is what the gate reads.
_AUTOMATED = InvokerIdentity(invoker="session:overseerd", invoker_source="flag")
_OPERATOR = InvokerIdentity(invoker="human:chad", invoker_source="flag")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A fresh in-memory tenant per case, with the fake backend selected."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_scenario122_an_automated_press_is_refused_and_a_human_press_is_admitted(
    tmp_path: Path,
) -> None:
    """Given effective answer disposition human,
    When an automated disposition presses resolve-blocked with an answer,
    Then drive refuses the press naming the work-item and the disposition human,
    And the same press from a human operator lands the answer as a ledger comment.

    One case for both halves, because either alone is uninformative: a build
    that refused EVERY press passes the refusal, and a build that admitted
    every press passes the admission. Only the pair pins the gate to the role.
    """
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_parked(id_=_PLAIN))
    action = f"resolve-blocked:{_PLAIN}:ready"

    refused = run_action(repo=repo, action_id=action, answer=_ANSWER, identity=_AUTOMATED)

    assert refused["status"] == "failed"
    assert refused["domain_error"] == _REFUSED
    # The refusal names the work-item and the effective disposition, which is
    # what sends the presser to the right remedy rather than to a retry.
    assert _PLAIN in str(refused["summary"])
    assert f"disposition for {_PLAIN} is {_HUMAN}" in str(refused["summary"])
    assert _still_parked_with_no_comment(item_id=_PLAIN)

    admitted = run_action(repo=repo, action_id=action, answer=_ANSWER, identity=_OPERATOR)

    assert admitted["status"] == "green"
    assert admitted["target_status"] == "ready"
    assert [_comment_text(record) for record in _comments(item_id=_PLAIN)] == [
        f"livespec-human-answer ({_OPERATOR.invoker} via {_OPERATOR.invoker_source}, "
        f"{_answered_at(item_id=_PLAIN)}, {action}):\n{_ANSWER}"
    ]


def test_scenario122_a_per_item_label_lowers_the_item_and_the_lane_offers_no_answer_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a global consensus disposition and an item carrying `answer:human`,
    When the effective answer disposition is resolved for that item,
    Then it is human,
    And the resolve-blocked lane advertises no answer handoff drive would refuse.

    The binding is satisfied by offering NONE: the lane's handoff is the plain
    `resolve-blocked:<id>:ready` action it has always been, so no advertised
    command carries an answer for the gate to refuse. Asserting the action id
    alone would not show that — a command string carrying `--answer` beside an
    unchanged action id is exactly the drift this reads for.
    """
    repo = _repo(tmp_path=tmp_path, disposition=_CONSENSUS)
    append_work_item(path=_config(), item=_parked(id_=_LABELLED))
    fake_singleton().update_issue(issue_id=_LABELLED, add_labels=[f"answer:{_HUMAN}"])

    assert _resolved_disposition(repo=repo, item_id=_LABELLED) == _HUMAN

    handoff = _valve_entry(repo=repo, monkeypatch=monkeypatch, item_id=_LABELLED)["handoff"]

    assert handoff["action_id"] == f"resolve-blocked:{_LABELLED}:ready"
    assert "--answer" not in str(handoff["command"])
    assert "answer" not in str(handoff["action_id"])


def test_scenario122_an_automated_press_under_consensus_is_refused_exactly_as_under_human(
    tmp_path: Path,
) -> None:
    """Given effective answer disposition consensus, livespec core having not ratified it,
    When an automated disposition presses resolve-blocked with an answer,
    Then drive refuses the press exactly as under the human disposition.

    "Exactly as" is read as the refusal code, the admitted-identity clause and
    the written-nothing outcome all being identical, with only the reported
    disposition differing. A build that quietly admitted the consensus tier
    today would return `green` here, which is the one shape this forbids.
    """
    consensus_repo = _repo(tmp_path=tmp_path / "consensus", disposition=_CONSENSUS)
    append_work_item(path=_config(), item=_parked(id_=_PLAIN))

    refused = run_action(
        repo=consensus_repo,
        action_id=f"resolve-blocked:{_PLAIN}:ready",
        answer=_ANSWER,
        identity=_AUTOMATED,
    )

    assert _resolved_disposition(repo=consensus_repo, item_id=_PLAIN) == _CONSENSUS
    assert refused["status"] == "failed"
    assert refused["domain_error"] == _REFUSED
    assert f"disposition for {_PLAIN} is {_CONSENSUS}" in str(refused["summary"])
    assert "admits an answer only from human:<name>" in str(refused["summary"])
    assert _still_parked_with_no_comment(item_id=_PLAIN)


def test_scenario122_the_json_snapshot_carries_each_attention_entrys_effective_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given blocked work-items whose blocked_reason is needs-human,
    When needs-attention composes its snapshot as JSON,
    Then each item's attention entry carries its effective answer disposition.

    TWO rows under ONE `consensus` global, one of them labelled down to
    `human`. That is what makes "its own" disposition checkable: a build that
    reported the global on every row, or the label-derived value on every row,
    renders both entries the same and fails whichever row it got wrong.
    """
    repo = _repo(tmp_path=tmp_path, disposition=_CONSENSUS)
    append_work_item(path=_config(), item=_parked(id_=_LABELLED))
    append_work_item(path=_config(), item=_parked(id_=_PLAIN))
    fake_singleton().update_issue(issue_id=_LABELLED, add_labels=[f"answer:{_HUMAN}"])

    entries = _valve_entries(repo=repo, monkeypatch=monkeypatch)

    assert sorted(entries) == [
        f"valve:resolve-blocked:{_LABELLED}",
        f"valve:resolve-blocked:{_PLAIN}",
    ]
    lowered = str(entries[f"valve:resolve-blocked:{_LABELLED}"]["summary"])
    inherited = str(entries[f"valve:resolve-blocked:{_PLAIN}"]["summary"])
    assert f"Effective answer disposition {_HUMAN}:" in lowered
    assert f"Effective answer disposition {_CONSENSUS}:" not in lowered
    assert f"Effective answer disposition {_CONSENSUS}:" in inherited
    assert f"Effective answer disposition {_HUMAN}:" not in inherited


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    """Stand the cross-plane spec lane down: it answers nothing this heading asks."""
    _ = project_root
    return None


def _resolved_disposition(*, repo: Path, item_id: str) -> str:
    """The item's effective disposition, through the production resolver.

    `unsafe_perform_io` is mandatory rather than decorative: `IOResult.value_or`
    yields `IO[value]`, and that wrapper compares equal to no disposition at
    all — so omitting it would make every assertion here fail for the wrong
    reason.
    """
    item = materialize_work_items(records=read_work_items(path=_config()))[item_id]
    labels = read_answer_disposition_labels(path=_config()).get(item_id, ())
    return unsafe_perform_io(
        effective_answer_disposition(item=item, cwd=repo, raw_labels=labels).value_or("unresolved")
    )


def _valve_entries(*, repo: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, object]]:
    """Every resolve-blocked valve entry of the composed JSON snapshot, by id.

    The cross-plane spec lane is the one thing stood down, because it reaches
    outside this repository's tenant and answers nothing this heading asks.
    Everything else — the store seam, the label read, the lane composition and
    the conformance boundary — is production code.
    """
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    attention = build_attention(project_root=repo, repo_name="repo", include_hygiene=False)
    payload = json.loads(render_json(attention=attention))
    return {
        str(entry["id"]): entry
        for entry in payload["attention"]
        if str(entry["id"]).startswith("valve:resolve-blocked:")
    }


def _valve_entry(*, repo: Path, monkeypatch: pytest.MonkeyPatch, item_id: str) -> dict[str, object]:
    return _valve_entries(repo=repo, monkeypatch=monkeypatch)[f"valve:resolve-blocked:{item_id}"]


def _still_parked_with_no_comment(*, item_id: str) -> bool:
    """Whether a refused press left the item exactly as it was resting."""
    record = fake_singleton().show_issue(issue_id=item_id)
    return record["status"] == "blocked" and _comments(item_id=item_id) == []


def _comments(*, item_id: str) -> list[dict[str, object]]:
    return list(fake_singleton().list_comments(issue_id=item_id))


def _comment_text(record: dict[str, object]) -> str:
    """One comment's body, read off `text`.

    `text` is the key beads returns, and `body` is the one this repository's
    agent instructions record two sessions reaching for: it yields an empty
    string per comment, which is the identical observation to a lost write.
    """
    return str(record["text"])


def _answered_at(*, item_id: str) -> str:
    """The write instant the delivered comment recorded, read back from it.

    Read out of the comment rather than frozen, because the assertion this
    serves is about the header's SHAPE — the invoker, its source, the instant
    and the action id, in that order — and a frozen clock would prove only that
    a patched function was called.
    """
    head = _comment_text(_comments(item_id=item_id)[0]).split("\n", 1)[0]
    return head.rstrip("):").rsplit(", ", 2)[-2]


def _parked(*, id_: str) -> WorkItem:
    """A work-item resting at `blocked` with `blocked_reason: needs-human`."""
    return WorkItem(
        id=id_,
        type="task",
        status="blocked",
        title=f"Parked on a question ({id_})",
        description="It could not be finished without a decision.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        blocked_reason="needs-human",
    )


def _repo(*, tmp_path: Path, disposition: str | None = None) -> Path:
    """A governed clone, carrying the global disposition when one is configured.

    An ABSENT `answer_disposition` key is the documented default rather than a
    gap, so the human-disposition cases configure nothing: that is the shape
    every repository in this fleet actually carries today.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    block: dict[str, object] = {"connection": {"prefix": _PREFIX}}
    if disposition is not None:
        block["dispatcher"] = {"answer_disposition": disposition}
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

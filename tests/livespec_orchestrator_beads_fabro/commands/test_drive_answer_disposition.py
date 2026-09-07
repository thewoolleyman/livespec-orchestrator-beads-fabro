"""The v104 gate on WHO may answer an attention item, enforced at `drive`.

The ratified clause in `SPECIFICATION/contracts.md` says `drive` MUST refuse a
`resolve-blocked … --answer` press the item's effective answer disposition does
not admit, naming the work-item and that disposition. Every test here drives
the valve entry point rather than the gate function, because the refusal is
only worth anything where an operator meets it — and because the property that
matters most is what a refusal leaves behind: an item still parked, with no
comment and no transition.

The control pair is the first test, and it is a pair on purpose. Asserting only
the refusal would pass just as well against a gate that refuses everyone, so the
admitted half runs the SAME answer against the SAME item shape and differs in
one input: the invoker the press asserted.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    ANSWER_DISPOSITION_LABEL_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ANSWER = "Take option B: the guard stays fail-closed."
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _repo(*, tmp_path: Path, dispatcher: dict[str, object] | None = None) -> Path:
    """A repository root whose committed configuration the valve will read."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    block: dict[str, object] = {
        "connection": {
            "tenant": "livespec-impl-beads",
            "prefix": "bd",
            "server_user": "livespec-impl-beads",
            "database": "livespec-impl-beads",
            "bd_path": "bd",
            "fake": True,
        }
    }
    if dispatcher is not None:
        block["dispatcher"] = dispatcher
    _ = (repo / ".livespec.jsonc").write_text(json.dumps({_PLUGIN_BLOCK: block}), encoding="utf-8")
    return repo


def _parked(*, item_id: str, label: str | None = None) -> WorkItem:
    """One attention item: parked at `blocked` on a `needs-human` question."""
    item = replace(
        WorkItem(
            id=item_id,
            type="task",
            status="blocked",
            title="Parked on a question",
            description="d",
            origin="freeform",
            rank="a1",
            gap_id=None,
            assignee=None,
            depends_on=(),
            captured_at="2026-09-07T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
        blocked_reason="needs-human",
    )
    append_work_item(path=_config(), item=item)
    if label is not None:
        _fake().update_issue(
            issue_id=item_id, add_labels=[f"{ANSWER_DISPOSITION_LABEL_PREFIX}{label}"]
        )
    return item


def _press(*, repo: Path, item_id: str, invoker: str, answer: str | None = _ANSWER) -> dict:
    return run_human_valve_action(
        repo=repo,
        action_id=f"resolve-blocked:{item_id}:ready",
        identity=InvokerIdentity(invoker=invoker, invoker_source="flag"),
        answer=answer,
    )


def test_a_human_press_is_admitted_while_the_same_automated_press_is_refused(
    tmp_path: Path,
) -> None:
    """The control pair: one input differs — who the press asserted it came from."""
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id="bd-ib-ad-human")
    _parked(item_id="bd-ib-ad-auto")

    admitted = _press(repo=repo, item_id="bd-ib-ad-human", invoker="human:cw")
    refused = _press(repo=repo, item_id="bd-ib-ad-auto", invoker="session:overseerd")

    assert admitted["status"] == "green"
    assert admitted["target_status"] == "ready"
    [comment] = read_work_item_comments(path=_config(), work_item_id="bd-ib-ad-human")
    assert _ANSWER in comment.text
    assert refused["status"] == "failed"
    assert refused["domain_error"] == "answer-disposition-refused"
    assert _fake().show_issue(issue_id="bd-ib-ad-auto")["status"] == "blocked"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-ad-auto") == ()


def test_the_refusal_names_the_work_item_and_the_effective_disposition(
    tmp_path: Path,
) -> None:
    """Both, in the message an operator actually reads, and the press it refused."""
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id="bd-ib-ad-named")

    refused = _press(repo=repo, item_id="bd-ib-ad-named", invoker="foreman:seat-1")

    summary = str(refused["summary"])
    assert "bd-ib-ad-named" in summary
    assert "disposition for bd-ib-ad-named is human" in summary
    assert "foreman:seat-1" in summary


def test_an_identity_asserting_no_role_is_not_a_human_press(tmp_path: Path) -> None:
    """The fallback MARK and a nameless role both assert no one, so both are refused.

    The mark is the identity an unattended process carries by DEFAULT, so
    reading it as a person at a shell would admit the automation the
    disposition exists to keep out.
    """
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id="bd-ib-ad-mark")
    _parked(item_id="bd-ib-ad-nameless")

    unattributed = _press(repo=repo, item_id="bd-ib-ad-mark", invoker="unattributed:cw@box")
    nameless = _press(repo=repo, item_id="bd-ib-ad-nameless", invoker="human: ")

    assert unattributed["domain_error"] == "answer-disposition-refused"
    assert nameless["domain_error"] == "answer-disposition-refused"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-ad-mark") == ()
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-ad-nameless") == ()


def test_consensus_refuses_an_automated_press_exactly_as_human_does(tmp_path: Path) -> None:
    """`consensus` behaves as `human` until livespec core ratifies the tier.

    So the opted-in repository is the case that could fail open, and the
    refusal still has to name the disposition the operator configured rather
    than the one it behaves as.
    """
    repo = _repo(tmp_path=tmp_path, dispatcher={"answer_disposition": "consensus"})
    _parked(item_id="bd-ib-ad-consensus")
    _parked(item_id="bd-ib-ad-consensus-human")

    refused = _press(repo=repo, item_id="bd-ib-ad-consensus", invoker="session:overseerd")
    admitted = _press(repo=repo, item_id="bd-ib-ad-consensus-human", invoker="human:cw")

    assert refused["domain_error"] == "answer-disposition-refused"
    assert "disposition for bd-ib-ad-consensus is consensus" in str(refused["summary"])
    assert admitted["status"] == "green"


def test_a_per_item_answer_label_lowers_an_opted_in_repository(tmp_path: Path) -> None:
    """The gate reads the item's own label, not the global default alone."""
    repo = _repo(tmp_path=tmp_path, dispatcher={"answer_disposition": "consensus"})
    _parked(item_id="bd-ib-ad-lowered", label="human")

    refused = _press(repo=repo, item_id="bd-ib-ad-lowered", invoker="session:overseerd")

    assert refused["domain_error"] == "answer-disposition-refused"
    assert "disposition for bd-ib-ad-lowered is human" in str(refused["summary"])


def test_a_press_carrying_no_answer_is_not_gated_on_who_pressed_it(tmp_path: Path) -> None:
    """The ratified refusal is scoped to a press CARRYING `--answer`.

    A plain `resolve-blocked` transition decides nothing on the item's behalf,
    so gating it would refuse the ordinary queue-control move the valve has
    always been.
    """
    repo = _repo(tmp_path=tmp_path)
    _parked(item_id="bd-ib-ad-bare")

    result = _press(repo=repo, item_id="bd-ib-ad-bare", invoker="session:overseerd", answer=None)

    assert result["status"] == "green"
    assert _fake().show_issue(issue_id="bd-ib-ad-bare")["status"] == "ready"

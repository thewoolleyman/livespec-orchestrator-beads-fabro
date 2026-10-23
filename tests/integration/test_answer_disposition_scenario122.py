"""Integration-tier acceptance for Scenario 122's answer-disposition policy.

Binds `SPECIFICATION/scenarios.md` "Scenario 122 — An attention item's answer
disposition governs who may answer it" and the fifth dispatcher policy setting
of `SPECIFICATION/contracts.md` that it realizes.

EVERY CASE DRIVES THE TWO SURFACES AN OPERATOR MEETS, not the gate and the
advertiser behind them: the press goes through `drive.run_action`, the published
disposition through the real `needs_attention.main(argv=["--json", ...])`
envelope, and both read the same tenant over the REAL store/client seam against
the in-memory `FakeBeadsClient`. That is what makes the clause's
advertiser-and-enforcer binding observable at all — the binding is a claim about
two surfaces AGREEING, and a test that called `answer_press_refusal` and
`answer_disposition_summary` directly could show neither surface composing nor
the handoff an operator is actually offered.

THE REFUSAL AND THE ADMISSION ARE ONE CASE, deliberately. A refusal asserted
alone passes just as well against a gate that refuses every press, which would
make the ratified answer route unreachable; the admitted half therefore runs the
IDENTICAL answer against an identically-shaped item and differs in exactly one
input — the role the invoker asserts.

THE CONSENSUS LEG IS COMPARED BYTE FOR BYTE against the human leg's refusal
rather than needle by needle, because the clause's requirement is that consensus
refuse "exactly as under the human disposition": two independently drifting
messages that each mention the item and a disposition satisfy a containment
check just as well, and the one thing that must differ — the disposition the
operator configured — is asserted separately.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_answer_disposition import (
    ANSWER_DISPOSITION_LABEL_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_item_comments
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_ANSWER = "Take option B: the guard stays fail-closed."
_HUMAN_INVOKER = "human:cwoolley"
_AUTOMATED_INVOKER = "session:overseerd"
# The two sentences the advertiser composes, one per effective disposition. They
# are asserted through their load-bearing opening clause rather than in full:
# the clause requires the entry to CARRY the effective disposition, and the
# prose around it is the advertiser's to reword.
_HUMAN_SENTENCE = "Effective answer disposition human:"
_CONSENSUS_SENTENCE = "Effective answer disposition consensus:"


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


def _repo(*, tmp_path: Path, answer_disposition: str | None) -> Path:
    """A repository root whose COMMITTED configuration both surfaces read.

    `answer_disposition=None` writes no `dispatcher` block at all, which is the
    shape of every repository that has not opted in — so the `human` leg
    exercises the setting's own ratified default rather than a value this
    fixture restates.
    """
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    block: dict[str, object] = {
        "connection": {
            "tenant": "livespec-impl-beads",
            "prefix": "bd-ib",
            "server_user": "livespec-impl-beads",
            "database": "livespec-impl-beads",
            "bd_path": "bd",
            "fake": True,
        }
    }
    if answer_disposition is not None:
        block["dispatcher"] = {"answer_disposition": answer_disposition}
    _ = (repo / ".livespec.jsonc").write_text(json.dumps({_PLUGIN_BLOCK: block}), encoding="utf-8")
    return repo


def _parked(*, item_id: str, label: str | None) -> None:
    """Seed one attention item: parked at `blocked` on a `needs-human` question.

    The `answer:` override is written through the client's own public write verb
    because the shared `WorkItem` model carries no field for it — the label is
    exactly what `read_answer_disposition_labels` reads back off the raw record.
    """
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
    if label is not None:
        _fake().update_issue(
            issue_id=item_id, add_labels=[f"{ANSWER_DISPOSITION_LABEL_PREFIX}{label}"]
        )


def _press(*, repo: Path, item_id: str, invoker: str) -> dict[str, object]:
    """One `resolve-blocked … --answer` press through the operator entry point."""
    return run_action(
        repo=repo,
        action_id=f"resolve-blocked:{item_id}:ready",
        identity=InvokerIdentity(invoker=invoker, invoker_source="flag"),
        answer=_ANSWER,
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _snapshot(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> list[dict[str, object]]:
    """Every attention entry of the real JSON envelope, as a console reads it."""
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    exit_code = needs_attention.main(
        argv=["--json", "--project-root", str(repo), "--repo-name", "repo", "--skip-hygiene"]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    return list(payload["attention"])


def _resolve_blocked_entry(*, entries: list[dict[str, object]], item_id: str) -> dict[str, object]:
    [entry] = [one for one in entries if one["id"] == f"valve:resolve-blocked:{item_id}"]
    return entry


def test_scenario122_an_automated_press_is_refused_and_a_human_press_lands_the_answer(
    tmp_path: Path,
) -> None:
    """The control pair: one input differs — the role the press asserted.

    Both halves are asserted on what the press LEFT BEHIND rather than on its
    status word alone: the refused item is still parked with no comment, and the
    admitted one carries the operator's answer on the ledger, which is the only
    channel the next dispatch's brief reads.
    """
    repo = _repo(tmp_path=tmp_path, answer_disposition=None)
    _parked(item_id="bd-ib-s122-auto", label=None)
    _parked(item_id="bd-ib-s122-human", label=None)

    refused = _press(repo=repo, item_id="bd-ib-s122-auto", invoker=_AUTOMATED_INVOKER)
    admitted = _press(repo=repo, item_id="bd-ib-s122-human", invoker=_HUMAN_INVOKER)

    assert refused["status"] == "failed"
    assert refused["domain_error"] == "answer-disposition-refused"
    summary = str(refused["summary"])
    assert "bd-ib-s122-auto" in summary
    assert "disposition for bd-ib-s122-auto is human" in summary
    assert _fake().show_issue(issue_id="bd-ib-s122-auto")["status"] == "blocked"
    assert read_work_item_comments(path=_config(), work_item_id="bd-ib-s122-auto") == ()
    assert admitted["status"] == "green"
    assert admitted["target_status"] == "ready"
    [comment] = read_work_item_comments(path=_config(), work_item_id="bd-ib-s122-human")
    assert _ANSWER in comment.text


def test_scenario122_a_per_item_human_label_outranks_a_consensus_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The label LOWERS an opted-in repository, and the lane advertises no press.

    The sibling in the same tenant carries no label, so it reports the
    repository's own `consensus` setting: without it, "the labelled item reports
    human" is equally consistent with an advertiser that reports `human` for
    every row, which is also the one direction this fallback must never fail in.

    The advertiser-and-enforcer binding is read off the HANDOFF the envelope
    publishes, which is the only thing an operator can press: the lane may name
    the disposition in its summary and MUST NOT offer a command the enforcer
    above would refuse.
    """
    repo = _repo(tmp_path=tmp_path, answer_disposition="consensus")
    _parked(item_id="bd-ib-s122-lowered", label="human")
    _parked(item_id="bd-ib-s122-inherits", label=None)

    entries = _snapshot(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    lowered = _resolve_blocked_entry(entries=entries, item_id="bd-ib-s122-lowered")
    inherits = _resolve_blocked_entry(entries=entries, item_id="bd-ib-s122-inherits")
    refused = _press(repo=repo, item_id="bd-ib-s122-lowered", invoker=_AUTOMATED_INVOKER)

    assert _HUMAN_SENTENCE in str(lowered["summary"])
    assert _CONSENSUS_SENTENCE in str(inherits["summary"])
    handoff = lowered["handoff"]
    assert isinstance(handoff, dict)
    assert handoff["action_id"] == "resolve-blocked:bd-ib-s122-lowered:ready"
    assert "--answer" not in str(handoff["command"])
    # The enforcer agrees with what the advertiser reported for this item.
    assert refused["domain_error"] == "answer-disposition-refused"
    assert "disposition for bd-ib-s122-lowered is human" in str(refused["summary"])


def test_scenario122_consensus_refuses_an_automated_press_exactly_as_human_does(
    tmp_path: Path,
) -> None:
    """`consensus` behaves as `human` until livespec core ratifies the tier.

    So the opted-in repository is the leg that could fail OPEN, and the two
    refusals are compared BYTE FOR BYTE with the disposition word substituted:
    the clause asks for the same refusal, and two messages that merely both
    mention a disposition would satisfy a weaker reading.
    """
    human_repo = _repo(tmp_path=tmp_path / "human", answer_disposition=None)
    consensus_repo = _repo(tmp_path=tmp_path / "consensus", answer_disposition="consensus")
    _parked(item_id="bd-ib-s122-cmp-human", label=None)
    _parked(item_id="bd-ib-s122-cmp-consensus", label=None)

    under_human = _press(
        repo=human_repo, item_id="bd-ib-s122-cmp-human", invoker=_AUTOMATED_INVOKER
    )
    under_consensus = _press(
        repo=consensus_repo, item_id="bd-ib-s122-cmp-consensus", invoker=_AUTOMATED_INVOKER
    )

    assert under_consensus["domain_error"] == under_human["domain_error"]
    normalized = str(under_consensus["summary"]).replace(
        "bd-ib-s122-cmp-consensus is consensus", "bd-ib-s122-cmp-human is human"
    )
    assert normalized.replace("bd-ib-s122-cmp-consensus", "bd-ib-s122-cmp-human") == str(
        under_human["summary"]
    )
    # Neither press wrote anything, which is what makes a refusal free to retry.
    for item_id in ("bd-ib-s122-cmp-human", "bd-ib-s122-cmp-consensus"):
        assert _fake().show_issue(issue_id=item_id)["status"] == "blocked"
        assert read_work_item_comments(path=_config(), work_item_id=item_id) == ()


def test_scenario122_every_parked_entry_of_the_json_snapshot_carries_its_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Composed as JSON, EACH parked entry reports its OWN effective disposition.

    Two parked items under one repository setting, differing only in whether
    they carry the per-item override, so a snapshot that reported one
    disposition for the whole tenant cannot pass. The non-parked control in the
    same tenant must produce no resolve-blocked entry at all, since a lane that
    fired on every row would also satisfy a per-entry assertion.
    """
    repo = _repo(tmp_path=tmp_path, answer_disposition="consensus")
    _parked(item_id="bd-ib-s122-json-lowered", label="human")
    _parked(item_id="bd-ib-s122-json-open", label=None)
    append_work_item(
        path=_config(),
        item=replace(
            WorkItem(
                id="bd-ib-s122-json-ready",
                type="task",
                status="ready",
                title="Not parked on anything",
                description="d",
                origin="freeform",
                gap_id=None,
                rank="a3",
                assignee=None,
                depends_on=(),
                captured_at="2026-10-22T00:00:00Z",
                resolution=None,
                reason=None,
                audit=None,
                superseded_by=None,
            ),
            blocked_reason=None,
        ),
    )

    entries = _snapshot(repo=repo, monkeypatch=monkeypatch, capsys=capsys)
    parked = {
        str(entry["id"]): str(entry["summary"])
        for entry in entries
        if str(entry["id"]).startswith("valve:resolve-blocked:")
    }

    assert sorted(parked) == [
        "valve:resolve-blocked:bd-ib-s122-json-lowered",
        "valve:resolve-blocked:bd-ib-s122-json-open",
    ]
    assert _HUMAN_SENTENCE in parked["valve:resolve-blocked:bd-ib-s122-json-lowered"]
    assert _CONSENSUS_SENTENCE in parked["valve:resolve-blocked:bd-ib-s122-json-open"]

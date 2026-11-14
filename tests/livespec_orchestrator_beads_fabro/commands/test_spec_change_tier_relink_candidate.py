"""A held item whose generalization target was ratified under another topic names it.

`bd-ib-jnbcny`: the autonomy-tier bullet of `SPECIFICATION/contracts.md` asks that
the pre-dispatch wall's refusal of an `unratified-topic` hold NAME the proposed-change
topic and specification version of a revision that amended the record's
generalization-target heading, so a seat whose filing-time stem went stale can
see the relink it owes.

THE SPEC HISTORY IS A REAL FIXTURE, not a stubbed candidate: the thing the read
has to get right is the comparison of one heading's body between consecutive
history snapshots, and a double that returned a candidate would pass for a read
that compared nothing. `reject` is the control the clause names ("A revision whose
decision is `reject` MUST NOT be named"), and the unchanged-heading case is the
control that the read does not name every later ratification.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    decide_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_spec_change_tier_relink_candidate.py"
)
_ITEM = "bd-ib-held"
_LINKED_TOPIC = "the-stem-the-dispatcher-derived"
_TARGET = "## A governing clause"
_OTHER_HEADING = "## An unrelated clause"
_DERIVED_TOPIC = "hold-an-unstated-feature-for"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _module(*, name: str) -> Any:
    return importlib.import_module(f"{_PACKAGE}.{name}")


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _snapshot(*, spec_root: Path, version: int, body: str, filename: str = "spec.md") -> Path:
    version_dir = spec_root / "history" / f"v{version:03d}"
    version_dir.mkdir(parents=True, exist_ok=True)
    _ = (version_dir / filename).write_text(
        f"# Spec\n\n{_OTHER_HEADING}\n\nstable\n\n{_TARGET}\n\n{body}\n\n## Last clause\n\nend\n",
        encoding="utf-8",
    )
    return version_dir


def _revise(*, version_dir: Path, topic: str, decision: str) -> None:
    changes = version_dir / "proposed_changes"
    changes.mkdir(parents=True, exist_ok=True)
    _ = (changes / f"{topic}.md").write_text("the proposal\n", encoding="utf-8")
    _ = (changes / f"{topic}-revision.md").write_text(
        f"---\nproposal: {topic}.md\ndecision: {decision}\n---\n", encoding="utf-8"
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION").mkdir(parents=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM,
        type="bug",
        status="ready",
        title="Hold an unstated feature for its proposal",
        description="New observable behaviour.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _record_hold(*, repo: Path, spec_version: str, target: str | None = _TARGET) -> None:
    item = _item()
    append_work_item(path=_config(repo=repo), item=item)
    decision = decide_spec_change_tier(
        item=item,
        classification="feature",
        verdict=SpecStatedVerdict(
            kind="unstated",
            stated_by=(),
            generalization_target=target,
            rationale="the ratified text does not state the whole of it",
        ),
    )
    append_work_item_comment(
        path=_config(repo=repo),
        work_item_id=_ITEM,
        body=spec_change_tier_comment(
            item_id=_ITEM,
            stage=STAGE_DISPATCH,
            decision=decision,
            spec_version=spec_version,
            digest="a-digest",
        ),
    )


def _recorded(*, spec_version: str, target: str | None = _TARGET) -> Any:
    return _module(name="_spec_change_tier_record").RecordedSpecChangeTier(
        tier="spec-change",
        classification="feature",
        verdict_kind="unstated",
        generalization_target=target,
        linked_proposal_topic=_LINKED_TOPIC,
        spec_version=spec_version,
        digest="a-digest",
    )


def _candidate(*, spec_root: Path, spec_version: str = "1", target: str | None = _TARGET) -> Any:
    assert _MODULE_PATH.is_file()
    return _module(name="_spec_change_tier_relink_candidate").relink_candidate(
        spec_root=spec_root, recorded=_recorded(spec_version=spec_version, target=target)
    )


def _refusal(*, repo: Path) -> str:
    refusal = _module(name="_spec_change_tier_wall").spec_change_tier_refusal(
        repo=repo, items=[_item()]
    )
    assert refusal is not None
    return refusal


def test_a_later_accepted_revision_that_amended_the_target_is_a_candidate(
    tmp_path: Path,
) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="the-topic-it-was-filed-under",
        decision="accept",
    )

    found = _candidate(spec_root=spec_root)
    assert (found.topic, found.spec_version) == ("the-topic-it-was-filed-under", "v002")


def test_a_modify_decision_is_a_candidate_too(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-modified-topic",
        decision="modify",
    )

    assert _candidate(spec_root=spec_root).topic == "a-modified-topic"


def test_a_rejected_revision_is_never_a_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-rejected-topic",
        decision="reject",
    )

    assert _candidate(spec_root=spec_root) is None


def test_the_most_recently_cut_amending_revision_is_the_one_named(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="first body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="second body"),
        topic="the-earlier-topic",
        decision="accept",
    )
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=3, body="third body"),
        topic="the-later-topic",
        decision="accept",
    )

    found = _candidate(spec_root=spec_root)
    assert (found.topic, found.spec_version) == ("the-later-topic", "v003")


def test_a_later_ratification_that_left_the_target_alone_is_not_a_candidate(
    tmp_path: Path,
) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="same body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="same body"),
        topic="an-unrelated-topic",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root) is None


def test_a_ratification_after_the_amendment_does_not_inherit_the_amendment(
    tmp_path: Path,
) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="the-amending-topic",
        decision="accept",
    )
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=3, body="new body"),
        topic="a-later-unrelated-topic",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root).topic == "the-amending-topic"


def test_an_amendment_cut_at_or_before_the_record_is_not_a_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-topic-cut-before-the-record",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root, spec_version="2") is None


def test_the_linked_topic_itself_is_not_a_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic=_LINKED_TOPIC,
        decision="accept",
    )

    assert _candidate(spec_root=spec_root) is None


def test_a_heading_inside_a_code_fence_does_not_end_the_body(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    fenced = "```\n## not a heading\n```\n{}"
    _ = _snapshot(spec_root=spec_root, version=1, body=fenced.format("old tail"))
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body=fenced.format("new tail")),
        topic="a-topic-amending-after-a-fence",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root).topic == "a-topic-amending-after-a-fence"


def test_a_target_without_the_hash_prefix_resolves_to_the_same_heading(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-topic-named-without-hashes",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root, target="A governing clause").topic == (
        "a-topic-named-without-hashes"
    )


def test_a_record_naming_no_target_has_no_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-topic-nobody-targeted",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root, target=None) is None


def test_an_unparseable_record_version_has_no_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-topic-with-no-baseline",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root, spec_version="") is None


def test_a_record_whose_version_snapshot_is_gone_has_no_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-topic-with-no-baseline",
        decision="accept",
    )

    assert _candidate(spec_root=spec_root, spec_version="1") is None


def test_a_snapshot_that_cannot_be_read_names_no_candidate(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    unreadable = _snapshot(spec_root=spec_root, version=2, body="new body")
    _revise(version_dir=unreadable, topic="a-topic-in-a-broken-snapshot", decision="accept")
    _ = (unreadable / "broken.md").write_bytes(b"\xff\xfe not utf-8")

    assert _candidate(spec_root=spec_root) is None


def test_a_pruned_snapshot_is_passed_over(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    pruned = _snapshot(spec_root=spec_root, version=2, body="new body")
    _revise(version_dir=pruned, topic="a-topic-in-a-pruned-snapshot", decision="accept")
    _ = (pruned / "PRUNED_HISTORY.json").write_text("{}", encoding="utf-8")

    assert _candidate(spec_root=spec_root) is None


def test_a_snapshot_that_dropped_the_heading_is_not_an_amendment(tmp_path: Path) -> None:
    spec_root = tmp_path / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    version_dir = spec_root / "history" / "v002"
    version_dir.mkdir()
    _ = (version_dir / "spec.md").write_text("# Spec\n\n## Another clause\n\nx\n", encoding="utf-8")
    _revise(version_dir=version_dir, topic="a-topic-that-removed-it", decision="accept")

    assert _candidate(spec_root=spec_root) is None


def test_an_absent_history_directory_has_no_candidate(tmp_path: Path) -> None:
    assert _candidate(spec_root=tmp_path / "SPECIFICATION") is None


def test_the_refusal_names_the_candidate_topic_and_specification_version(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    spec_root = repo / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="the-topic-it-was-filed-under",
        decision="accept",
    )
    _record_hold(repo=repo, spec_version="1")

    refusal = _refusal(repo=repo)
    assert "relink candidate" in refusal
    assert "the-topic-it-was-filed-under" in refusal
    assert "v002" in refusal
    assert f"relink-spec-tier:{_ITEM}:the-topic-it-was-filed-under" in refusal
    assert "Hold reason: unratified-topic." in refusal


def test_the_refusal_names_the_most_recently_cut_candidate(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    spec_root = repo / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="first body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="second body"),
        topic="the-earlier-topic",
        decision="accept",
    )
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=3, body="third body"),
        topic="the-later-topic",
        decision="modify",
    )
    _record_hold(repo=repo, spec_version="1")

    refusal = _refusal(repo=repo)
    assert "the-later-topic" in refusal
    assert "the-earlier-topic" not in refusal


def test_a_hold_whose_target_no_later_revision_amended_refuses_exactly_as_before(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    spec_root = repo / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="same body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="same body"),
        topic="an-unrelated-topic",
        decision="accept",
    )
    _record_hold(repo=repo, spec_version="1")

    assert _refusal(repo=repo) == (
        f"REFUSED: work-item {_ITEM} is spec-change tier and is held for its linked"
        f" proposed-change topic {_DERIVED_TOPIC}; no claim was taken and no factory run was"
        " created. The spec-stated judgement reported its asked-for behaviour unstated"
        f" and named {_TARGET} as the heading to generalize. Hold reason: unratified-topic.\n"
    )


def test_a_rejected_revision_adds_nothing_to_the_refusal(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    spec_root = repo / "SPECIFICATION"
    _ = _snapshot(spec_root=spec_root, version=1, body="old body")
    _revise(
        version_dir=_snapshot(spec_root=spec_root, version=2, body="new body"),
        topic="a-rejected-topic",
        decision="reject",
    )
    _record_hold(repo=repo, spec_version="1")

    refusal = _refusal(repo=repo)
    assert "relink" not in refusal
    assert "a-rejected-topic" not in refusal

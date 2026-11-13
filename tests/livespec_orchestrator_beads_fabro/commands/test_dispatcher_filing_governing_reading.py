"""The filing display reuses and records its governing-heading verdict."""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_filing_governing_reading"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_filing_governing_reading.py"
)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-3h7dsf",
        type="bug",
        status="backlog",
        title="Reuse a filing verdict",
        description="## Definition of Done\n\n- The display reuses a recorded verdict.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def test_a_second_unchanged_filing_read_reuses_the_receipt_without_a_judge_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One current receipt has the same display answer and spends no second taking."""
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)
    comments: list[str] = []
    verdict = GoverningHeadingVerdict(kind="unstated")
    candidates = 0

    def reusable(
        *, item: WorkItem, repo: Path, comments: tuple[str, ...]
    ) -> GoverningHeadingVerdict | None:
        _ = (item, repo)
        return verdict if comments else None

    def taking_reader(*, runner: object) -> object:
        del runner

        def read(*, item: WorkItem, repo: Path) -> object:
            nonlocal candidates
            _ = (item, repo)
            candidates += 1
            return module.GoverningHeadingTaking(verdict=verdict)

        return read

    monkeypatch.setattr(module, "store_config", lambda *, repo: (repo, object())[1])
    monkeypatch.setattr(
        module,
        "judgement_comment_bodies",
        lambda *, path, work_item_id, repo: (path, work_item_id, repo, tuple(comments))[3],
    )
    monkeypatch.setattr(module, "reusable_governing_heading_verdict", reusable)
    monkeypatch.setattr(module, "host_governing_heading_taking_reader", taking_reader)
    monkeypatch.setattr(
        module,
        "append_work_item_comment",
        lambda *, path, work_item_id, body: (path, work_item_id, comments.append(body))[2],
    )

    first = module.filing_governing_heading_reading(item=_item(), repo=tmp_path)
    second = module.filing_governing_heading_reading(item=_item(), repo=tmp_path)

    assert candidates == 1
    assert first.verdict == second.verdict == verdict
    assert first.not_taken_reason is second.not_taken_reason is None
    assert len(comments) == 1
    assert comments[0].startswith("livespec-dod-judgement\n")
    assert "outcome:" not in comments[0]


def test_an_unusable_taking_never_appends_a_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An evidence-discarded candidate must be tried again, not recorded as clean."""
    module = importlib.import_module(_MODULE)
    comments: list[str] = []

    monkeypatch.setattr(module, "store_config", lambda *, repo: (repo, object())[1])
    monkeypatch.setattr(
        module,
        "judgement_comment_bodies",
        lambda *, path, work_item_id, repo: (path, work_item_id, repo, tuple(comments))[3],
    )
    monkeypatch.setattr(
        module,
        "reusable_governing_heading_verdict",
        lambda **_: None,
    )
    monkeypatch.setattr(
        module,
        "host_governing_heading_taking_reader",
        lambda *, runner: (
            runner,
            lambda **_: module.GoverningHeadingTaking(
                verdict=None, not_taken_reason="evidence-quote check discarded the reply"
            ),
        )[1],
    )
    monkeypatch.setattr(
        module,
        "append_work_item_comment",
        lambda *, path, work_item_id, body: (path, work_item_id, comments.append(body))[2],
    )

    reading = module.filing_governing_heading_reading(item=_item(), repo=tmp_path)

    assert reading.verdict is None
    assert reading.not_taken_reason == "evidence-quote check discarded the reply"
    assert comments == []


def test_a_failed_receipt_append_keeps_the_taken_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = importlib.import_module(_MODULE)
    verdict = GoverningHeadingVerdict(kind="unstated")
    monkeypatch.setattr(module, "store_config", lambda *, repo: (repo, object())[1])
    monkeypatch.setattr(module, "judgement_comment_bodies", lambda **_: ())
    monkeypatch.setattr(module, "reusable_governing_heading_verdict", lambda **_: None)
    monkeypatch.setattr(
        module,
        "host_governing_heading_taking_reader",
        lambda **_: lambda **_: module.GoverningHeadingTaking(verdict=verdict),
    )
    monkeypatch.setattr(
        module,
        "append_work_item_comment",
        lambda **_: (_ for _ in ()).throw(
            module.BeadsCommandError(command="bd", exit_code=1, stderr="down")
        ),
    )

    assert module.filing_governing_heading_reading(item=_item(), repo=tmp_path).verdict == verdict


def test_the_claude_journal_header_identifies_the_item_and_full_prompt_digest(
    tmp_path: Path,
) -> None:
    """The digest remains exact even though the retained prompt is truncated."""
    journal_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._host_judge_spend_journal"
    )
    prompt = "x" * 2_100

    journal = journal_module.start_spend_journal(
        home=tmp_path,
        name="purpose:dod_governing_heading@repo",
        cwd=tmp_path / "repo",
        first_prompt=prompt,
        work_item_id="bd-ib-3h7dsf",
    )

    header = json.loads(journal.path.read_text(encoding="utf-8").splitlines()[0])
    assert header["work_item_id"] == "bd-ib-3h7dsf"
    assert header["first_prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert len(header["first_prompt"]) == 2_000

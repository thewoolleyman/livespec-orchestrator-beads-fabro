"""The groom classification's two arms a healthy draft never reaches.

CONTROLS for `test_groom_spec_change_classification.py` rather than claims of
their own. Each one is what WOULD fail if a later edit made the groom position
decide a tier on evidence it does not have — an unreadable VERDICT, which is a
different failure from the unreadable CLASSIFICATION the sibling module covers,
and a candidate whose acceptance field is blank, where naming the absence is
what keeps the judge from reporting `unstated` for a half it was never shown.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._groom_spec_change_classification import (
    classified_candidate_slices,
)
from livespec_orchestrator_beads_fabro.commands._groom_types import CandidateSlice

_HEADING = "## A governing clause"


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _candidate(*, acceptance: str = "- It does the new thing.") -> CandidateSlice:
    return CandidateSlice(
        title="A drafted slice",
        description="New observable behaviour.",
        acceptance=acceptance,
        autonomy_tier="factory",
        repo_target="livespec-orchestrator-beads-fabro",
        is_spec_change=False,
    )


def _install_judge(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replies: tuple[str, ...]
) -> None:
    ledger = tmp_path / "judge-calls"
    script = tmp_path / "fake-judge"
    arms = "\n".join(
        f"{index})\n  cat <<'REPLY'\n{reply}\nREPLY\n  ;;"
        for index, reply in enumerate(replies, start=1)
    )
    _ = script.write_text(
        "#!/bin/sh\n"
        f"echo call >> {ledger}\n"
        f"calls=$(wc -l < {ledger} | tr -d ' ')\n"
        # The prompt travels on STANDARD INPUT, so capturing it here is how the
        # statement the judge really sees becomes assertable without reaching
        # past the module's public surface.
        f"cat > {tmp_path}/prompt-$calls\n"
        "case $calls in\n"
        f"{arms}\n"
        "*)\n  exit 1\n  ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def test_an_unreadable_verdict_leaves_the_draft_standing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("feature", "not a verdict"))
    declared = [_candidate()]

    assert classified_candidate_slices(slices=declared, repo=_repo(tmp_path=tmp_path)) == declared


def test_a_blank_field_is_named_rather_than_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read off the PROMPT the judge received, never past the public surface.

    The statement is what the judge is handed on standard input, so the capture
    is also the only instrument that can show the absence was NAMED rather than
    dropped: a renderer that omitted the field produces a prompt in which the
    line is simply missing, which is indistinguishable from an item whose
    criteria the renderer failed to read.
    """
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", "not a verdict"),
    )
    _ = classified_candidate_slices(
        slices=[_candidate(acceptance="   ")], repo=_repo(tmp_path=tmp_path)
    )

    # The SECOND call is the spec-stated judgement, whose prompt carries the
    # behaviour statement; the first is the classification.
    rendered = (tmp_path / "prompt-2").read_text(encoding="utf-8")
    assert "Acceptance criteria: (none recorded)" in rendered
    assert "Title: A drafted slice" in rendered

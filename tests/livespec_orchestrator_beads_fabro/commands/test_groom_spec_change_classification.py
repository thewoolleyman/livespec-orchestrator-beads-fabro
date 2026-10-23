"""At groom the tier is decided by the judgement, with the draft as evidence.

The GROOM cadence point of assertion 1 of `bd-ib-57ss2n`: "At filing, at groom
and on each dispatch path, every implement-kind item is classified by the
spec-stated judgement, with the stored type as evidence". The autonomy-tier
bullet of `SPECIFICATION/contracts.md` makes the groom position explicit and
says the tier is "never declared by the filer" — and at groom the filer is the
DRAFT, whose `is_spec_change` field is exactly such a declaration.

So the draft's own flag is EVIDENCE here in the same sense the stored type is
evidence at filing: it is what somebody happened to record, and the judgement is
the answer. Both directions are asserted, because the clause's defect is
two-sided — a draft that declared a factory slice must be ROUTED to
propose-change when its behaviour is unstated, and a draft that declared a
spec-change slice must be FILED when the specification already states it.

A `bug` IS NEVER SPEC-CHANGE TIER whatever the draft says, which is the third
case and the one that keeps the groom door from closing on ordinary repair work.

AND A JUDGEMENT THAT CANNOT RUN LEAVES THE DRAFT'S OWN DECLARATION STANDING,
which is the clause's route-as-before direction at this position: the groom cut
is the maintainer's, and a classifier outage must not silently re-route a slice
the maintainer declared.
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
_UNSTATED = (
    '{"kind": "unstated", "stated_by": [], "generalization_target": '
    f'"{_HEADING}", "rationale": "the ratified text does not state it"}}'
)
_STATED = (
    f'{{"kind": "stated", "stated_by": ["{_HEADING}"], '
    '"generalization_target": null, "rationale": "the clause states it"}'
)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_HEADING}\n\nThe clause body.\n", encoding="utf-8"
    )
    return repo


def _candidate(*, is_spec_change: bool, title: str = "A drafted slice") -> CandidateSlice:
    return CandidateSlice(
        title=title,
        description="New observable behaviour.",
        acceptance="- It does the new thing.",
        autonomy_tier="factory",
        repo_target="livespec-orchestrator-beads-fabro",
        is_spec_change=is_spec_change,
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
        "case $calls in\n"
        f"{arms}\n"
        "*)\n  exit 1\n  ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("LIVESPEC_DOD_JUDGEMENT_CLAUDE_PATH", str(script))


def test_the_judgement_overrides_the_draft_in_both_directions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_judge(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        replies=("feature", _UNSTATED, "feature", _STATED),
    )
    classified = classified_candidate_slices(
        slices=[
            _candidate(is_spec_change=False, title="Declared a factory slice"),
            _candidate(is_spec_change=True, title="Declared a spec-change slice"),
        ],
        repo=_repo(tmp_path=tmp_path),
    )

    # The draft said factory and the behaviour is unstated: it routes to
    # propose-change.
    assert classified[0].is_spec_change is True
    # The draft said spec-change and the specification already states it: it is
    # filed as ordinary work.
    assert classified[1].is_spec_change is False
    # Nothing else about either candidate moved.
    assert classified[0].title == "Declared a factory slice"
    assert classified[1].repo_target == "livespec-orchestrator-beads-fabro"


def test_a_bug_is_never_spec_change_tier_whatever_the_draft_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("bug",))
    classified = classified_candidate_slices(
        slices=[_candidate(is_spec_change=True)], repo=_repo(tmp_path=tmp_path)
    )
    assert classified[0].is_spec_change is False


def test_a_judgement_that_cannot_run_leaves_the_draft_standing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_judge(tmp_path=tmp_path, monkeypatch=monkeypatch, replies=("not-a-class",))
    declared = [_candidate(is_spec_change=True), _candidate(is_spec_change=False)]

    classified = classified_candidate_slices(slices=declared, repo=_repo(tmp_path=tmp_path))
    assert [one.is_spec_change for one in classified] == [True, False]


def test_an_unreadable_spec_tree_leaves_every_draft_standing(tmp_path: Path) -> None:
    declared = [_candidate(is_spec_change=True), _candidate(is_spec_change=False)]

    classified = classified_candidate_slices(slices=declared, repo=tmp_path / "absent")
    assert [one.is_spec_change for one in classified] == [True, False]
    assert classified == declared
